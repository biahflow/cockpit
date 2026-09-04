"""Regressão: a IA lê a resposta do cliente; **quem registra é gente** (ADR 0032, ADR 0006).

A FDD 036 dá à IA a tarefa de classificar a resposta a uma cobrança em `forgot` / `unable_to_pay` /
`dissatisfied`, e a FDD 038 finalmente dá um **leitor** a esse campo: o painel mostra a leitura e
oferece o atalho para registrá-la. O atalho é a tentação, e é o que este arquivo cerca — entre
"mostrar um formulário pré-preenchido" e "gravar o registro" há uma linha de código e a decisão
inteira da ADR 0032.

O que se perde ao cruzar a linha não aparece em teste de comportamento nenhum: a escada continua
trocando, o Health Score continua descontando, tudo verde. O que muda é o significado. Um
`Satisfacao(fonte=declarada)` gravado pela IA afirma que **o cliente disse** — e o que houve foi um
modelo tendo lido uma frase digitada por quem atendeu. Passa a valer 20 pontos de Health Score e
uma troca de escada por inferência, com a mesma aparência de evidência que o registro humano tem.

O oráculo é o estado depois de classificar: nenhum registro, nenhum ponto, nenhuma escada trocada.
"""

from datetime import date, timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import ai, cobranca, health
from apps.core.models import Activity, Invoice, Satisfacao, User
from apps.core.tests.factories import (
    AccountFactory,
    ActivityFactory,
    InvoiceFactory,
    ProjectFactory,
    UserFactory,
)

HOJE = date(2026, 9, 2)  # quarta-feira, como no resto da suíte de cobrança

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_api() -> APIClient:
    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return api


@pytest.fixture
def insatisfeito(monkeypatch: pytest.MonkeyPatch) -> None:
    """A IA devolvendo o sinal mais perigoso dos três: o que muda comportamento quando registrado."""
    monkeypatch.setattr(
        ai, "complete", lambda s, u, **_: ('{"sinal": "dissatisfied"}', {"prompt_tokens": 1})
    )


def _resposta_de_cobranca() -> Activity:
    account = AccountFactory()
    invoice = InvoiceFactory(
        account=account, status=Invoice.Status.OVERDUE, number="2026-0001",
        due_date=HOJE - timedelta(days=12),
    )
    return ActivityFactory(
        account=account, invoice=invoice,
        summary="Cliente disse que não paga enquanto o marco 2 não entrar.",
        # `HOJE`, e não o dia real: a satisfação criada a partir desta atividade herda a data dela
        # (`str(activity.happened_on)` abaixo), e a régua é avaliada em `HOJE`. Com o dia real, o
        # registro fica **no futuro** em relação a `HOJE` e sai do recorte de `vigente`
        # (`inicio <= happened_on <= hoje`, `satisfacao.py:73`) — foi o que quebrou este arquivo em
        # 2026-09-03, quando o relógio passou da quarta-feira congelada.
        happened_on=HOJE,
    )


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_classificar_nao_cria_satisfacao(admin_api: APIClient, insatisfeito: None) -> None:
    activity = _resposta_de_cobranca()

    resposta = admin_api.post(f"/api/v1/activities/{activity.pk}/classificar/")

    assert resposta.status_code == 200
    activity.refresh_from_db()
    assert activity.dunning_signal == Activity.DunningSignal.DISSATISFIED
    # O sinal foi gravado; o **registro** não. São coisas diferentes, e a diferença é quem afirma.
    assert not Satisfacao.objects.exists()


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_classificar_nao_move_o_health_score(admin_api: APIClient, insatisfeito: None) -> None:
    """20 pontos por inferência seriam indistinguíveis de 20 pontos por evidência — e um número
    errado é consultado com a mesma confiança de um número certo."""
    activity = _resposta_de_cobranca()
    project = ProjectFactory(engagement__account=activity.account)
    antes = health.assess_project_health(project)

    admin_api.post(f"/api/v1/activities/{activity.pk}/classificar/")

    depois = health.assess_project_health(project)
    assert depois["score"] == antes["score"]
    assert depois["signals"] == antes["signals"]


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_classificar_nao_troca_a_escada(admin_api: APIClient, insatisfeito: None) -> None:
    """A régua continua a padrão: em D+12 sai o degrau firme, e não a escalada da relação tensa."""
    activity = _resposta_de_cobranca()
    invoice = activity.invoice
    assert invoice is not None

    admin_api.post(f"/api/v1/activities/{activity.pk}/classificar/")

    assert cobranca.regua_para(activity.account, HOJE, ignorando=invoice) is cobranca.PADRAO
    degrau = cobranca.degrau_devido(invoice, HOJE)
    assert degrau is not None and degrau.key == "firme"


@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_so_o_registro_humano_move_a_escada(admin_api: APIClient, insatisfeito: None) -> None:
    """O complemento, e sem ele os três de cima passariam por o sinal não fazer nada em lugar
    nenhum: registrado por uma pessoa, o **mesmo** sinal troca a escada."""
    activity = _resposta_de_cobranca()
    invoice = activity.invoice
    assert invoice is not None
    admin_api.post(f"/api/v1/activities/{activity.pk}/classificar/")

    resposta = admin_api.post(
        "/api/v1/satisfacoes/",
        {
            "account": activity.account_id,
            "source_activity": activity.pk,
            "nivel": Satisfacao.Nivel.INSATISFEITO,
            "fonte": Satisfacao.Fonte.DECLARADA,
            "happened_on": str(activity.happened_on),
            "note": "Disse na ligação que não paga enquanto o marco 2 não entrar.",
        },
        format="json",
    )

    assert resposta.status_code == 201, resposta.data
    registro = Satisfacao.objects.get()
    # Quem afirma tem nome, e o nome é o da sessão — não o do modelo.
    assert registro.registered_by is not None
    assert registro.source_activity_id == activity.pk
    assert cobranca.regua_para(activity.account, HOJE, ignorando=invoice) is cobranca.RELACAO_TENSA


def test_o_atalho_nao_atravessa_o_cliente(admin_api: APIClient) -> None:
    """A fronteira do `source_activity`: o id vem do corpo da requisição, e a resposta de **outro**
    cliente viraria a satisfação declarada deste — a linha que troca a escada e tira 20 pontos."""
    alheia = ActivityFactory(dunning_signal=Activity.DunningSignal.DISSATISFIED)
    account = AccountFactory()

    resposta = admin_api.post(
        "/api/v1/satisfacoes/",
        {
            "account": account.pk,
            "source_activity": alheia.pk,
            "nivel": Satisfacao.Nivel.INSATISFEITO,
            "fonte": Satisfacao.Fonte.DECLARADA,
            "happened_on": str(timezone.localdate()),
            "note": "Não deveria colar.",
        },
        format="json",
    )

    assert resposta.status_code == 400
    assert "source_activity" in resposta.data
    assert not Satisfacao.objects.exists()
