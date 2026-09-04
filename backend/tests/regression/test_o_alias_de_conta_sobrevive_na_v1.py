"""Regressão: as chaves `client` e `status` continuam na `/api/v1/`, na leitura e na escrita.

A fatia 2 da issue #67 renomeou `Client` para `Account`, os dez campos que apontavam para ela e o
`status` da conta para `lifecycle_status` (ADR 0052). O que a ADR **não** antecipou é a chave de
payload: rota e chave morrem na `/api/v2/`, não antes, porque um consumidor da v1 não tem como
saber que o nome mudou (`docs/ontology/aliases.md` §2c).

Sem este teste os aliases são linhas de serializer sem chamador dentro do repositório — a SPA já
escreve e lê `account`/`lifecycle_status` —, e a próxima pessoa que varrer `client` atrás do último
resquício do nome antigo vai removê-las achando que está pagando dívida. Estaria quebrando a
`/api/v1/` em silêncio: nada aqui dentro ficaria vermelho, e o erro apareceria no consumidor de
fora.

A **escrita** é o que nenhum outro teste cobre. `AliasesDaV1Mixin` normaliza a chave legada
antes da validação, e o empate resolve pela canônica — mesma regra de `apply-gate` desde a fatia 1
da issue.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Account, Contact, User
from apps.core.tests.factories import AccountFactory, UserFactory


@pytest.fixture
def sales_client() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.SALES))
    return client


@pytest.mark.django_db
def test_o_contato_devolve_as_duas_chaves_com_o_mesmo_valor(sales_client: APIClient) -> None:
    """`GET /contacts/` sai com `account` (canônica) **e** `client`, com o mesmo valor."""
    conta = AccountFactory()
    contato = Contact.objects.create(account=conta, first_name="Ana", last_name="Silva")

    resposta = sales_client.get(reverse("contact-list"))

    assert resposta.status_code == 200
    linha = next(item for item in resposta.data if item["id"] == contato.pk)
    assert linha["account"] == conta.pk
    assert linha["client"] == conta.pk


@pytest.mark.django_db
def test_o_contato_aceita_a_chave_antiga_no_corpo(sales_client: APIClient) -> None:
    """O alias de **escrita**: quem integrou com a v1 continua mandando `client`."""
    conta = AccountFactory()

    resposta = sales_client.post(
        reverse("contact-list"), {"client": conta.pk, "first_name": "Bruno"}, format="json"
    )

    assert resposta.status_code == 201, resposta.data
    assert Contact.objects.get(pk=resposta.data["id"]).account_id == conta.pk


@pytest.mark.django_db
def test_com_as_duas_chaves_no_corpo_a_canonica_vence(sales_client: APIClient) -> None:
    """Corpo com as duas é confusão do chamador; resolver pela nova não trava quem já migrou."""
    canonica = AccountFactory()
    legada = AccountFactory()

    resposta = sales_client.post(
        reverse("contact-list"),
        {"account": canonica.pk, "client": legada.pk, "first_name": "Clara"},
        format="json",
    )

    assert resposta.status_code == 201, resposta.data
    assert Contact.objects.get(pk=resposta.data["id"]).account_id == canonica.pk


@pytest.mark.django_db
def test_o_query_param_antigo_continua_filtrando(sales_client: APIClient) -> None:
    """`?client=` filtra igual a `?account=` — e não estoura `FieldError`.

    Em `QueryParamFilterMixin` o nome do param **é** o caminho do ORM, então o param antigo não
    ficaria "sem efeito" depois do renome: ele quebraria a requisição inteira.
    """
    conta = AccountFactory()
    dela = Contact.objects.create(account=conta, first_name="Dora")
    Contact.objects.create(account=AccountFactory(), first_name="Outro")

    legado = sales_client.get(reverse("contact-list"), {"client": conta.pk})
    canonico = sales_client.get(reverse("contact-list"), {"account": conta.pk})

    assert legado.status_code == 200
    assert {item["id"] for item in legado.data} == {dela.pk}
    assert {item["id"] for item in canonico.data} == {dela.pk}


@pytest.mark.django_db
def test_a_conta_devolve_lifecycle_status_e_status_iguais(sales_client: APIClient) -> None:
    """`GET /clients/` sai com as duas chaves de estado, e elas nunca divergem."""
    conta = AccountFactory(lifecycle_status=Account.LifecycleStatus.PROSPECT)

    resposta = sales_client.get(reverse("client-list"))

    assert resposta.status_code == 200
    linha = next(item for item in resposta.data if item["id"] == conta.pk)
    assert linha["lifecycle_status"] == "prospect"
    assert linha["status"] == "prospect"


@pytest.mark.django_db
def test_o_patch_pela_chave_antiga_grava_o_estado(sales_client: APIClient) -> None:
    """`PATCH {"status": "inactive"}` continua gravando — agora em `lifecycle_status`."""
    conta = AccountFactory(lifecycle_status=Account.LifecycleStatus.ACTIVE)

    resposta = sales_client.patch(
        reverse("client-detail", args=[conta.pk]), {"status": "inactive"}, format="json"
    )

    assert resposta.status_code == 200, resposta.data
    conta.refresh_from_db()
    assert conta.lifecycle_status == Account.LifecycleStatus.INACTIVE
    assert resposta.data["status"] == resposta.data["lifecycle_status"] == "inactive"


@pytest.mark.django_db
def test_a_visao_agregada_carrega_o_par_de_estado(sales_client: APIClient) -> None:
    """`/clients/overview/` é dicionário montado à mão, e por isso tem de ser afirmado à parte."""
    conta = AccountFactory(lifecycle_status=Account.LifecycleStatus.INACTIVE)

    resposta = sales_client.get(reverse("client-overview"))

    assert resposta.status_code == 200
    linha = next(item for item in resposta.data["clients"] if item["client_id"] == conta.pk)
    assert linha["lifecycle_status"] == linha["status"] == "inactive"


@pytest.mark.django_db
def test_a_rota_e_o_basename_nao_mudaram() -> None:
    """`/api/v1/clients/` e `reverse("client-…")` sobrevivem ao renome da classe.

    O `basename` virou explícito em `urls.py` justamente por isto: derivado do queryset ele
    passaria a ser `account`, e todo `reverse("client-…")` do repositório quebraria.
    """
    assert reverse("client-list") == "/api/v1/clients/"
    assert reverse("client-detail", args=[7]) == "/api/v1/clients/7/"

    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.SALES))
    assert api.get(reverse("client-list")).status_code == 200
