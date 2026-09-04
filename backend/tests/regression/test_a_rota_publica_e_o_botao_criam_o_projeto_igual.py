"""Regressão: o cliente marcando a sessão e o botão de Vendas fazem nascer o **mesmo** projeto.

É a razão do refactor da ADR 0061. A lógica de "nasce um projeto do mandato" morava **dentro** da
action `EngagementViewSet.create_project`; quando a rota pública de agendamento passou a criar
projeto sozinha, copiar aquele corpo teria produzido duas definições do mesmo ato. Duas definições
não divergem no dia em que nascem — divergem na primeira manutenção, quando alguém acrescenta um
passo de semeadura num lugar só, e o projeto nascido pelo outro caminho sai incompleto.

**O defeito regride calado**, e é por isso que a afirmação está aqui e não só na suíte de cada
fluxo: os dois caminhos continuariam devolvendo 201, os dois continuariam criando `Project`, e a
diferença apareceria semanas depois — um Discovery sem Executive Readout, ou sem a reunião que o
painel "Saúde da relação" lê, ou sem o cronograma de cobrança.

O que se compara é a **forma semeada**, não os campos que legitimamente diferem (nome, dono,
datas): marcos, tarefas, a travessia da sessão marcada e o cronograma de cobrança.
"""

from datetime import datetime, time, timedelta

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import booking, calendar_sync, design_partner, discovery_booking, kickoff
from apps.core.models import (
    Document,
    Engagement,
    Invoice,
    Meeting,
    Milestone,
    Project,
    Service,
    SignatureRequest,
    Task,
    User,
)
from apps.core.tests.factories import AccountFactory, UserFactory

pytestmark = pytest.mark.django_db

LIGADA = override_settings(
    DISCOVERY_BOOKING_ENABLED=True, CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal"
)


def _next_monday():
    today = timezone.localdate()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


def _at(day, hour: int) -> datetime:
    return timezone.make_aware(
        datetime.combine(day, time(hour, 0)), timezone.get_current_timezone()
    )


def _mandato(nome_da_conta: str) -> Engagement:
    uploader = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=uploader, name=nome_da_conta),
        original_name="acordo-design-partner.pdf",
        uploaded_by=uploader,
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
    )
    SignatureRequest.objects.create(
        document=document,
        signer_email="quem.assinou@x.test",
        status=SignatureRequest.Status.SIGNED,
        signed_at=timezone.now(),
    )
    engagement = design_partner.abrir_engagement_do_acordo(document)
    assert engagement is not None
    # Pago dos dois lados: o Design Partner não fatura (`invoices.seed_invoices`), e sem faturas o
    # cronograma de cobrança sairia vazio nos dois — a comparação não afirmaria nada.
    Engagement.objects.filter(pk=engagement.pk).update(
        commercial_model=Engagement.CommercialModel.PAID
    )
    engagement.refresh_from_db()
    return engagement


def _forma_semeada(project: Project) -> dict:
    """O que os dois caminhos precisam produzir igual."""
    return {
        "degrau": project.service.tier if project.service else "",
        "marcos": list(
            Milestone.objects.filter(project=project)
            .order_by("due_date", "id")
            .values_list("title", flat=True)
        ),
        "tarefas": sorted(
            Task.objects.filter(project=project).values_list("title", flat=True)
        ),
        # A sessão marcada atravessa para o projeto, e a tarefa de agendar nasce cumprida.
        "sessoes": list(
            Meeting.objects.filter(project=project).values_list("title", flat=True)
        ),
        "agendar_concluida": Task.objects.filter(
            project=project, title=kickoff.TAREFA_DE_AGENDAR_O_DISCOVERY,
            status=Task.Status.DONE,
        ).exists(),
        "cobrancas": list(
            Invoice.objects.filter(project=project)
            .order_by("due_date", "id")
            .values_list("description", flat=True)
        ),
    }


@LIGADA
def test_a_rota_publica_e_o_botao_criam_o_projeto_do_mesmo_jeito(monkeypatch) -> None:
    monkeypatch.setattr(calendar_sync, "freebusy", lambda a, b: [])
    monkeypatch.setattr(calendar_sync, "create_timed_event", lambda **kw: ("ev", "http://cal/ev"))
    degrau = Service.objects.get(tier=Service.Tier.DISCOVERY_SPRINT)
    slot = _at(_next_monday(), 9)

    # 1) O cliente marca o horário pelo link do convite: o projeto nasce sozinho.
    pelo_cliente = _mandato("Padaria do Zé")
    resposta_publica = APIClient().post(
        reverse("discovery-booking-create"),
        {"token": discovery_booking.token_for(pelo_cliente), "slot_start": slot.isoformat()},
        format="json",
    )
    assert resposta_publica.status_code == 201
    projeto_do_cliente = Project.objects.get(engagement=pelo_cliente)

    # 2) O mesmo cenário, criado pelo botão de Vendas — com a sessão já marcada, que é o estado
    # em que a action roda quando alguém a usa depois do agendamento.
    pelo_botao = _mandato("Rio Home Care")
    booking.book_discovery(pelo_botao, _at(_next_monday(), 10), "quem.assinou@x.test")
    vendas = UserFactory(role=User.Role.SALES)
    api = APIClient()
    api.force_authenticate(vendas)
    resposta_da_action = api.post(
        reverse("engagement-create-project", args=[pelo_botao.pk]),
        {
            "name": f"Discovery Sprint — {pelo_botao.account.name}",
            "service": degrau.pk,
            "start_date": str(projeto_do_cliente.start_date),
            "due_date": str(projeto_do_cliente.due_date),
        },
        format="json",
    )
    assert resposta_da_action.status_code == 201
    projeto_da_action = Project.objects.get(pk=resposta_da_action.data["id"])

    assert _forma_semeada(projeto_do_cliente) == _forma_semeada(projeto_da_action)
    # E a forma não é vazia dos dois lados — uma comparação entre dois nadas passaria sempre.
    forma = _forma_semeada(projeto_do_cliente)
    assert forma["marcos"] and forma["tarefas"] and forma["sessoes"] and forma["cobrancas"]
    assert forma["agendar_concluida"]
