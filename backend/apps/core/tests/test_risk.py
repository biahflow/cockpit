from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core import recommendations, risk
from apps.core.models import Milestone, Task

from .factories import ClientFactory, ProjectFactory


@pytest.mark.django_db
def test_forecast_predicts_delay_from_slow_pace():
    # começou há 20 dias, prazo total de 30 dias, só 25% concluído → prevê término além do prazo
    start = timezone.localdate() - timedelta(days=20)
    project = ProjectFactory(start_date=start, due_date=start + timedelta(days=30))
    for index in range(4):
        Milestone.objects.create(
            project=project, title=f"M{index}", owner=project.owner,
            due_date=timezone.localdate(), status="done" if index == 0 else "todo",
        )
    forecast = risk.assess_project(project)["forecast"]
    assert forecast is not None
    assert forecast["delay_days"] > 0  # 25% em 20 dias → previsão ultrapassa o prazo


@pytest.mark.django_db
def test_forecast_is_none_without_progress():
    project = ProjectFactory()
    Milestone.objects.create(
        project=project, title="M", owner=project.owner,
        due_date=timezone.localdate(), status="todo",
    )
    assert risk.assess_project(project)["forecast"] is None  # 0% concluído → sem base


@pytest.mark.django_db
def test_assess_project_flags_overdue_and_explains_signals():
    project = ProjectFactory(due_date=timezone.localdate() - timedelta(days=5))
    Task.objects.create(
        project=project, title="Atrasada", owner=project.owner,
        due_date=timezone.localdate() - timedelta(days=2),
    )

    result = risk.assess_project(project)

    labels = [signal["label"] for signal in result["signals"]]
    assert "Projeto vencido" in labels
    assert "Itens atrasados" in labels
    assert result["score"] > 0
    assert result["level"] in {"baixo", "médio", "alto"}


@pytest.mark.django_db
def test_assess_project_low_risk_when_healthy():
    project = ProjectFactory(
        start_date=timezone.localdate(),
        due_date=timezone.localdate() + timedelta(days=60),
        status="active",
    )
    result = risk.assess_project(project)
    assert result["level"] == "baixo"
    assert result["signals"] == []


@pytest.mark.django_db
def test_recommendations_cover_upsell_and_deadline():
    client = ClientFactory()
    ProjectFactory(client=client, due_date=timezone.localdate() + timedelta(days=3), status="active")

    kinds = {rec["kind"] for rec in recommendations.build_recommendations()}

    assert "upsell" in kinds  # cliente com projeto e sem oportunidade aberta
    assert "deadline" in kinds  # projeto vencendo em breve
