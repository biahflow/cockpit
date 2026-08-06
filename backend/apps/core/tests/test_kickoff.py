from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core import kickoff
from apps.core.models import Milestone, Notification, Service, Task

from .factories import ProjectFactory, ServiceFactory, UserFactory


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
def test_discovery_express_gets_the_short_schedule():
    project = ProjectFactory(service=Service.objects.get(tier=Service.Tier.DISCOVERY_EXPRESS))

    milestones, _ = kickoff.seed_work_items(project)

    assert milestones == 1
    assert Milestone.objects.get(project=project).title == "Discovery"


@pytest.mark.django_db
def test_discovery_assessment_gets_two_milestones():
    project = ProjectFactory(service=Service.objects.get(tier=Service.Tier.DISCOVERY_ASSESSMENT))

    milestones, _ = kickoff.seed_work_items(project)

    assert milestones == 2
    titles = list(Milestone.objects.filter(project=project).values_list("title", flat=True))
    assert "Assessment e recomendações" in titles


@pytest.mark.django_db
def test_implementation_keeps_the_default_schedule():
    project = ProjectFactory(service=Service.objects.get(tier=Service.Tier.IMPLEMENTATION))

    milestones, _ = kickoff.seed_work_items(project)

    assert milestones == len(kickoff.KICKOFF_TEMPLATE)


@pytest.mark.django_db
def test_project_without_tier_falls_back_to_the_default_schedule():
    without_service = ProjectFactory()
    loose_service = ProjectFactory(service=ServiceFactory())

    assert kickoff.template_for(without_service) is kickoff.KICKOFF_TEMPLATE
    assert kickoff.template_for(loose_service) is kickoff.KICKOFF_TEMPLATE


@pytest.mark.django_db
def test_finalize_sends_email_and_notifies_owner(mailoutbox):
    owner = UserFactory(email="dono@example.test")
    project = ProjectFactory(owner=owner)

    kickoff.finalize(project)

    # Saem dois e-mails desde a ADR 0018: o do kickoff, que ignora a flag `email` por ser parte do
    # fluxo e não notificação, e o da própria notificação, que passou a ser ligada por padrão. O que
    # este teste garante é o primeiro — daí procurá-lo pelo assunto em vez de contar a caixa.
    kickoff_mail = next(mail for mail in mailoutbox if project.name in mail.subject)
    assert kickoff_mail.to == ["dono@example.test"]
    assert Notification.objects.filter(user=owner, kind="kickoff").count() == 1


@pytest.mark.django_db
def test_finalize_skips_email_without_owner_address(mailoutbox):
    owner = UserFactory(email="")
    project = ProjectFactory(owner=owner)

    kickoff.finalize(project)

    assert len(mailoutbox) == 0
    assert Notification.objects.filter(user=owner, kind="kickoff").count() == 1
