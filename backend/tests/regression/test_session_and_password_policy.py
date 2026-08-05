"""Regressão: sessão expira e senha fraca é recusada no aceite de convite (FDD 019).

Os dois eram itens que a FDD 017 adiou. A sessão não tinha prazo nenhum — o cookie durava as duas
semanas do default do Django e nada expirava por inatividade. E dos quatro validadores de senha só
dois estavam ligados: senha numérica passava, e senha parecida com o nome de usuário passava.

O `UserAttributeSimilarityValidator` merece atenção: ele **desiste em silêncio** sem um `user`. O
serializer chamava `validate_password(value)` sem usuário, então ligá-lo no settings sozinho não
mudaria nada. A validação passou a ser de objeto, com um `User` instanciado e não salvo.
"""

from datetime import timedelta

import pytest
from django.contrib.sessions.models import Session
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Invitation, User
from apps.core.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

SENHA_BOA = "Segura123!senha"


def _convite() -> Invitation:
    return Invitation.objects.create(
        email="nova@exemplo.com",
        role=User.Role.DELIVERY,
        invited_by=UserFactory(role=User.Role.ADMIN),
        expires_at=timezone.now() + timedelta(days=2),
    )


@override_settings(SESSION_COOKIE_AGE=3600)
def test_o_cookie_de_sessao_carrega_o_prazo_configurado() -> None:
    user = UserFactory(role=User.Role.SALES, password=SENHA_BOA)
    client = APIClient()

    resposta = client.post(
        reverse("login"), {"username": user.username, "password": SENHA_BOA}, format="json"
    )

    assert resposta.status_code == 200
    assert client.cookies["sessionid"]["max-age"] == 3600


def test_sessao_expirada_deixa_de_autenticar() -> None:
    user = UserFactory(role=User.Role.SALES, password=SENHA_BOA)
    client = APIClient()
    client.post(reverse("login"), {"username": user.username, "password": SENHA_BOA}, format="json")
    assert client.get(reverse("me")).status_code == 200

    # Envelhece a sessão no banco, que é onde ela mora (não no cache — ver ADR 0011).
    Session.objects.update(expire_date=timezone.now() - timedelta(seconds=1))

    assert client.get(reverse("me")).status_code == 403


@pytest.mark.parametrize(
    "senha",
    [
        "98765432101",  # só dígitos
        "pessoa-nova-1",  # parecida com o nome de usuário
        "curta",  # curta demais
    ],
)
def test_aceite_de_convite_recusa_senha_fraca(senha: str) -> None:
    convite = _convite()

    resposta = APIClient().post(
        reverse("accept-invitation"),
        {"token": str(convite.token), "username": "pessoa-nova", "password": senha},
        format="json",
    )

    # 400 com erro no campo, no padrão que a FDD 017 estabeleceu (nunca 500).
    assert resposta.status_code == 400
    assert "password" in resposta.data
    assert not User.objects.filter(username="pessoa-nova").exists()


def test_aceite_de_convite_aceita_senha_forte() -> None:
    convite = _convite()

    resposta = APIClient().post(
        reverse("accept-invitation"),
        {"token": str(convite.token), "username": "pessoa-nova", "password": SENHA_BOA},
        format="json",
    )

    assert resposta.status_code == 201
    assert User.objects.filter(username="pessoa-nova").exists()
