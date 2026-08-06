"""Regressão: `createsuperuser` dá um administrador de verdade (FDD 017, ADR 0010).

`createsuperuser` é o **primeiro comando** de toda instalação — está no `producao.md` e no roteiro
de teste. Ele não pede papel, então o usuário nasce com o default `delivery`.

O backend sempre soube resolver isso: `is_admin_role` é `role == ADMIN or is_superuser`, e é o que
autoriza em 14 lugares. Quem não sabia era a tela, que decidia tudo por `role` — e o resultado era
um portal capado, sem Leads, Indicadores, Jornada, Equipe nem Configurações, embora a API
respondesse 200 em todas elas. Pior: **não havia conserto pela interface**, porque `UserViewSet` é
read-only e papel só se define em convite.

Estes testes travam os dois lados: a autoridade que a API já dava, e o campo `is_admin` pelo qual
o SPA passou a enxergá-la.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import User
from apps.core.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def superusuario() -> User:
    """O que `createsuperuser` produz: superusuário, papel no default."""
    user = UserFactory(is_superuser=True, is_staff=True)
    user.role = User.Role.DELIVERY
    user.save(update_fields=["role"])
    return user


@pytest.fixture
def api(superusuario: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(superusuario)
    return client


def test_o_superusuario_recem_criado_se_declara_admin(api: APIClient) -> None:
    """É por este campo que o menu decide — sem ele o SPA não tinha como saber."""
    resposta = api.get(reverse("me"))

    assert resposta.status_code == 200
    assert resposta.data["role"] == User.Role.DELIVERY
    assert resposta.data["is_admin"] is True


@pytest.mark.parametrize("rota", ["lead-list", "user-list"])
def test_alcanca_as_rotas_que_o_menu_escondia(api: APIClient, rota: str) -> None:
    assert api.get(reverse(rota)).status_code == 200


def test_alcanca_indicadores(api: APIClient) -> None:
    """`/analytics/` alimenta a tela Indicadores, um dos cinco itens sumidos."""
    assert api.get(reverse("analytics")).status_code == 200


def test_monta_equipe_de_projeto(api: APIClient, superusuario: User) -> None:
    """O nó do problema: Equipe some do menu, e é a tela que dá acesso à Entrega.

    Sem esta correção a pessoa via um portal sem Equipe e sem meio de consertar o próprio papel —
    `UserViewSet` é read-only, então nem por lá.
    """
    from apps.core.tests.factories import ProjectFactory

    projeto = ProjectFactory()
    entrega = UserFactory(role=User.Role.DELIVERY)

    resposta = api.post(
        reverse("projectmember-list"), {"project": projeto.id, "user": entrega.id}
    )

    assert resposta.status_code == 201


def test_entrega_comum_continua_restrita() -> None:
    """O contraponto: a correção não pode transformar toda Entrega em admin."""
    client = APIClient()
    client.force_authenticate(UserFactory(role=User.Role.DELIVERY))

    me = client.get(reverse("me"))

    assert me.data["is_admin"] is False
    assert client.get(reverse("lead-list")).status_code == 403
