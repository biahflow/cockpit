"""Regressão: a entrada da sincronia não repropaga para o fornecedor (evita loop/eco)."""

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core import tasksync
from apps.core.models import Task
from apps.core.tests.factories import ProjectFactory


@pytest.mark.django_db
def test_inbound_apply_does_not_call_outbound(monkeypatch: pytest.MonkeyPatch) -> None:
    project = ProjectFactory()
    Task.objects.create(
        project=project,
        title="Tarefa",
        owner=project.owner,
        due_date=timezone.localdate() + timedelta(days=3),
        source="linear",
        external_id="ENG-77",
        status=Task.Status.TODO,
    )
    calls: list = []
    monkeypatch.setattr(tasksync, "push_update", lambda task: calls.append(task))

    with override_settings(TASKSYNC_ENABLED=True, TASKSYNC_TOKEN="t"):
        tasksync.apply_inbound("linear", "ENG-77", "completed")

    assert calls == []
