import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Meeting, Pendencia, User

from .factories import ProjectFactory, UserFactory


@pytest.mark.django_db
def test_delivery_creates_and_lists_meetings_filtered_by_project() -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    other = ProjectFactory()
    Meeting.objects.create(project=other, title="Outra", date=timezone.localdate())
    client = APIClient()
    client.force_authenticate(delivery)

    created = client.post(
        reverse("meeting-list"),
        {"project": project.pk, "title": "Kickoff", "date": str(timezone.localdate())},
        format="json",
    )
    assert created.status_code == 201

    listed = client.get(reverse("meeting-list"), {"project": project.pk}).json()
    rows = listed if isinstance(listed, list) else listed["results"]
    assert [row["title"] for row in rows] == ["Kickoff"]  # não traz a reunião do outro projeto


@pytest.mark.django_db
def test_sales_cannot_manage_pendencias() -> None:
    sales = UserFactory(role=User.Role.SALES)
    project = ProjectFactory()
    client = APIClient()
    client.force_authenticate(sales)
    resp = client.post(
        reverse("pendencia-list"),
        {"project": project.pk, "title": "Aprovar escopo"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_resolving_pendencia_sets_resolved_at() -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    pendencia = Pendencia.objects.create(project=project, title="Aprovar escopo", owner=delivery)
    assert pendencia.resolved_at is None
    client = APIClient()
    client.force_authenticate(delivery)

    resp = client.patch(
        reverse("pendencia-detail", args=[pendencia.pk]),
        {"status": "resolved"},
        format="json",
    )
    assert resp.status_code == 200
    pendencia.refresh_from_db()
    assert pendencia.status == Pendencia.Status.RESOLVED
    assert pendencia.resolved_at is not None


@pytest.mark.django_db
def test_pendencia_owner_is_set_to_request_user() -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    client = APIClient()
    client.force_authenticate(delivery)
    resp = client.post(
        reverse("pendencia-list"),
        {"project": project.pk, "title": "Definir alçada", "party": "client"},
        format="json",
    )
    assert resp.status_code == 201
    assert Pendencia.objects.get(pk=resp.json()["id"]).owner_id == delivery.pk
