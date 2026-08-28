"""Regressão: `inactive` é conta viva; só o arquivamento a tira da lista.

É a invariante da decisão C1 do DAP `dap-lifecycle-status-r1`, e é a que se perde primeiro num
refactor: os dois estados *parecem* a mesma coisa na tela — a conta some da carteira ativa — e a
tentação de tratar "inativo" como um jeito bonito de arquivar é grande.

Eles não são a mesma coisa. **Inativa é uma conta que existe**: ela continua no histórico, continua
somando no que já faturou, e volta a ser cliente quando uma oportunidade for ganha. Arquivada é uma
conta que saiu da base, e o `ArchiveModelViewSet` a esconde de toda listagem por `archived_at`.

Se alguém filtrar `lifecycle_status != "inactive"` no `get_queryset` — ou no agregador, que não
passa por queryset nenhum —, nada aqui fica vermelho sem este teste: a lista simplesmente encolhe,
e ninguém percebe que uma conta sumiu do inventário da casa.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Account, User
from apps.core.tests.factories import AccountFactory, UserFactory


@pytest.fixture
def api() -> APIClient:
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return client


@pytest.mark.django_db
def test_conta_inativa_continua_na_listagem(api: APIClient) -> None:
    inativa = AccountFactory(lifecycle_status=Account.LifecycleStatus.INACTIVE)

    resposta = api.get(reverse("client-list"))

    assert resposta.status_code == 200
    assert inativa.pk in {item["id"] for item in resposta.data}


@pytest.mark.django_db
def test_conta_inativa_continua_no_agregado(api: APIClient) -> None:
    """`/clients/overview/` é montado à mão e não passa pelo `get_queryset` do arquivamento."""
    inativa = AccountFactory(lifecycle_status=Account.LifecycleStatus.INACTIVE)

    resposta = api.get(reverse("client-overview"))

    assert resposta.status_code == 200
    assert inativa.pk in {item["client_id"] for item in resposta.data["clients"]}


@pytest.mark.django_db
def test_so_o_arquivamento_tira_a_conta_da_lista(api: APIClient) -> None:
    inativa = AccountFactory(lifecycle_status=Account.LifecycleStatus.INACTIVE)

    apagada = api.delete(reverse("client-detail", args=[inativa.pk]))

    assert apagada.status_code == 204
    ativas = api.get(reverse("client-list"))
    assert inativa.pk not in {item["id"] for item in ativas.data}
    arquivadas = api.get(reverse("client-list"), {"archived": "1"})
    assert inativa.pk in {item["id"] for item in arquivadas.data}
    # E o estado do ciclo de vida não muda com o arquivamento: são eixos diferentes.
    inativa.refresh_from_db()
    assert inativa.lifecycle_status == Account.LifecycleStatus.INACTIVE
    assert inativa.archived_at is not None


@pytest.mark.django_db
def test_o_filtro_por_estado_aceita_os_tres_valores(api: APIClient) -> None:
    prospect = AccountFactory(lifecycle_status=Account.LifecycleStatus.PROSPECT)
    cliente = AccountFactory(lifecycle_status=Account.LifecycleStatus.ACTIVE)
    inativa = AccountFactory(lifecycle_status=Account.LifecycleStatus.INACTIVE)

    def ids(**params: str) -> set[int]:
        return {item["client_id"] for item in api.get(reverse("client-overview"), params).data["clients"]}

    assert ids(lifecycle_status="prospect") == {prospect.pk}
    assert ids(lifecycle_status="active") == {cliente.pk}
    assert ids(lifecycle_status="inactive") == {inativa.pk}
    # Sem filtro, os três estados vivos aparecem juntos.
    assert ids() == {prospect.pk, cliente.pk, inativa.pk}


@pytest.mark.django_db
def test_de_cliente_para_inativa_e_permitido_e_o_caminho_de_volta_nao(api: APIClient) -> None:
    """`active → inactive` é o caminho que o estado existe para ter; `inactive → prospect` não.

    Rebaixar para prospect apagaria o fato de a conta já ter comprado, e o signal
    `_promote_account_on_won` só promove na transição — ele não corrigiria de volta.
    """
    conta = AccountFactory(lifecycle_status=Account.LifecycleStatus.ACTIVE)
    url = reverse("client-detail", args=[conta.pk])

    desativada = api.patch(url, {"lifecycle_status": "inactive"}, format="json")

    assert desativada.status_code == 200, desativada.data
    conta.refresh_from_db()
    assert conta.lifecycle_status == Account.LifecycleStatus.INACTIVE

    recuada = api.patch(url, {"lifecycle_status": "prospect"}, format="json")

    assert recuada.status_code == 400
    conta.refresh_from_db()
    assert conta.lifecycle_status == Account.LifecycleStatus.INACTIVE
