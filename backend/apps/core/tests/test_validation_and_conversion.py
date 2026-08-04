from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Milestone, PipelineStage, User

from .factories import ClientFactory, OpportunityFactory, ProjectFactory, UserFactory


@pytest.fixture
def sales_client() -> tuple[APIClient, User]:
    user = UserFactory(role=User.Role.SALES)
    client = APIClient()
    client.force_authenticate(user)
    return client, user


@pytest.mark.django_db
def test_opportunity_rejects_contact_from_different_client(sales_client: tuple[APIClient, User]) -> None:
    client, _ = sales_client
    first = ClientFactory()
    second = ClientFactory()
    contact = second.contacts.create(name="Contato externo")
    response = client.post(reverse("opportunity-list"), {
        "client": first.id,
        "contact": contact.id,
        "title": "Escopo",
        "estimated_value": "1000.00",
        "stage": PipelineStage.objects.filter(kind="open").first().id,
        "expected_close_date": str(timezone.localdate()),
    }, format="json")

    assert response.status_code == 400
    assert "contact" in response.data


@pytest.mark.django_db
def test_project_rejects_end_date_before_start() -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project_client = ClientFactory()
    client = APIClient()
    client.force_authenticate(delivery)

    response = client.post(reverse("project-list"), {
        "client": project_client.id,
        "name": "Datas inválidas",
        "start_date": "2026-08-10",
        "due_date": "2026-08-09",
    }, format="json")

    assert response.status_code == 400
    assert "due_date" in response.data


@pytest.mark.django_db
def test_task_rejects_milestone_from_another_project() -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    first_project = ProjectFactory()
    second_project = ProjectFactory()
    milestone = Milestone.objects.create(
        project=first_project, title="Marco", owner=delivery, due_date=timezone.localdate()
    )
    client = APIClient()
    client.force_authenticate(delivery)

    response = client.post(reverse("task-list"), {
        "project": second_project.id,
        "milestone": milestone.id,
        "title": "Tarefa inválida",
        "owner": delivery.id,
        "due_date": str(timezone.localdate()),
    }, format="json")

    assert response.status_code == 400
    assert "milestone" in response.data


@pytest.mark.django_db
@override_settings(MEDIA_ROOT="/tmp/biahflow-test-media")
def test_document_rejects_multiple_links_and_excessive_size() -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    first = ClientFactory(owner=admin)
    second = ClientFactory(owner=admin)
    client = APIClient()
    client.force_authenticate(admin)

    linked_twice = client.post(reverse("document-list"), {
        "client": first.id,
        "project": ProjectFactory(client=second).id,
        "file": SimpleUploadedFile("duplicado.pdf", b"ok"),
    })
    oversized = client.post(reverse("document-list"), {
        "client": first.id,
        "file": SimpleUploadedFile("grande.pdf", b"x" * (10 * 1024 * 1024 + 1)),
    })

    assert linked_twice.status_code == 400
    assert oversized.status_code == 400
    assert "file" in oversized.data


@pytest.mark.django_db
def test_conversion_rejects_delivery_foreign_client_and_invalid_dates() -> None:
    sales = UserFactory(role=User.Role.SALES)
    opportunity = OpportunityFactory(stage=PipelineStage.objects.get(kind="won"), owner=sales)
    endpoint = reverse("opportunity-convert-to-project", args=[opportunity.id])

    delivery_client = APIClient()
    delivery_client.force_authenticate(UserFactory(role=User.Role.DELIVERY))
    forbidden = delivery_client.post(endpoint, {}, format="json")

    sales_client = APIClient()
    sales_client.force_authenticate(sales)
    foreign = sales_client.post(endpoint, {
        "client": ClientFactory().id,
        "name": "Cliente incorreto",
        "start_date": "2026-08-01",
        "due_date": "2026-08-10",
    }, format="json")
    invalid_dates = sales_client.post(endpoint, {
        "client": opportunity.client_id,
        "name": "Datas inválidas",
        "start_date": "2026-08-10",
        "due_date": "2026-08-01",
    }, format="json")

    assert forbidden.status_code == 403
    assert foreign.status_code == 400
    assert invalid_dates.status_code == 400


@pytest.mark.django_db
def test_conversion_returns_conflict_without_partial_project_on_integrity_error() -> None:
    sales = UserFactory(role=User.Role.SALES)
    opportunity = OpportunityFactory(stage=PipelineStage.objects.get(kind="won"), owner=sales)
    client = APIClient()
    client.force_authenticate(sales)
    payload = {
        "client": opportunity.client_id,
        "name": "Projeto",
        "start_date": str(timezone.localdate()),
        "due_date": str(timezone.localdate() + timedelta(days=10)),
    }

    with patch("apps.core.views.ProjectSerializer.save", side_effect=IntegrityError):
        response = client.post(
            reverse("opportunity-convert-to-project", args=[opportunity.id]), payload, format="json"
        )

    assert response.status_code == 409
    assert not hasattr(opportunity, "project")
