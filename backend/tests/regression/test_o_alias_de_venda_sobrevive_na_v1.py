"""Regressão: a chave `opportunity` continua na `/api/v1/`, na leitura, na escrita e no filtro.

A issue #67 renomeou `Opportunity` para `CommercialOpportunity` e, com ela, os cinco campos que
apontavam para a venda (ADR 0052). O que a ADR **não** antecipou é a chave de payload: rota e
chave morrem na `/api/v2/`, não antes, porque um consumidor da v1 não tem como saber que o nome
mudou (`docs/ontology/aliases.md` §2c).

Sem este teste o alias é uma linha de serializer sem chamador dentro do repositório — a SPA já
escreve e lê `commercial_opportunity` —, e a próxima pessoa que varrer `opportunity` atrás do
último resquício do nome antigo vai remover a chave achando que está pagando dívida. Estaria
quebrando a `/api/v1/` em silêncio: nada aqui dentro ficaria vermelho, e o erro apareceria no
consumidor de fora.

A **escrita** é o que nenhum outro teste cobre. `AliasesDaV1Mixin` normaliza a chave legada
antes da validação, e o empate resolve pela canônica — mesma regra de `apply-gate` desde a fatia 1
da issue.

O **query param** entra pelo mesmo argumento e por um motivo a mais: em `QueryParamFilterMixin` o
nome do param **é** o caminho do ORM, então `?opportunity=` não ficaria "sem efeito" depois do
renome — estouraria `FieldError`.
"""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Activity, Document, User
from apps.core.tests.factories import (
    ActivityFactory,
    CommercialOpportunityFactory,
    UserFactory,
)


@pytest.fixture
def sales_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.SALES))
    return client


def _arquivo() -> SimpleUploadedFile:
    return SimpleUploadedFile("proposta.pdf", b"valor e margem", content_type="application/pdf")


@pytest.mark.django_db
def test_o_documento_devolve_as_duas_chaves_com_o_mesmo_valor(sales_client: APIClient) -> None:
    """`GET /documents/` sai com `commercial_opportunity` (canônica) **e** `opportunity`."""
    venda = CommercialOpportunityFactory()
    documento = Document.objects.create(
        commercial_opportunity=venda,
        original_name="proposta.pdf",
        file=_arquivo(),
        uploaded_by=UserFactory(),
    )

    resposta = sales_client.get(reverse("document-list"))

    assert resposta.status_code == 200
    linha = next(item for item in resposta.data if item["id"] == documento.pk)
    assert linha["commercial_opportunity"] == venda.pk
    assert linha["opportunity"] == venda.pk


@pytest.mark.django_db
def test_o_documento_aceita_a_chave_antiga_no_corpo(sales_client: APIClient) -> None:
    """O alias de **escrita**: quem integrou com a v1 continua mandando `opportunity`."""
    venda = CommercialOpportunityFactory()

    resposta = sales_client.post(
        reverse("document-list"), {"opportunity": venda.pk, "file": _arquivo()}
    )

    assert resposta.status_code == 201, resposta.data
    documento = Document.objects.get(pk=resposta.data["id"])
    assert documento.commercial_opportunity_id == venda.pk


@pytest.mark.django_db
def test_com_as_duas_chaves_no_corpo_a_canonica_vence(sales_client: APIClient) -> None:
    """Corpo com as duas é confusão do chamador; resolver pela nova não trava quem já migrou."""
    canonica = CommercialOpportunityFactory()
    legada = CommercialOpportunityFactory()

    resposta = sales_client.post(
        reverse("document-list"),
        {
            "commercial_opportunity": canonica.pk,
            "opportunity": legada.pk,
            "file": _arquivo(),
        },
    )

    assert resposta.status_code == 201, resposta.data
    documento = Document.objects.get(pk=resposta.data["id"])
    assert documento.commercial_opportunity_id == canonica.pk


@pytest.mark.django_db
def test_a_atividade_carrega_o_mesmo_par(sales_client: APIClient) -> None:
    """A interação comercial é o outro escritor da chave, e é JSON em vez de multipart."""
    venda = CommercialOpportunityFactory()

    criada = sales_client.post(
        reverse("activity-list"),
        {
            "account": venda.account_id,
            "opportunity": venda.pk,
            "kind": Activity.Kind.MEETING,
            "happened_on": "2026-08-28",
            "summary": "Reunião pela chave antiga",
        },
        format="json",
    )

    assert criada.status_code == 201, criada.data
    assert criada.data["commercial_opportunity"] == venda.pk
    assert criada.data["opportunity"] == venda.pk
    assert Activity.objects.get(pk=criada.data["id"]).commercial_opportunity_id == venda.pk


@pytest.mark.django_db
def test_o_query_param_antigo_continua_filtrando(sales_client: APIClient) -> None:
    """`?opportunity=` filtra igual a `?commercial_opportunity=` — e não estoura `FieldError`."""
    venda = CommercialOpportunityFactory()
    da_venda = ActivityFactory(account=venda.account, commercial_opportunity=venda)
    ActivityFactory(account=venda.account)

    legado = sales_client.get(reverse("activity-list"), {"opportunity": venda.pk})
    canonico = sales_client.get(reverse("activity-list"), {"commercial_opportunity": venda.pk})

    assert legado.status_code == 200
    assert {item["id"] for item in legado.data} == {da_venda.pk}
    assert {item["id"] for item in canonico.data} == {da_venda.pk}


@pytest.mark.django_db
def test_a_rota_e_o_basename_nao_mudaram() -> None:
    """`/api/v1/opportunities/` e `reverse("opportunity-…")` sobrevivem ao renome da classe.

    O `basename` virou explícito em `urls.py` justamente por isto: derivado do queryset ele
    passaria a ser `commercialopportunity`.
    """
    assert reverse("opportunity-list") == "/api/v1/opportunities/"
    assert reverse("opportunity-detail", args=[7]) == "/api/v1/opportunities/7/"

    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.SALES))
    assert api.get(reverse("opportunity-list")).status_code == 200
