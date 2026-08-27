"""API /github-projections/ e webhook /github/webhook/ (FDD 041).

Escopo de projeto, nega-por-padrão, fail-closed sem a flag, e a fronteira da ADR 0046: o corpo
nunca reescreve o estado de engenharia. O webhook autentica por HMAC e é idempotente.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import GithubDeliveryProjection, User

from .factories import (
    GithubDeliveryProjectionFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)

_ON = dict(
    GITHUB_DELIVERY_ENABLED=True,
    GITHUB_TOKEN="ghp_test",
    GITHUB_WEBHOOK_SECRET="whsec_test",
)

_PStatus = GithubDeliveryProjection.ProjectionStatus
_IState = GithubDeliveryProjection.IssueState


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def _map_payload(project_id: int, **overrides: object) -> dict:
    base: dict = {"project": project_id, "repository": "acme/repo", "issue_number": 7}
    base.update(overrides)
    return base


# --- Viewset -----------------------------------------------------------------


@pytest.mark.django_db
@override_settings(**_ON)
def test_admin_mapeia_projecao(api: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    api.force_authenticate(admin)
    created = api.post(
        reverse("githubdeliveryprojection-list"), _map_payload(project.id), format="json"
    )
    assert created.status_code == 201
    assert created.data["state"] == "pending"  # criada, nunca observada
    assert created.data["projection_status"] == _PStatus.PENDING
    assert created.data["issue_state"] == _IState.UNKNOWN


@pytest.mark.django_db
@override_settings(GITHUB_DELIVERY_ENABLED=False, GITHUB_TOKEN="x", GITHUB_WEBHOOK_SECRET="y")
def test_flag_off_create_503_sem_row(api: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    api.force_authenticate(admin)
    response = api.post(
        reverse("githubdeliveryprojection-list"), _map_payload(project.id), format="json"
    )
    assert response.status_code == 503
    assert GithubDeliveryProjection.objects.count() == 0


@pytest.mark.django_db
@override_settings(**_ON)
def test_corpo_nao_reescreve_estado_de_engenharia(api: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    projection = GithubDeliveryProjectionFactory()
    api.force_authenticate(admin)
    # Um PATCH tentando forjar o estado de engenharia é silenciosamente ignorado (campos read-only).
    patched = api.patch(
        reverse("githubdeliveryprojection-detail", args=[projection.id]),
        {"issue_state": "closed", "ci_state": "success", "projection_status": "current"},
        format="json",
    )
    assert patched.status_code == 200
    projection.refresh_from_db()
    assert projection.issue_state == _IState.UNKNOWN
    assert projection.projection_status == _PStatus.PENDING


@pytest.mark.django_db
@override_settings(**_ON)
def test_referencia_da_issue_nao_muda(api: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    projection = GithubDeliveryProjectionFactory(issue_number=7)
    api.force_authenticate(admin)
    patched = api.patch(
        reverse("githubdeliveryprojection-detail", args=[projection.id]),
        {"issue_number": 99},
        format="json",
    )
    assert patched.status_code == 400


@pytest.mark.django_db
@override_settings(**_ON)
def test_escopo_de_projeto_delivery_e_vendas(api: APIClient) -> None:
    project = ProjectFactory()
    delivery = UserFactory(role=User.Role.DELIVERY)
    ProjectMemberFactory(project=project, user=delivery)
    outsider = UserFactory(role=User.Role.DELIVERY, username="outsider")
    sales = UserFactory(role=User.Role.SALES)

    api.force_authenticate(delivery)
    created = api.post(
        reverse("githubdeliveryprojection-list"), _map_payload(project.id), format="json"
    )
    assert created.status_code == 201

    api.force_authenticate(outsider)
    assert api.get(reverse("githubdeliveryprojection-list")).data == []
    forbidden = api.post(
        reverse("githubdeliveryprojection-list"),
        _map_payload(project.id, issue_number=8),
        format="json",
    )
    assert forbidden.status_code == 403

    api.force_authenticate(sales)
    assert api.get(reverse("githubdeliveryprojection-list")).status_code == 403


@pytest.mark.django_db
@override_settings(**_ON)
def test_reconcile_action_indisponivel_marca_estado(
    api: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from apps.core import github_delivery

    admin = UserFactory(role=User.Role.ADMIN)
    projection = GithubDeliveryProjectionFactory()
    api.force_authenticate(admin)

    class BoomClient:
        def fetch_issue(self, repository: str, issue_number: int) -> object:
            from apps.core.github_issues import GitHubIssuesError

            raise GitHubIssuesError("GitHub request failed")

    monkeypatch.setattr(github_delivery, "GithubDeliveryApi", lambda: BoomClient())
    response = api.post(reverse("githubdeliveryprojection-reconcile", args=[projection.id]))
    assert response.status_code == 200
    assert response.data["projection_status"] == _PStatus.UNAVAILABLE


@pytest.mark.django_db
@override_settings(GITHUB_DELIVERY_ENABLED=False, GITHUB_TOKEN="x", GITHUB_WEBHOOK_SECRET="y")
def test_reconcile_flag_off_503(api: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    projection = GithubDeliveryProjectionFactory()
    api.force_authenticate(admin)
    response = api.post(reverse("githubdeliveryprojection-reconcile", args=[projection.id]))
    assert response.status_code == 503


# --- Webhook -----------------------------------------------------------------


def _post_webhook(
    api: APIClient, event: str, delivery: str, payload: dict, *, secret: str = "whsec_test"
) -> object:
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return api.post(
        reverse("github-webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=sig,
        HTTP_X_GITHUB_EVENT=event,
        HTTP_X_GITHUB_DELIVERY=delivery,
    )


@pytest.mark.django_db
@override_settings(**_ON)
def test_webhook_aplica_e_e_idempotente(api: APIClient) -> None:
    projection = GithubDeliveryProjectionFactory(repository="acme/repo", issue_number=7)
    payload = {
        "repository": {"full_name": "acme/repo"},
        "issue": {"number": 7, "state": "closed", "updated_at": "2026-08-27T10:00:00Z"},
    }
    first = _post_webhook(api, "issues", "delivery-1", payload)
    second = _post_webhook(api, "issues", "delivery-1", payload)
    assert first.status_code == 200
    assert first.data["outcome"] == "applied"
    assert second.data["outcome"] == "duplicate"
    projection.refresh_from_db()
    assert projection.issue_state == _IState.CLOSED
    assert projection.projection_status == _PStatus.CURRENT


@pytest.mark.django_db
@override_settings(**_ON)
def test_webhook_assinatura_invalida_401(api: APIClient) -> None:
    body = json.dumps({"repository": {"full_name": "acme/repo"}}).encode()
    response = api.post(
        reverse("github-webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256="sha256=deadbeef",
        HTTP_X_GITHUB_EVENT="issues",
        HTTP_X_GITHUB_DELIVERY="d",
    )
    assert response.status_code == 401


@pytest.mark.django_db
@override_settings(GITHUB_DELIVERY_ENABLED=False, GITHUB_TOKEN="x", GITHUB_WEBHOOK_SECRET="y")
def test_webhook_flag_off_503(api: APIClient) -> None:
    response = _post_webhook(api, "issues", "d", {"repository": {"full_name": "acme/repo"}})
    assert response.status_code == 503


@pytest.mark.django_db
@override_settings(**_ON)
def test_webhook_evento_sem_projecao_ignorado_200(api: APIClient) -> None:
    payload = {
        "repository": {"full_name": "acme/repo"},
        "issue": {"number": 404, "state": "open"},
    }
    response = _post_webhook(api, "issues", "d-x", payload)
    assert response.status_code == 200
    assert response.data["outcome"] == "ignored"
