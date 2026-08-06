"""Regressão: os defeitos que só apareceriam contra o provedor real (FDD 024).

Todos os três moram atrás de `# pragma: no cover` — a chamada HTTP de verdade —, e por isso
passaram por 493 testes sem serem notados. Os testes abaixo exercitam a **regra**, extraída da
chamada de rede justamente para poder ser testada sem ela.

A propriedade que une os três: **falhar fechado**. Um agendamento que não enxerga a agenda não pode
concluir "está tudo livre"; uma integração sem credencial não pode se dizer pronta.
"""

from datetime import date, datetime, timedelta

import pytest
from django.test import override_settings

from apps.core import calendar_sync, flags

pytestmark = pytest.mark.django_db


# --- evento de dia inteiro: `end.date` é exclusivo ---------------------------------------------


def test_evento_de_dia_inteiro_termina_no_dia_seguinte() -> None:
    """O Google trata `end.date` como exclusivo: start == end é intervalo de comprimento zero,
    e a API recusa. O botão "Adicionar ao calendário" falhava em 100% das tentativas."""
    inicio, fim = calendar_sync.all_day_range(date(2026, 8, 6))

    assert inicio == "2026-08-06"
    assert fim == "2026-08-07"
    assert inicio != fim


def test_intervalo_de_dia_inteiro_nunca_tem_comprimento_zero() -> None:
    for dia in (date(2026, 1, 1), date(2026, 2, 28), date(2026, 12, 31)):
        inicio, fim = calendar_sync.all_day_range(dia)
        assert date.fromisoformat(fim) - date.fromisoformat(inicio) == timedelta(days=1)


# --- free/busy: falhar fechado ------------------------------------------------------------------


def _resposta(**agenda: object) -> dict:
    return {"calendars": {"agenda@x.test": agenda}}


def test_freebusy_le_os_periodos_ocupados() -> None:
    resultado = calendar_sync.parse_freebusy(
        _resposta(busy=[{"start": "2026-08-06T10:00:00+00:00", "end": "2026-08-06T11:00:00+00:00"}]),
        "agenda@x.test",
    )

    assert resultado == [
        (datetime.fromisoformat("2026-08-06T10:00:00+00:00"),
         datetime.fromisoformat("2026-08-06T11:00:00+00:00"))
    ]


def test_agenda_vazia_e_agenda_livre_de_verdade() -> None:
    """`busy: []` presente é resposta legítima — o dia está livre mesmo."""
    assert calendar_sync.parse_freebusy(_resposta(busy=[]), "agenda@x.test") == []


def test_calendario_inacessivel_nao_vira_agenda_livre() -> None:
    """O defeito. O Google devolve **200** com `errors` no lugar de `busy` quando a conta de
    serviço não enxerga o calendário; ler isso como `[]` significa "tudo livre", e o site passa a
    marcar reunião por cima da agenda real. Falhar aberto é a pior direção possível.
    """
    with pytest.raises(calendar_sync.CalendarUnavailable, match="notFound"):
        calendar_sync.parse_freebusy(
            _resposta(errors=[{"domain": "global", "reason": "notFound"}]), "agenda@x.test"
        )


def test_resposta_sem_busy_nao_vira_agenda_livre() -> None:
    with pytest.raises(calendar_sync.CalendarUnavailable):
        calendar_sync.parse_freebusy(_resposta(), "agenda@x.test")


def test_resposta_sem_o_calendario_pedido_nao_vira_agenda_livre() -> None:
    with pytest.raises(calendar_sync.CalendarUnavailable):
        calendar_sync.parse_freebusy({"calendars": {}}, "agenda@x.test")


# --- `configured()` cobra o que o código dereferencia -------------------------------------------


@override_settings(GOOGLE_DRIVE_ROOT_FOLDER_ID="pasta", GOOGLE_SERVICE_ACCOUNT_INFO="",
                   GOOGLE_SERVICE_ACCOUNT_FILE="")
def test_drive_nao_se_diz_pronto_sem_a_conta_de_servico() -> None:
    """Antes, o id da pasta bastava para a tela Configurações liberar o toggle — e o primeiro
    upload estourava em `_service()`, com o arquivo do usuário perdido junto."""
    assert flags.configured("drive") is False
    assert any("GOOGLE_SERVICE_ACCOUNT" in falta for falta in flags.missing("drive"))


@override_settings(GOOGLE_DRIVE_ROOT_FOLDER_ID="pasta", GOOGLE_SERVICE_ACCOUNT_INFO="{}",
                   GOOGLE_SERVICE_ACCOUNT_FILE="")
def test_credencial_do_google_aceita_json_inline_ou_arquivo() -> None:
    """São duas formas da mesma credencial: exigir ambas recusaria instalação legítima."""
    assert flags.configured("drive") is True


@override_settings(GOOGLE_DRIVE_ROOT_FOLDER_ID="pasta", GOOGLE_SERVICE_ACCOUNT_INFO="",
                   GOOGLE_SERVICE_ACCOUNT_FILE="/caminho/sa.json")
def test_credencial_do_google_por_arquivo_tambem_serve() -> None:
    assert flags.configured("drive") is True


@override_settings(GOOGLE_CALENDAR_ID="agenda", GOOGLE_SERVICE_ACCOUNT_INFO="",
                   GOOGLE_SERVICE_ACCOUNT_FILE="")
