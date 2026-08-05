"""Regressão: concluir não é caminho sem volta.

A tela deixava marcar como concluído e travava o controle (`disabled`), então uma marcação por
engano não tinha desfazer. Reabrir depende de o modelo limpar o carimbo de conclusão — se
`WorkItem.save`/`Pendencia.save` pararem de fazer isso, o item volta para "a fazer" carregando um
`completed_at`/`resolved_at` de um fato que não aconteceu, e todo indicador que conta conclusão
passa a mentir.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Pendencia, Task, User
from apps.core.tests.factories import ProjectFactory, UserFactory


@pytest.fixture
def admin_api() -> APIClient:
    api = APIClient()
    api.force_authenticate(UserFactory(role=User.Role.ADMIN))
    return api


@pytest.mark.django_db
def test_reopening_a_task_clears_completed_at(admin_api: APIClient) -> None:
    project = ProjectFactory()
    task = Task.objects.create(
        project=project, title="Concluída por engano", owner=project.owner,
        due_date=project.due_date, status=Task.Status.DONE,
    )
    assert task.completed_at is not None

    response = admin_api.patch(
        reverse("task-detail", args=[task.pk]), {"status": "todo"}, format="json"
    )

    assert response.status_code == 200
    task.refresh_from_db()
    assert task.status == Task.Status.TODO
    assert task.completed_at is None


@pytest.mark.django_db
def test_reopening_a_pendencia_clears_resolved_at(admin_api: APIClient) -> None:
    project = ProjectFactory()
    pendencia = Pendencia.objects.create(
        project=project, title="Resolvida por engano", status=Pendencia.Status.RESOLVED,
    )
    assert pendencia.resolved_at is not None

    response = admin_api.patch(
        reverse("pendencia-detail", args=[pendencia.pk]), {"status": "open"}, format="json"
    )

    assert response.status_code == 200
    pendencia.refresh_from_db()
    assert pendencia.status == Pendencia.Status.OPEN
    assert pendencia.resolved_at is None
