"""Regressão: a sessão que o cliente marcou atravessa para o projeto que nasce do mandato.

Três defeitos observados em uso, todos com a **mesma** raiz — o `Booking` do Discovery não chegava
ao projeto (ADR 0061, emenda de 02/09 da FDD 046):

* o painel "Saúde da relação" dizia *"Próxima reunião: A agendar"* com a sessão marcada, porque
  `build_account_overview` lê `Meeting` e o agendamento cria `Booking`;
* a tarefa "Agendar a sessão de discovery" nascia pendente logo depois de a automação a cumprir;
* o cronograma não se ancorava na sessão — e essa metade fica com a **tela**, que pré-preenche o
  formulário a partir de `discovery_scheduled_at`. O servidor não sobrescreve as datas escolhidas
  (DAP `dap-engagement-r3`, C1).

Os dois primeiros são testados **pelo efeito observável**: o que importa não é a linha da `Meeting`
ter sido criada, é o painel parar de dizer "A agendar" e a tarefa nascer concluída.
"""

from datetime import UTC, datetime, time, timedelta

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import booking, calendar_sync, discovery_booking, kickoff
from apps.core.models import Engagement, Meeting, Project, Service, Task, User
from apps.core.tests.factories import AccountFactory, EngagementFactory, UserFactory
from apps.core.views import build_account_overview

pytestmark = pytest.mark.django_db

LIGADA = override_settings(
    DISCOVERY_BOOKING_ENABLED=True, CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal"
)


def _next_monday():
    hoje = timezone.localdate()
    return hoje + timedelta(days=(7 - hoje.weekday()) % 7 or 7)


def _at(day, hour, minute=0) -> datetime:
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(day, time(hour, minute)), tz)


def _api(role: str = User.Role.ADMIN) -> tuple[APIClient, User]:
    quem = UserFactory(role=role)
    api = APIClient()
    api.force_authenticate(quem)
    return api, quem


def _mandato() -> Engagement:
    return EngagementFactory(
        account=AccountFactory(), commercial_model=Engagement.CommercialModel.DESIGN_PARTNER
    )


def _agenda(monkeypatch, link: str = "https://meet.example/abc") -> None:
    monkeypatch.setattr(calendar_sync, "freebusy", lambda a, b: [])
    monkeypatch.setattr(calendar_sync, "create_timed_event", lambda **kw: ("ev", link))


def _criar_projeto(api: APIClient, engagement: Engagement, tier: str = Service.Tier.DISCOVERY_SPRINT):
    degrau = Service.objects.get(tier=tier)
    return api.post(
        reverse("engagement-create-project", args=[engagement.pk]),
        {
            "name": f"Discovery Sprint — {engagement.account.name}",
            "service": degrau.pk,
            "start_date": str(timezone.localdate()),
            "due_date": str(timezone.localdate() + timedelta(days=10)),
        },
        format="json",
    )


# --- o painel para de dizer "A agendar" -----------------------------------------------------


@LIGADA
def test_a_sessao_marcada_vira_a_proxima_reuniao_do_painel(monkeypatch) -> None:
    """O efeito observável: `next_meeting` do agregado, não a existência da linha.

    É por `build_account_overview` que o painel "Saúde da relação" responde, e ele só conhece
    `Meeting`. Afirmar aqui só `Meeting.objects.exists()` deixaria passar uma `Meeting` criada com
    `status=held` ou com data no passado — as duas somem do agregado e o painel voltaria a mentir.
    """
    _agenda(monkeypatch)
    api, _ = _api()
    UserFactory()
    engagement = _mandato()
    sessao = _at(_next_monday(), 9)
    booking.book_discovery(engagement, sessao, "quem@x.test")

    assert _criar_projeto(api, engagement).status_code == 201

    overview = build_account_overview(engagement.account)
    assert overview["next_meeting"] is not None
    assert overview["next_meeting"]["date"] == sessao.date().isoformat()