def test_calendario_nao_se_diz_pronto_sem_a_conta_de_servico() -> None:
    assert flags.configured("calendar") is False


@override_settings(ESIGN_PROVIDER="autentique", ESIGN_API_TOKEN="", ESIGN_WEBHOOK_SECRET="")
def test_esign_nao_se_diz_pronto_so_com_o_nome_do_provedor() -> None:
    assert flags.configured("esign") is False
    assert "ESIGN_API_TOKEN" in flags.missing("esign")
    # Sem o segredo do webhook o status do fornecedor leva 401 e a assinatura nunca fecha sozinha.
    assert "ESIGN_WEBHOOK_SECRET" in flags.missing("esign")


@override_settings(TASKSYNC_TOKEN="entrada", LINEAR_API_KEY="", GITHUB_TOKEN="")
def test_tasksync_nao_se_diz_pronto_so_com_o_segredo_de_entrada() -> None:
    """`TASKSYNC_TOKEN` autentica quem entra; sem credencial de fornecedor a saída fica muda."""
    assert flags.configured("tasksync") is False


@override_settings(TASKSYNC_TOKEN="entrada", LINEAR_API_KEY="", GITHUB_TOKEN="ghp_x")
def test_tasksync_aceita_um_fornecedor_so() -> None:
    assert flags.configured("tasksync") is True


# --- o número não pode mentir -------------------------------------------------------------------


@override_settings(EMAIL_NOTIFICATIONS_ENABLED=True, AI_ENABLED=False)
def test_digest_nao_conta_envio_que_o_smtp_recusou(monkeypatch: pytest.MonkeyPatch) -> None:
    """O laço somava 1 por usuário independentemente do resultado, e `fail_silently=True` engole a
    falha — então o scheduler logava "Digests enviados: 12" com zero entregues. É o defeito do
    agendador que não existia, uma camada abaixo: o número dizia que estava tudo bem.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.core import digest
    from apps.core.models import Task
    from apps.core.tests.factories import ProjectFactory, UserFactory

    dono = UserFactory(email="dono@x.test")
    projeto = ProjectFactory(owner=dono)
    Task.objects.create(
        project=projeto, title="Atrasada", owner=dono,
        due_date=timezone.localdate() - timedelta(days=2),
    )

    # SMTP recusando: `send_mail` devolve 0 em vez de levantar.
    monkeypatch.setattr(digest, "send_mail", lambda *a, **k: 0)

    assert digest.send_daily_digest() == 0


@override_settings(EMAIL_NOTIFICATIONS_ENABLED=True, AI_ENABLED=False)
def test_digest_conta_o_que_saiu_de_verdade(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import timedelta

    from django.utils import timezone

    from apps.core import digest
    from apps.core.models import Task
    from apps.core.tests.factories import ProjectFactory, UserFactory

    dono = UserFactory(email="dono@x.test")
    projeto = ProjectFactory(owner=dono)
    Task.objects.create(
        project=projeto, title="Atrasada", owner=dono,
        due_date=timezone.localdate() - timedelta(days=2),
    )
    monkeypatch.setattr(digest, "send_mail", lambda *a, **k: 1)

    assert digest.send_daily_digest() == 1


# --- o fornecedor não derruba o pedido ----------------------------------------------------------


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-x")
def test_openai_fora_do_ar_nao_derruba_o_formulario_publico(monkeypatch: pytest.MonkeyPatch) -> None:
    """`qualify_lead` roda dentro do POST público de intake. Sem guarda, um 429 ou um timeout
    da OpenAI viravam 500 para o visitante — e o `Lead` já estava gravado, então ele via erro
    para um cadastro que funcionou.
    """
    from apps.core import ai, qualification
    from apps.core.models import Lead

    def explode(*a: object, **k: object) -> tuple[str, dict]:
        raise RuntimeError("429 Rate limit reached")

    monkeypatch.setattr(ai, "complete", explode)
    lead = Lead.objects.create(name="Fulano", email="fulano@x.test")

    # Não levanta, e devolve o mesmo que devolveria com a IA desligada: triagem manual.
    assert qualification.qualify_lead(lead) is False


# --- convite: o e-mail é o convite ---------------------------------------------------------------


@override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
                   EMAIL_HOST="127.0.0.1", EMAIL_PORT=1)
def test_convite_nao_fica_orfao_quando_o_smtp_recusa() -> None:
    """Observado na homologação da FDD 024, com o SMTP apontado para uma porta morta.

    O convite **é** o e-mail: quem recebe não tem outro caminho para o token. Antes, a linha era
    gravada e o `fail_silently=False` devolvia 500 — sobrava um convite válido que ninguém recebeu,
    o admin achava que falhara, e cada tentativa criava mais um. Agora grava e envia na mesma
    transação: ou os dois acontecem, ou nenhum.
    """
    from django.urls import reverse
    from rest_framework.test import APIClient

    from apps.core.models import Invitation, User
    from apps.core.tests.factories import UserFactory

    admin = UserFactory(role=User.Role.ADMIN)
    client = APIClient()
    client.force_authenticate(admin)
    antes = Invitation.objects.count()

    resposta = client.post(
        reverse("invitation"), {"email": "ninguem@exemplo.test", "role": "delivery"}, format="json"
    )

    assert resposta.status_code == 502
    assert Invitation.objects.count() == antes
    assert not Invitation.objects.filter(email="ninguem@exemplo.test").exists()
