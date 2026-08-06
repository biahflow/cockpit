from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Invitation, User

from .factories import UserFactory


@pytest.mark.django_db
def test_csrf_login_me_and_logout_round_trip() -> None:
    user = UserFactory(role=User.Role.SALES, password="SenhaSegura123!")
    client = APIClient()

    csrf = client.get(reverse("csrf"))
    login = client.post(reverse("login"), {"username": user.username, "password": "SenhaSegura123!"})
    current_user = client.get(reverse("me"))
    logout = client.post(reverse("logout"))
    after_logout = client.get(reverse("me"))

    assert csrf.status_code == 200
    assert csrf.data["csrfToken"]
    assert login.status_code == 200
    assert current_user.data["id"] == user.id
    assert logout.status_code == 204
    assert after_logout.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "superuser", "esperado"),
    [
        # O caso que motivou o campo: `createsuperuser` deixa o papel no default `delivery`, e sem
        # `is_admin` o SPA tratava essa pessoa como Entrega — portal capado, sem Equipe nem
        # Configurações — enquanto a API já a autorizava em tudo (FDD 017, ADR 0010).
        (User.Role.DELIVERY, True, True),
        (User.Role.DELIVERY, False, False),
        (User.Role.ADMIN, False, True),
        (User.Role.SALES, False, False),
    ],
)
def test_me_expoe_is_admin_com_o_mesmo_criterio_da_api(
    role: str, superuser: bool, esperado: bool
) -> None:
    user = UserFactory(role=role, is_superuser=superuser, password="SenhaSegura123!")
    client = APIClient()
    client.force_authenticate(user)

    resposta = client.get(reverse("me"))

    assert resposta.status_code == 200
    assert resposta.data["is_admin"] is esperado
    # O SPA consome o predicado; não o reconstrói. Se estes dois divergirem, a tela volta a
    # discordar da API — que é o defeito inteiro.
    assert resposta.data["is_admin"] == user.is_admin_role


@pytest.mark.django_db
def test_is_admin_e_somente_leitura() -> None:
    """Nenhum endpoint de escrita usa o `UserSerializer` hoje; o campo já nasce blindado."""
    from apps.core.serializers import UserSerializer

    assert UserSerializer().fields["is_admin"].read_only


@pytest.mark.django_db
def test_login_rejects_invalid_credentials() -> None:
    client = APIClient()
    response = client.post(reverse("login"), {"username": "inexistente", "password": "errada"})
    assert response.status_code == 400


@pytest.mark.django_db
def test_invitation_requires_admin_and_rejects_duplicate_email() -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    sales = UserFactory(role=User.Role.SALES)
    client = APIClient()
    client.force_authenticate(sales)
    rejected = client.post(reverse("invitation"), {"email": "team@example.test", "role": "delivery"})

    client.force_authenticate(admin)
    created = client.post(reverse("invitation"), {"email": "team@example.test", "role": "delivery"})
    duplicated = client.post(reverse("invitation"), {"email": "team@example.test", "role": "delivery"})

    assert rejected.status_code == 403
    assert created.status_code == 201
    assert duplicated.status_code == 400


@pytest.mark.django_db
def test_invitation_cannot_be_accepted_after_expiry_or_second_use() -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    expired = Invitation.objects.create(
        email="expired@example.test",
        role=User.Role.DELIVERY,
        invited_by=admin,
        expires_at=timezone.now() - timedelta(seconds=1),
    )
    valid = Invitation.objects.create(
        email="valid@example.test",
        role=User.Role.DELIVERY,
        invited_by=admin,
        expires_at=timezone.now() + timedelta(days=1),
    )
    client = APIClient()

    expired_response = client.post(reverse("accept-invitation"), {
        "token": str(expired.token), "username": "expired", "password": "SenhaSegura123!"
    })
    accepted = client.post(reverse("accept-invitation"), {
        "token": str(valid.token), "username": "valid", "password": "SenhaSegura123!"
    })
    repeated = client.post(reverse("accept-invitation"), {
        "token": str(valid.token), "username": "valid-again", "password": "SenhaSegura123!"
    })

    assert expired_response.status_code == 400
    assert accepted.status_code == 201
    assert repeated.status_code == 400


@pytest.mark.django_db
def test_invitation_rejects_weak_password() -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    invitation = Invitation.objects.create(
        email="weak@example.test",
        role=User.Role.DELIVERY,
        invited_by=admin,
        expires_at=timezone.now() + timedelta(days=1),
    )

    response = APIClient().post(reverse("accept-invitation"), {
        "token": str(invitation.token), "username": "weak", "password": "curta"
    })

    assert response.status_code == 400
