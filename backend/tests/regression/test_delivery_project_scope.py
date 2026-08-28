"""Regressão: Entrega só enxerga os projetos de que participa (RFC 0003, ADR 0010, FDD 018).

Fecha a assimetria que a ADR 0009 registrou como aceita e pendente de RFC: a revisão de
segurança restringiu os **documentos** de Entrega aos projetos em que atua, mas a pessoa
continuava vendo todos os projetos e tudo o que pende deles — marcos, tarefas, reuniões,
pendências, fases, entregáveis, funcionários digitais e artefatos.

O critério de pertencimento agora é um só: `ProjectMember` ativo.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import (
    Artifact,
    DigitalEmployee,
    Meeting,
    Milestone,
    Pendencia,
    Task,
    User,
)
from apps.core.tests.factories import (
    ArtifactFactory,
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def delivery() -> User:
    return UserFactory(role=User.Role.DELIVERY)


@pytest.fixture
def api(delivery: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(delivery)
    return client


def _populate(project):  # type: ignore[no-untyped-def]
    """Um de cada recurso pendurado no projeto, para varrer a superfície inteira."""
    owner = project.owner
    milestone = Milestone.objects.create(
        project=project, title="Marco", owner=owner, due_date=project.due_date
    )
    return {
        "milestone": milestone,
        "task": Task.objects.create(
            project=project, title="Tarefa", owner=owner,
            due_date=project.due_date, milestone=milestone,
        ),
        "meeting": Meeting.objects.create(
            project=project, title="Reunião", date=project.start_date
        ),
        "pendencia": Pendencia.objects.create(project=project, title="Pendência"),
        "digitalemployee": DigitalEmployee.objects.create(project=project, name="Bia"),
        "artifact": ArtifactFactory(project=project, commercial_opportunity=None, kind=Artifact.Kind.DISCOVERY),
    }


# (nome da rota, chave em `_populate`) — cobre a superfície pendurada no projeto
SCOPED = [
    ("milestone", "milestone"),
    ("task", "task"),
    ("meeting", "meeting"),
    ("pendencia", "pendencia"),
    ("digitalemployee", "digitalemployee"),
    ("artifact", "artifact"),
]


def test_delivery_outside_the_team_sees_no_project(api: APIClient) -> None:
    ProjectFactory()

    assert api.get(reverse("project-list")).data == []


def test_delivery_outside_the_team_gets_404_on_the_project(api: APIClient) -> None:
    project = ProjectFactory()

    assert api.get(reverse("project-detail", args=[project.id])).status_code == 404


@pytest.mark.parametrize(("route", "key"), SCOPED)
def test_delivery_outside_the_team_sees_nothing_hanging_off_the_project(
    api: APIClient, route: str, key: str
) -> None:
    records = _populate(ProjectFactory())

    assert api.get(reverse(f"{route}-list")).data == []
    assert api.get(reverse(f"{route}-detail", args=[records[key].id])).status_code == 404


@pytest.mark.parametrize("action", ["risk", "health", "assistant", "summary", "next-steps"])
def test_detail_actions_are_scoped_by_the_queryset(
    api: APIClient, action: str
) -> None:
    """As actions herdam o recorte por `get_object()` — travado aqui para não reabrir em silêncio."""
    project = ProjectFactory()
    url = reverse(f"project-{action}", args=[project.id])
    method = api.get if action in {"risk", "health"} else api.post

    assert method(url).status_code == 404


def test_member_sees_the_project_and_only_it(api: APIClient, delivery: User) -> None:
    mine = ProjectFactory()
    ProjectMemberFactory(project=mine, user=delivery)
    ProjectFactory()  # de outra equipe

    listed = api.get(reverse("project-list"))

    assert [row["id"] for row in listed.data] == [mine.id]
    assert api.get(reverse("project-detail", args=[mine.id])).status_code == 200


@pytest.mark.parametrize(("route", "key"), SCOPED)
def test_member_sees_what_hangs_off_the_project(
    api: APIClient, delivery: User, route: str, key: str
) -> None:
    mine = ProjectFactory()
    ProjectMemberFactory(project=mine, user=delivery)
    records = _populate(mine)
    _populate(ProjectFactory())  # ruído de projeto alheio

    listed = api.get(reverse(f"{route}-list"))

    assert [row["id"] for row in listed.data] == [records[key].id]


def test_removing_someone_from_the_team_revokes_access(api: APIClient, delivery: User) -> None:
    project = ProjectFactory()
    membership = ProjectMemberFactory(project=project, user=delivery)
    assert api.get(reverse("project-detail", args=[project.id])).status_code == 200

    membership.archive()

    assert api.get(reverse("project-detail", args=[project.id])).status_code == 404


def test_the_owner_is_always_a_member(delivery: User) -> None:
    """Invariante: quem responde pelo projeto participa dele, sem alguém precisar lembrar."""
    project = ProjectFactory(owner=delivery)

    assert project.members.filter(user=delivery, archived_at__isnull=True).exists()


def test_admin_and_sales_keep_seeing_every_project() -> None:
    ProjectFactory()
    ProjectFactory()

    for role in (User.Role.ADMIN, User.Role.SALES):
        client = APIClient()
        client.force_authenticate(UserFactory(role=role))
        assert len(client.get(reverse("project-list")).data) == 2, role
