"""Modelo EngineeringHandoff (FDD 040): chave de idempotência e estado provisioned fechado."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.models import EngineeringHandoff, Task

from .factories import EngineeringHandoffFactory, ProjectFactory


@pytest.mark.django_db
def test_factory_cria_pending_valido() -> None:
    handoff = EngineeringHandoffFactory()
    handoff.full_clean()
    assert handoff.status == EngineeringHandoff.Status.PENDING
    assert handoff.github_issue_number is None
    assert handoff.github_issue_url == ""
    assert handoff.attempt_count == 0
    assert handoff.correlation_id is not None


@pytest.mark.django_db
def test_pulse_work_item_id_unico() -> None:
    project = ProjectFactory()
    EngineeringHandoffFactory(project=project, pulse_work_item_id="pulse-dup")
    with pytest.raises(IntegrityError), transaction.atomic():
        EngineeringHandoffFactory(project=project, pulse_work_item_id="pulse-dup")


@pytest.mark.django_db
def test_full_clean_recusa_provisioned_sem_issue() -> None:
    handoff = EngineeringHandoffFactory(
        status=EngineeringHandoff.Status.PROVISIONED,
        github_issue_number=None,
        github_issue_url="",
    )
    with pytest.raises(ValidationError) as exc:
        handoff.full_clean()
    assert "status" in exc.value.message_dict


@pytest.mark.django_db
def test_full_clean_recusa_source_task_de_outro_projeto() -> None:
    projeto = ProjectFactory()
    outro = ProjectFactory()
    tarefa = Task.objects.create(
        project=outro,
        title="Tarefa alheia",
        owner=outro.owner,
        due_date=timezone.localdate(),
    )
    handoff = EngineeringHandoffFactory(project=projeto, source_task=tarefa)
    with pytest.raises(ValidationError) as exc:
        handoff.full_clean()
    assert "source_task" in exc.value.message_dict
