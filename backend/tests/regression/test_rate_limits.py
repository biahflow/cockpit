"""Regressão: as portas de entrada têm teto de requisições (FDD 017, ADR 0009).

O login era `AllowAny` sem throttle e o DRF não tinha limite padrão: força bruta de senha
era ilimitada. O mesmo valia para o aceite de convite (cria usuário sem autenticação) e para
o snapshot do portal, cujo Bearer virava um oráculo para adivinhar `PORTAL_READ_TOKEN`.

`override_settings(REST_FRAMEWORK=...)` **não** basta para mexer nas taxas: o DRF fixa
`SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES` como atributo de
classe no import, então `api_settings.reload()` troca o objeto do settings mas a classe segue
apontando para o dicionário antigo. Por isso os testes abaixo trocam o atributo da classe.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from apps.core.models import Invitation, User
from apps.core.tests.factories import ProjectFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def rate(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    def apply(**overrides: str) -> None:
        monkeypatch.setattr(
            SimpleRateThrottle,
            "THROTTLE_RATES",
            {**SimpleRateThrottle.THROTTLE_RATES, **overrides},
        )

    return apply


def test_login_is_throttled_after_repeated_failures(rate) -> None:  # type: ignore[no-untyped-def]
    rate(login="2/min")
    UserFactory(username="alvo", password="Segura123!senha")
    api = APIClient()
    payload = {"username": "alvo", "password": "errada"}

    assert api.post(reverse("login"), payload, format="json").status_code == 400
    assert api.post(reverse("login"), payload, format="json").status_code == 400
    assert api.post(reverse("login"), payload, format="json").status_code == 429


def test_legitimate_login_still_works_within_the_limit(rate) -> None:  # type: ignore[no-untyped-def]
    rate(login="10/min")
    UserFactory(username="pessoa", password="Segura123!senha")

    response = APIClient().post(
        reverse("login"), {"username": "pessoa", "password": "Segura123!senha"}, format="json"
    )

    assert response.status_code == 200


def test_invitation_accept_is_throttled(rate) -> None:  # type: ignore[no-untyped-def]
    rate(invitation_accept="1/min")
    invitation = Invitation.objects.create(
        email="nova@example.test",
        role=User.Role.DELIVERY,
        invited_by=UserFactory(),
        expires_at=timezone.now() + timedelta(days=7),
    )
    api = APIClient()
    body = {"token": str(invitation.token), "username": "nova", "password": "Segura123!senha"}

    assert api.post(reverse("accept-invitation"), body, format="json").status_code == 201
    assert api.post(reverse("accept-invitation"), body, format="json").status_code == 429


def test_portal_snapshot_is_not_an_unlimited_token_oracle(rate, settings) -> None:  # type: ignore[no-untyped-def]
    rate(portal_read="1/min")
    settings.PORTAL_READ_TOKEN = "segredo"
    project = ProjectFactory()
    api = APIClient()
    url = reverse("portal-project-snapshot", args=[project.id])
    headers = {"HTTP_AUTHORIZATION": "Bearer chute-errado"}

    assert api.get(url, **headers).status_code == 401
    assert api.get(url, **headers).status_code == 429


def test_the_whole_api_has_a_default_ceiling(rate) -> None:  # type: ignore[no-untyped-def]
    """`anon`/`user` são a rede de baixo: sem eles, só as rotas nomeadas tinham teto."""
    rate(user="1/min")
    api = APIClient()
    api.force_authenticate(UserFactory())

    assert api.get(reverse("client-list")).status_code == 200
    assert api.get(reverse("client-list")).status_code == 429


def test_csrf_endpoint_is_not_locked_behind_a_tight_scope() -> None:
    """O SPA busca o token antes de **cada** mutação; um escopo apertado ali travaria o app."""
    api = APIClient()

    for _ in range(5):
        assert api.get(reverse("csrf")).status_code == 200