@LIGADA
def test_a_reuniao_leva_o_link_do_convite(monkeypatch) -> None:
    _agenda(monkeypatch, link="https://meet.example/sessao")
    api, _ = _api()
    UserFactory()
    engagement = _mandato()
    booking.book_discovery(engagement, _at(_next_monday(), 9), "quem@x.test")

    resposta = _criar_projeto(api, engagement)

    reuniao = Meeting.objects.get(project_id=resposta.data["id"])
    assert reuniao.meeting_url == "https://meet.example/sessao"
    assert reuniao.title == discovery_booking.TITULO_DA_SESSAO_DE_DISCOVERY
    assert reuniao.status == Meeting.Status.SCHEDULED


@LIGADA
def test_sem_sessao_marcada_o_projeto_nasce_sem_reuniao(monkeypatch) -> None:
    _agenda(monkeypatch)
    api, _ = _api()
    engagement = _mandato()

    resposta = _criar_projeto(api, engagement)

    assert resposta.status_code == 201
    assert not Meeting.objects.filter(project_id=resposta.data["id"]).exists()
    assert build_account_overview(engagement.account)["next_meeting"] is None


# --- a data respeita o fuso local -----------------------------------------------------------


@LIGADA
def test_a_data_da_reuniao_e_a_local_e_nao_a_de_utc(monkeypatch) -> None:
    """Uma sessão às 21h em `America/Sao_Paulo` é meia-noite do dia seguinte em UTC.

    `Meeting.date` é `DateField` e a reserva é `DateTimeField`: converter no fuso errado joga a
    sessão para o dia seguinte, e o painel passa a anunciar uma reunião que não é a marcada.
    """
    _agenda(monkeypatch)
    api, _ = _api()
    UserFactory()
    engagement = _mandato()
    dia = _next_monday()
    tarde_da_noite = _at(dia, 21)
    # A reserva é gravada direto: a grade comercial não oferta 21h, e o que se testa aqui é a
    # conversão de fuso, não a oferta.
    from apps.core.models import Booking

    Booking.objects.create(
        engagement=engagement,
        starts_at=tarde_da_noite,
        ends_at=tarde_da_noite + timedelta(minutes=45),
        attendee_email="quem@x.test",
    )
    assert tarde_da_noite.astimezone(UTC).date() > dia, "o caso perdeu o sentido"

    resposta = _criar_projeto(api, engagement)

    reuniao = Meeting.objects.get(project_id=resposta.data["id"])
    assert reuniao.date == dia


# --- a tarefa de agendar ---------------------------------------------------------------------


@LIGADA
def test_a_tarefa_de_agendar_nasce_concluida_quando_havia_sessao(monkeypatch) -> None:
    _agenda(monkeypatch)
    api, _ = _api()
    UserFactory()
    engagement = _mandato()
    booking.book_discovery(engagement, _at(_next_monday(), 9), "quem@x.test")

    resposta = _criar_projeto(api, engagement)

    tarefa = Task.objects.get(
        project_id=resposta.data["id"], title=kickoff.TAREFA_DE_AGENDAR_O_DISCOVERY
    )
    assert tarefa.status == Task.Status.DONE
    # `completed_at` vem de `WorkItem.save()`: concluída sem data é estado que o cronograma lê.
    assert tarefa.completed_at is not None


@LIGADA
def test_a_tarefa_de_agendar_nasce_pendente_quando_nao_havia_sessao(monkeypatch) -> None:
    _agenda(monkeypatch)
    api, _ = _api()
    engagement = _mandato()

    resposta = _criar_projeto(api, engagement)

    tarefa = Task.objects.get(
        project_id=resposta.data["id"], title=kickoff.TAREFA_DE_AGENDAR_O_DISCOVERY
    )
    assert tarefa.status == Task.Status.TODO
    assert tarefa.completed_at is None


def test_o_template_do_discovery_usa_a_constante_da_tarefa() -> None:
    """Sem isto, alguém reescreve o texto do template e a tarefa nasce pendente para sempre —
    calado, porque nada mais liga os dois lados."""
    titulos = [
        titulo
        for marco in kickoff.KICKOFF_TEMPLATES["discovery_sprint"]
        for titulo in marco["tasks"]
    ]
    assert kickoff.TAREFA_DE_AGENDAR_O_DISCOVERY in titulos


