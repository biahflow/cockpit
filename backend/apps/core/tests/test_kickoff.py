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
def test_qualification_call_gets_the_short_schedule():
    project = ProjectFactory(service=Service.objects.get(tier=Service.Tier.QUALIFICATION_CALL))

    milestones, _ = kickoff.seed_work_items(project)

    assert milestones == 1
    assert Milestone.objects.get(project=project).title == "Qualification Call"


@pytest.mark.django_db
def test_discovery_sprint_ends_in_the_executive_readout():
    """Sprint pago sem readout é trabalho feito que ninguém viu (ADR 0030)."""
    project = ProjectFactory(service=Service.objects.get(tier=Service.Tier.DISCOVERY_SPRINT))

    milestones, _ = kickoff.seed_work_items(project)

    assert milestones == len(kickoff.KICKOFF_TEMPLATES["discovery_sprint"])
    titles = list(Milestone.objects.filter(project=project).order_by("due_date")
                  .values_list("title", flat=True))
    assert titles[-1] == "Executive Readout"
    tasks = list(Task.objects.filter(project=project).values_list("title", flat=True))
    assert "Calcular o Opportunity Score de cada processo" in tasks


@pytest.mark.django_db
def test_feasibility_sets_the_target_before_running_the_sample():
    """Critério definido depois do resultado não é critério, é narrativa (ADR 0030)."""
    project = ProjectFactory(service=Service.objects.get(tier=Service.Tier.FEASIBILITY))

    milestones, _ = kickoff.seed_work_items(project)

    assert milestones == len(kickoff.KICKOFF_TEMPLATES["feasibility"])
    tasks = list(Task.objects.filter(project=project).values_list("title", flat=True))
    assert "Definir a meta **antes** de rodar a amostra" in tasks
    assert "Registrar o gate (GO / CONDITIONAL GO / REDESIGN / NO-GO)" in tasks


@pytest.mark.django_db
def test_discovery_sprint_fecha_em_executive_readout():
    project = ProjectFactory(service=Service.objects.get(tier=Service.Tier.DISCOVERY_SPRINT))

    milestones, _ = kickoff.seed_work_items(project)

    assert milestones == 3
    titles = list(Milestone.objects.filter(project=project).values_list("title", flat=True))
    assert "Executive Readout" in titles


@pytest.mark.django_db
def test_prove_gets_the_baseline_and_the_decision_gate():
    # ADR 0030: baseline/critérios antes de construir e o decision gate no encerramento
    # fazem parte do cronograma semeado.
    project = ProjectFactory(service=Service.objects.get(tier=Service.Tier.PROVE))

    milestones, _ = kickoff.seed_work_items(project)

    assert milestones == len(kickoff.KICKOFF_TEMPLATES["prove"])
    tasks = list(Task.objects.filter(project=project).values_list("title", flat=True))
    assert "Registrar o baseline e os critérios de sucesso antes de construir" in tasks
    assert "Registrar a decisão SCALE / ITERATE / STOP" in tasks


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
