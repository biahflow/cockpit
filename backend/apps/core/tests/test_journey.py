"""Testes da Jornada de Transformação (FDD 011): materialização, avanço e permissões."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import (
    JourneyPhase,
    ProjectDeliverable,
    ProjectPhase,
    User,
)

from .factories import ProjectFactory, UserFactory


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_project_creation_materializes_the_journey() -> None:
    """Ao nascer, um projeto ganha uma cópia do template: 1ª fase ativa, resto bloqueado."""
    project = ProjectFactory()

    phases = list(project.phases.order_by("phase__position"))
    assert len(phases) == JourneyPhase.objects.count() > 0
    assert phases[0].status == ProjectPhase.Status.ACTIVE
    assert phases[0].started_at is not None
    assert all(p.status == ProjectPhase.Status.LOCKED for p in phases[1:])
    # entregáveis do template foram copiados para a instância do projeto
    assert phases[0].deliverables.exists()
    assert project.current_phase == phases[0]


@pytest.mark.django_db
def test_advance_phase_completes_active_and_activates_next(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    client.force_authenticate(delivery)

    response = client.post(reverse("project-advance-phase", args=[project.id]))

    assert response.status_code == 200
    ordered = list(project.phases.order_by("phase__position"))
    assert ordered[0].status == ProjectPhase.Status.DONE
    assert ordered[0].completed_at is not None
    assert ordered[1].status == ProjectPhase.Status.ACTIVE
    assert ordered[1].started_at is not None


@pytest.mark.django_db
def test_advance_phase_past_last_phase_is_graceful(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    client.force_authenticate(admin)

    total = JourneyPhase.objects.count()
    for _ in range(total + 1):  # avança além da última fase
        response = client.post(reverse("project-advance-phase", args=[project.id]))
        assert response.status_code == 200

    assert project.current_phase is None
    assert project.phases.filter(status=ProjectPhase.Status.DONE).count() == total


@pytest.mark.django_db
def test_mark_deliverable_delivered_sets_timestamp(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory()
    deliverable = ProjectDeliverable.objects.filter(project_phase__project=project).first()
    assert deliverable is not None
    client.force_authenticate(delivery)

    response = client.patch(
        reverse("projectdeliverable-detail", args=[deliverable.id]),
        {"status": ProjectDeliverable.Status.DELIVERED},
        format="json",
    )

    assert response.status_code == 200
    deliverable.refresh_from_db()
    assert deliverable.status == ProjectDeliverable.Status.DELIVERED
    assert deliverable.delivered_at is not None


@pytest.mark.django_db
def test_project_phases_are_lazily_materialized_when_missing(client: APIClient) -> None:
    admin = UserFactory(role=User.Role.ADMIN)
    project = ProjectFactory()
    project.phases.all().delete()  # simula projeto antigo, anterior à jornada
    client.force_authenticate(admin)

    response = client.get(reverse("projectphase-list"), {"project": project.id})

    assert response.status_code == 200
    assert len(response.data) == JourneyPhase.objects.count()
    assert project.phases.filter(status=ProjectPhase.Status.ACTIVE).count() == 1


@pytest.mark.django_db
def test_delivery_reads_journey_but_sales_cannot_advance(client: APIClient) -> None:
    sales = UserFactory(role=User.Role.SALES)
    project = ProjectFactory()
    client.force_authenticate(sales)

    listed = client.get(reverse("projectphase-list"), {"project": project.id})
    advanced = client.post(reverse("project-advance-phase", args=[project.id]))
    deliverable = ProjectDeliverable.objects.filter(project_phase__project=project).first()
    marked = client.patch(
        reverse("projectdeliverable-detail", args=[deliverable.id]),
        {"status": ProjectDeliverable.Status.DELIVERED},
        format="json",
    )

    assert listed.status_code == 200  # vendas lê a jornada do projeto
    assert advanced.status_code == 403  # mas não avança fases
    assert marked.status_code == 403  # nem marca entregáveis


@pytest.mark.django_db
def test_journey_template_is_admin_only(client: APIClient) -> None:
    delivery = UserFactory(role=User.Role.DELIVERY)
    admin = UserFactory(role=User.Role.ADMIN)

    client.force_authenticate(delivery)
    assert client.get(reverse("journeyphase-list")).status_code == 403

    client.force_authenticate(admin)
    admin_list = client.get(reverse("journeyphase-list"))
    assert admin_list.status_code == 200
    assert len(admin_list.data) == JourneyPhase.objects.count()
