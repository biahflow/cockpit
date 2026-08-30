"""Regressão: Entrega não se auto-concede acesso a projeto alheio (RFC 0003, FDD 018).

O recorte de leitura só vale se a escrita for fechada junto. Antes, `POST /milestones/` ou
`/tasks/` apontando para qualquer projeto tornava a pessoa dona do item — e, pelo critério
antigo, "atuante" naquele projeto. A restrição de leitura seria contornável em uma requisição.
É o mesmo furo que o `Artifact` tinha e que o commit 0361819 fechou só para ele.

O segundo caminho, mais silencioso: **mover** um objeto próprio para um projeto alheio por
PATCH. Não concede acesso, mas leva dado para fora do alcance de quem deveria vê-lo.
"""

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Milestone, Task, User
from apps.core.tests.factories import ProjectFactory, ProjectMemberFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def delivery() -> User:
    return UserFactory(role=User.Role.DELIVERY)


@pytest.fixture
def api(delivery: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(delivery)
    return client


def _payload(route: str, project_id: int) -> dict[str, object]:
    today = str(timezone.localdate())
    return {
        "milestone": {"project": project_id, "title": "Marco", "due_date": today},
        "task": {"project": project_id, "title": "Tarefa", "due_date": today},
        "meeting": {"project": project_id, "title": "Reunião", "date": today},
        "pendencia": {"project": project_id, "title": "Pendência"},
        "digitalemployee": {"project": project_id, "name": "Bia"},
        "artifact": {"project": project_id, "kind": "discovery", "title": "Discovery"},
    }[route]


@pytest.mark.parametrize(
    "route", ["milestone", "task", "meeting", "pendencia", "digitalemployee", "artifact"]
)
def test_delivery_cannot_create_anything_in_someone_elses_project(
    api: APIClient, route: str
) -> None:
    project = ProjectFactory()

    response = api.post(reverse(f"{route}-list"), _payload(route, project.id), format="json")

    assert response.status_code == 403
    assert not project.members.filter(archived_at__isnull=True).exclude(
        user=project.owner
    ).exists()


def test_delivery_creates_inside_its_own_project(api: APIClient, delivery: User) -> None:
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)

    response = api.post(
        reverse("task-list"), _payload("task", project.id), format="json"
    )

    assert response.status_code == 201


def test_delivery_cannot_move_an_item_into_someone_elses_project(
    api: APIClient, delivery: User
) -> None:
    mine = ProjectFactory()
    ProjectMemberFactory(project=mine, user=delivery)
    theirs = ProjectFactory()
    task = Task.objects.create(
        project=mine, title="Tarefa", owner=delivery, due_date=mine.due_date
    )

    response = api.patch(
        reverse("task-detail", args=[task.id]), {"project": theirs.id}, format="json"
    )

    assert response.status_code == 403
    task.refresh_from_db()
    assert task.project_id == mine.id


def test_delivery_cannot_create_or_delete_projects(api: APIClient, delivery: User) -> None:
    """Projeto nasce da conversão comercial ou pela mão do admin — não da Entrega."""
    existing = ProjectFactory()
    ProjectMemberFactory(project=existing, user=delivery)

    created = api.post(reverse("project-list"), {
        "engagement": existing.engagement_id,
        "name": "Projeto próprio",
        "start_date": str(existing.start_date),
        "due_date": str(existing.due_date),
    }, format="json")
    deleted = api.delete(reverse("project-detail", args=[existing.id]))

    assert created.status_code == 403
    assert deleted.status_code == 403


def test_delivery_still_edits_its_own_project(api: APIClient, delivery: User) -> None:
    project = ProjectFactory()
    ProjectMemberFactory(project=project, user=delivery)

    response = api.patch(
        reverse("project-detail", args=[project.id]), {"status": "active"}, format="json"
    )

    assert response.status_code == 200


def test_milestone_from_another_project_is_not_reachable(api: APIClient, delivery: User) -> None:
    """Fecha o caminho indireto: apontar a tarefa para um marco de projeto alheio."""
    mine = ProjectFactory()
    ProjectMemberFactory(project=mine, user=delivery)
    theirs = ProjectFactory()
    foreign = Milestone.objects.create(
        project=theirs, title="Marco alheio", owner=theirs.owner, due_date=theirs.due_date
    )

    response = api.post(reverse("task-list"), {
        "project": mine.id, "title": "Tarefa", "due_date": str(mine.due_date),
        "milestone": foreign.id,
    }, format="json")

    assert response.status_code == 400
