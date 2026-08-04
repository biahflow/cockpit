from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core import kickoff
from apps.core.models import Milestone, Notification, Task

from .factories import ProjectFactory, UserFactory


@pytest.mark.django_db
def test_seed_work_items_creates_schedule_within_window():
    owner = UserFactory()
    project = ProjectFactory(owner=owner, start_date=timezone.localdate(),
                             due_date=timezone.localdate() + timedelta(days=120))

    milestones, tasks = kickoff.seed_work_items(project)

    assert milestones == len(kickoff.KICKOFF_TEMPLATE)
    assert tasks == sum(len(spec["tasks"]) for spec in kickoff.KICKOFF_TEMPLATE)
    created = Milestone.objects.filter(project=project)
    assert created.count() == milestones
    assert all(m.owner_id == owner.id for m in created)
    assert all(project.start_date <= m.due_date <= project.due_date for m in created)
    assert all(t.milestone_id is not None for t in Task.objects.filter(project=project))


@pytest.mark.django_db
def test_seed_work_items_clamps_due_dates_to_short_window():
    project = ProjectFactory(start_date=timezone.localdate(),
                             due_date=timezone.localdate() + timedelta(days=3))
    kickoff.seed_work_items(project)
    assert all(m.due_date <= project.due_date for m in Milestone.objects.filter(project=project))


@pytest.mark.django_db
def test_finalize_sends_email_and_notifies_owner(mailoutbox):
    owner = UserFactory(email="dono@example.test")
    project = ProjectFactory(owner=owner)

    kickoff.finalize(project)

    assert len(mailoutbox) == 1
    assert project.name in mailoutbox[0].subject
    assert mailoutbox[0].to == ["dono@example.test"]
    assert Notification.objects.filter(user=owner, kind="kickoff").count() == 1


@pytest.mark.django_db
def test_finalize_skips_email_without_owner_address(mailoutbox):
    owner = UserFactory(email="")
    project = ProjectFactory(owner=owner)

    kickoff.finalize(project)

    assert len(mailoutbox) == 0
    assert Notification.objects.filter(user=owner, kind="kickoff").count() == 1