# --- as datas do projeto continuam sendo as do formulário ------------------------------------


@LIGADA
def test_o_servidor_nao_sobrescreve_as_datas_do_formulario(monkeypatch) -> None:
    """C1 do DAP `dap-engagement-r3`: quem pré-preenche é a tela, com `discovery_scheduled_at`."""
    _agenda(monkeypatch)
    api, _ = _api()
    UserFactory()
    engagement = _mandato()
    booking.book_discovery(engagement, _at(_next_monday(), 9), "quem@x.test")
    inicio, prazo = timezone.localdate(), timezone.localdate() + timedelta(days=10)

    resposta = _criar_projeto(api, engagement)

    projeto = Project.objects.get(pk=resposta.data["id"])
    assert projeto.start_date == inicio
    assert projeto.due_date == prazo


# --- `discovery_scheduled_at` ---------------------------------------------------------------


@LIGADA
def test_o_mandato_publica_a_sessao_agendada(monkeypatch) -> None:
    _agenda(monkeypatch)
    api, _ = _api()
    UserFactory()
    engagement = _mandato()
    sessao = _at(_next_monday(), 9)
    booking.book_discovery(engagement, sessao, "quem@x.test")

    linha = api.get(reverse("engagement-detail", args=[engagement.pk])).data

    assert linha["discovery_scheduled_at"] is not None
    assert linha["discovery_scheduled_at"][:10] == sessao.date().isoformat()


def test_o_mandato_sem_sessao_publica_nulo() -> None:
    api, _ = _api()
    engagement = _mandato()

    linha = api.get(reverse("engagement-detail", args=[engagement.pk])).data

    assert linha["discovery_scheduled_at"] is None


@LIGADA
def test_a_sessao_so_atravessa_para_o_projeto_que_e_o_discovery(monkeypatch) -> None:
    """Um mandato origina vários projetos, e a reserva continua viva depois da sessão.

    Nada fecha a `Booking` quando a conversa acontece. Sem a guarda de degrau, o projeto de
    Feasibility criado semanas depois herdaria uma "Sessão de Discovery" que não é dele — a
    **mesma** reunião do mundo aparecendo em dois cronogramas, e contando duas vezes no "Próxima
    reunião" da conta.
    """
    _agenda(monkeypatch)
    api, _ = _api()
    UserFactory()
    engagement = _mandato()
    booking.book_discovery(engagement, _at(_next_monday(), 9), "quem@x.test")

    assert _criar_projeto(api, engagement).status_code == 201
    assert _criar_projeto(api, engagement, tier=Service.Tier.FEASIBILITY).status_code == 201

    discovery = Project.objects.get(service__tier=Service.Tier.DISCOVERY_SPRINT)
    feasibility = Project.objects.get(service__tier=Service.Tier.FEASIBILITY)

    assert discovery.meetings.count() == 1
    assert feasibility.meetings.count() == 0, "a sessão do Discovery não é reunião do Feasibility"


@LIGADA
def test_projeto_sem_degrau_nao_recebe_a_sessao(monkeypatch) -> None:
    """Sem degrau, o sistema não tem como afirmar que a sessão marcada é deste projeto."""
    _agenda(monkeypatch)
    api, _ = _api()
    UserFactory()
    engagement = _mandato()
    booking.book_discovery(engagement, _at(_next_monday(), 9), "quem@x.test")

    resposta = api.post(
        reverse("engagement-create-project", args=[engagement.pk]),
        {
            "name": "Projeto sem degrau",
            "start_date": str(timezone.localdate()),
            "due_date": str(timezone.localdate() + timedelta(days=10)),
        },
        format="json",
    )

    assert resposta.status_code == 201
    assert Project.objects.get(pk=resposta.data["id"]).meetings.count() == 0
