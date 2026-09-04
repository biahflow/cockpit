"""Regressão: `client_name`, `client_vertical*` e a chave `clients` continuam na `/api/v1/`.

A fatia 4a da issue #122 recolheu as chaves com «client» que **nunca tinham entrado** no mapa de
aliases (`apps/core/openapi_aliases.py`): o nome da conta em cinco serializers e em dois
agregadores de dict cru, a vertical projetada no projeto, e a chave que envolve a lista inteira em
`GET /clients/overview/`. Todas ganharam a canônica ao lado — `account_name`,
`account_vertical`/`account_vertical_name`, `accounts` — e todas morrem na `/api/v2/`.

**Nenhuma delas é renome de campo, e é isso que torna esta regressão a única coisa que as segura.**
`client_name` sempre foi projeção (`source="account.name"`), `client_vertical` sempre atravessou
`engagement.account.vertical` — não há coluna com esse nome em lugar nenhum, então uma varredura
atrás do último resquício de «client» olharia para estas linhas e não veria nada apontando de volta
para elas: a SPA lê, o backend não. Removê-las quebraria a `/api/v1/` sem nada ficar vermelho aqui
dentro, que é exatamente o modo de falha que a `docs/ontology/aliases.md` §2c descreve.

**A escrita não entra aqui, e a ausência é deliberada.** As quatro chaves são só de leitura nas
duas versões — não há nada a normalizar na v1 —, então o que a §2c exige é a prova da leitura. A
recusa delas no corpo da v2 (400 dizendo a canônica) está em `tests/test_aliases_da_v2.py`, junto
das outras.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Invoice, User, Vertical
from apps.core.tests.factories import (
    AccountFactory,
    EngagementFactory,
    InvoiceFactory,
    ProcessFactory,
    ProjectFactory,
    UserFactory,
)


@pytest.fixture
def admin_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


@pytest.mark.django_db
def test_a_fatura_devolve_os_dois_nomes_com_o_mesmo_valor(admin_client: APIClient) -> None:
    """`GET /invoices/` sai com `account_name` (canônica) **e** `client_name`."""
    fatura = InvoiceFactory()

    resposta = admin_client.get(reverse("invoice-list"))

    assert resposta.status_code == 200
    linha = next(item for item in resposta.data if item["id"] == fatura.pk)
    assert linha["account_name"] == linha["client_name"] == fatura.account.name


@pytest.mark.django_db
def test_o_processo_devolve_os_dois_nomes_com_o_mesmo_valor(admin_client: APIClient) -> None:
    """O mesmo par no processo — a rota legada `/processos/`, que também é da v1."""
    processo = ProcessFactory()

    resposta = admin_client.get(reverse("processo-detail", args=[processo.pk]))

    assert resposta.status_code == 200
    assert resposta.data["account_name"] == resposta.data["client_name"] == processo.account.name


@pytest.mark.django_db
def test_o_painel_de_cobranca_devolve_os_dois_nomes(admin_client: APIClient) -> None:
    """Dict cru: os dois pares são escritos à mão em `cobranca.painel()`, sem serializer."""
    fatura = InvoiceFactory(status=Invoice.Status.ISSUED)

    (linha,) = admin_client.get("/api/v1/cobranca/painel/").json()

    assert linha["account"] == linha["client"] == fatura.account_id
    assert linha["account_name"] == linha["client_name"] == fatura.account.name


@pytest.mark.django_db
def test_a_visao_compacta_da_entrega_devolve_os_dois_nomes(admin_client: APIClient) -> None:
    """O segundo dict cru — a visão da entrega no dashboard (FDD 042)."""
    projeto = ProjectFactory()

    (linha,) = admin_client.get(reverse("project-timeline-overview")).json()

    assert linha["project_id"] == projeto.pk
    assert linha["account_name"] == linha["client_name"] == projeto.engagement.account.name


@pytest.mark.django_db
def test_o_projeto_devolve_a_vertical_pelos_dois_nomes(admin_client: APIClient) -> None:
    """`client_vertical`/`client_vertical_name` — projeção, nunca coluna (FDD 026)."""
    vertical = Vertical.objects.create(name="Igrejas", slug="igrejas")
    conta = AccountFactory(vertical=vertical)
    projeto = ProjectFactory(engagement=EngagementFactory(account=conta))

    resposta = admin_client.get(reverse("project-detail", args=[projeto.pk]))

    assert resposta.status_code == 200
    assert resposta.data["account_vertical"] == resposta.data["client_vertical"] == vertical.pk
    assert resposta.data["account_vertical_name"] == "Igrejas"
    assert resposta.data["client_vertical_name"] == "Igrejas"


@pytest.mark.django_db
def test_a_visao_agregada_continua_envolvida_pela_chave_clients(
    admin_client: APIClient,
) -> None:
    """A chave que **troca** por versão: na v1 ela continua sendo `clients`, e só ela.

    Aqui a convivência não existe de propósito — duplicar o grid inteiro pagaria o corpo duas
    vezes —, então a prova da v1 é dupla: a legada presente e a canônica **ausente**.
    """
    conta = AccountFactory()

    resposta = admin_client.get(reverse("client-overview"))

    assert resposta.status_code == 200
    assert [linha["client_id"] for linha in resposta.data["clients"]] == [conta.pk]
    assert "accounts" not in resposta.data
