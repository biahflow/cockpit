"""Regressão: o backfill preserva o acesso que existia antes da regra nova (RFC 0003).

A migração 0025 é o que impede a mudança de regra de virar uma perda de acesso silenciosa no
deploy. Ela traduz o critério antigo — dono do projeto, de um marco ou de uma tarefa — em
linhas de `ProjectMember`. Se ela regredir, no dia do deploy toda a Entrega perde tudo, e o
sintoma (listas vazias) não parece um bug de migração.

O teste roda a função da migração sobre dados reais em vez de simular: é ela que vai rodar em
produção, uma vez só.
"""

import pytest

from apps.core.models import Milestone, Project, ProjectMember, Task, User
from apps.core.tests.factories import ProjectFactory, UserFactory

pytestmark = pytest.mark.django_db


def _run_backfill() -> None:
    """Importa a migração pelo nome de módulo (o número no início impede o `import` normal)."""
    import importlib

    from django.apps import apps as django_apps

    migration = importlib.import_module("apps.core.migrations.0025_backfill_project_members")
    migration.backfill_members(django_apps, None)


def test_backfill_covers_owner_and_work_item_owners() -> None:
    owner = UserFactory(role=User.Role.DELIVERY)
    milestone_owner = UserFactory(role=User.Role.DELIVERY)
    task_owner = UserFactory(role=User.Role.DELIVERY)
    project = ProjectFactory(owner=owner)
    Milestone.objects.create(
        project=project, title="Marco", owner=milestone_owner, due_date=project.due_date
    )
    Task.objects.create(
        project=project, title="Tarefa", owner=task_owner, due_date=project.due_date
    )
    ProjectMember.objects.all().delete()  # volta ao estado pré-migração

    _run_backfill()

    assert set(
        ProjectMember.objects.filter(project=project).values_list("user_id", flat=True)
    ) == {owner.pk, milestone_owner.pk, task_owner.pk}


def test_backfill_includes_owners_of_archived_work_items() -> None:
    """Fidelidade ao critério antigo, que não filtrava arquivados — apertar é decisão separada."""
    project = ProjectFactory()
    person = UserFactory(role=User.Role.DELIVERY)
    task = Task.objects.create(
        project=project, title="Tarefa", owner=person, due_date=project.due_date
    )
    task.archive()
    ProjectMember.objects.all().delete()

    _run_backfill()

    assert ProjectMember.objects.filter(project=project, user=person).exists()


def test_backfill_is_idempotent() -> None:
    project = ProjectFactory()

    _run_backfill()
    _run_backfill()

    assert ProjectMember.objects.filter(project=project, user=project.owner).count() == 1


def test_backfill_reaches_archived_projects() -> None:
    """Projeto arquivado volta se for desarquivado; sem membro, voltaria invisível."""
    project = ProjectFactory()
    project.archive()
    ProjectMember.objects.all().delete()

    _run_backfill()

    assert ProjectMember.objects.filter(project=project).exists()
    assert Project.objects.filter(pk=project.pk).exists()
