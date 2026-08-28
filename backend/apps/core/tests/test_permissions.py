from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import PipelineStage, Project, User

from .factories import (
    ClientFactory,
    OpportunityFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_anonymous_user_cannot_access_internal_crm(client: APIClient) -> None:
    assert client.get(reverse("client-list")).status_code == 403
    assert client.get(reverse("dashboard")).status_code == 403


@pytest.mark.django_db
def test_sales_operates_crm_but_cannot_create_or_edit_projects(client: APIClient) -> None:
    sales = UserFactory(role=User.Role.SALES)
    project = ProjectFactory()
    client.force_authenticate(sales)

    created_client = client.post(reverse("client-list"), {"name": "Novo cliente"}, format="json")
    rejected_project = client.post(
        reverse("project-list"),
        {
            "client": project.client_id,
            "name": "Projeto indevido",
            "start_date": str(timezone.localdate()),
            "due_date": str(timezone.localdate() + timedelta(days=10)),
        },
        format="json",
    )
    rejected_update = client.patch(
        reverse("project-detail", args=[project.id]), {"name": "Alteração indevida"}, format="json"
    )

    assert created_client.status_code == 201
    assert rejected_project.status_code == 403
    assert rejected_update.status_code == 403


@pytest.mark.django_db
def test_delivery_only_sees_won_opportunities_and_cannot_edit_crm(client: APIClient) -> None:
    """Ganha **e** convertida num projeto da equipe (RFC 0003) — antes bastava estar ganha."""
    delivery = UserFactory(role=User.Role.DELIVERY)
    won = OpportunityFactory(stage=PipelineStage.objects.get(kind=PipelineStage.Kind.WON))
    project = ProjectFactory(originating_commercial_opportunity=won, client=won.client)
    ProjectMemberFactory(project=project, user=delivery)
    OpportunityFactory(stage=PipelineStage.objects.get(kind=PipelineStage.Kind.WON))
    OpportunityFactory()
    client.force_authenticate(delivery)

    listed = client.get(reverse("opportunity-list"))
    rejected_client = client.post(reverse("client-list"), {"name": "Sem permissão"}, format="json")
    rejected_update = client.patch(
        reverse("opportunity-detail", args=[won.id]), {"title": "Alteração"}, format="json"
    )

    assert listed.status_code == 200
    assert [item["id"] for item in listed.data] == [won.id]
    assert rejected_client.status_code == 403
    assert rejected_update.status_code == 403


@pytest.mark.django_db
def test_delivery_can_manage_project_execution(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)
    client.force_authenticate(delivery)

    response = client.patch(
        reverse("project-detail", args=[project.id]), {"status": Project.Status.ACTIVE}, format="json"
    )

    assert response.status_code == 200
    assert response.data["status"] == Project.Status.ACTIVE


@pytest.mark.django_db
def test_only_administrators_manage_pipeline_and_invitations(client: APIClient) -> None:
    sales = UserFactory(role=User.Role.SALES)
    client.force_authenticate(sales)

    stage_response = client.get(reverse("pipelinestage-list"))
    invite_response = client.post(
        reverse("invitation"), {"email": "x@example.test", "role": "delivery"}, format="json"
    )

    assert stage_response.status_code == 403
    assert invite_response.status_code == 403


@pytest.mark.django_db
def test_delete_archives_client_without_losing_record(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    record = ClientFactory(owner=admin)
    client.force_authenticate(admin)

    deleted = client.delete(reverse("client-detail", args=[record.id]))
    listed = client.get(reverse("client-list"))

    assert deleted.status_code == 204
    assert list(listed.data) == []
    assert record.__class__.objects.get(id=record.id).archived_at is not None
