"""Regressão: só o admin monta a equipe do projeto (RFC 0003, ADR 0010).

Quem tem essa caneta concede acesso a dado de projeto, então ela fica com uma função só.
Entrega e Vendas leem a equipe dos projetos que já enxergam — precisam saber quem toca a
conta — mas não escrevem. Sem isso, participar de um projeto bastaria para entrar em
qualquer outro, e o recorte inteiro cairia.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import ProjectMember, User
from apps.core.tests.factories import ProjectFactory, ProjectMemberFactory, UserFactory

pytestmark = pytest.mark.django_db


def _client(role: str) -> tuple[APIClient, User]:
    user = UserFactory(role=role)
    api = APIClient()
    api.force_authenticate(user)
    return api, user


@pytest.mark.parametrize("role", [User.Role.DELIVERY, User.Role.SALES])
def test_only_admin_adds_someone_to_a_project(role: str) -> None:
    api, user = _client(role)
    project = ProjectFactory()
    if role == User.Role.DELIVERY:
        ProjectMemberFactory(project=project, user=user)

    response = api.post(reverse("projectmember-list"), {
        "project": project.id, "user": UserFactory(role=User.Role.DELIVERY).id,
    }, format="json")

    assert response.status_code == 403


def test_admin_adds_someone_to_a_project() -> None:
    api, admin = _client(User.Role.ADMIN)
    project = ProjectFactory()
    newcomer = UserFactory(role=User.Role.DELIVERY)

    response = api.post(reverse("projectmember-list"), {
        "project": project.id, "user": newcomer.id,
    }, format="json")

    assert response.status_code == 201
    membership = ProjectMember.objects.get(project=project, user=newcomer)
    assert membership.added_by_id == admin.pk


def test_admin_removes_someone_and_access_goes_away() -> None:
    api, _ = _client(User.Role.ADMIN)
    project = ProjectFactory()
    person = UserFactory(role=User.Role.DELIVERY)
    membership = ProjectMemberFactory(project=project, user=person)

    assert api.delete(reverse("projectmember-detail", args=[membership.id])).status_code == 204

    theirs = APIClient()
    theirs.force_authenticate(person)
    assert theirs.get(reverse("project-detail", args=[project.id])).status_code == 404


def test_delivery_reads_the_team_of_its_own_project_only() -> None:
    api, user = _client(User.Role.DELIVERY)
    mine = ProjectFactory()
    ProjectMemberFactory(project=mine, user=user)
    ProjectMemberFactory(project=ProjectFactory(), user=UserFactory(role=User.Role.DELIVERY))

    listed = api.get(reverse("projectmember-list")).data

    assert {row["project"] for row in listed} == {mine.id}


def test_someone_can_be_readded_after_leaving() -> None:
    """A constraint é condicional ao arquivamento — sair e voltar é rotina, não erro."""
    api, _ = _client(User.Role.ADMIN)
    project = ProjectFactory()
    person = UserFactory(role=User.Role.DELIVERY)
    membership = ProjectMemberFactory(project=project, user=person)
    api.delete(reverse("projectmember-detail", args=[membership.id]))

    response = api.post(reverse("projectmember-list"), {
        "project": project.id, "user": person.id,
    }, format="json")

    assert response.status_code == 201
