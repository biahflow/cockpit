from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import Milestone, PipelineStage, Task

from .factories import ProjectFactory, UserFactory


@pytest.mark.django_db
def test_initial_pipeline_has_required_terminal_stages():
    assert PipelineStage.objects.filter(kind=PipelineStage.Kind.WON).count() == 1
    assert PipelineStage.objects.filter(kind=PipelineStage.Kind.LOST).count() == 1


@pytest.mark.django_db
def test_work_item_is_overdue_until_done():
    project = ProjectFactory()
    milestone = Milestone.objects.create(
        project=project,
        title="Marco vencido",
        owner=UserFactory(),
        due_date=timezone.localdate() - timedelta(days=1),
    )
    assert milestone.is_overdue is True

    milestone.status = Milestone.Status.DONE
    milestone.save()
    assert milestone.completed_at is not None
    assert milestone.is_overdue is False

    milestone.status = Milestone.Status.TODO
    milestone.save()
    assert milestone.completed_at is None
    assert milestone.is_overdue is True


@pytest.mark.django_db
def test_task_rejects_milestone_from_another_project():
    first_project = ProjectFactory()
    second_project = ProjectFactory()
    milestone = Milestone.objects.create(
        project=first_project,
        title="Marco",
        owner=UserFactory(),
        due_date=timezone.localdate(),
    )
    task = Task(
        project=second_project,
        milestone=milestone,
        title="Tarefa",
        owner=UserFactory(),
        due_date=timezone.localdate(),
    )
    with pytest.raises(ValidationError):
        task.clean()
