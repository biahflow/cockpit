"""Regressão: aceitar convite com username já usado devolve 400, nunca 500 (FDD 017).

`AcceptInvitationSerializer` validava a senha mas não a unicidade do username, e a view
chamava `create_user` direto — o `IntegrityError` subia como 500. Além de ser um defeito,
o 500 distinguia "username existe" de "username livre" para quem não está autenticado.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Invitation, User
from apps.core.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _invitation(email: str) -> Invitation:
    return Invitation.objects.create(
        email=email,
        role=User.Role.DELIVERY,
        invited_by=UserFactory(),
        expires_at=timezone.now() + timedelta(days=7),
    )


def test_duplicate_username_is_a_field_error_not_a_crash() -> None:
    UserFactory(username="repetido")
    invitation = _invitation("nova@example.test")

    response = APIClient().post(reverse("accept-invitation"), {
        "token": str(invitation.token),
        "username": "repetido",
        "password": "Segura123!senha",
    }, format="json")

    assert response.status_code == 400
    assert "username" in response.data
    assert User.objects.filter(username="repetido").count() == 1
