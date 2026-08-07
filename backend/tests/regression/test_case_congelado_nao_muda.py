"""Regressão: os números do case não mudam quando o projeto muda depois (FDD 027, ADR 0020).

É a razão de o `Case` existir como registro em vez de uma tela que agrega o estado atual.
`assess_project_health` é função pura sobre o **agora**: um projeto concluído, recalculado meses
depois, devolve outro número porque tarefas fecharam e pendências sumiram. Um case cujo número
muda sozinho depois de publicado é pior que nenhum case — quem citou o número na proposta passa a
estar dizendo outra coisa sem saber.

O teste não confere que ninguém escreveu; confere que **não há por onde**. Mexe no projeto pelos
três caminhos que alterariam o cálculo (tarefa, pendência e valores) e tenta reescrever os campos
congelados pela API.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.core.models import (
    Case,
    DigitalEmployee,
    KpiDirection,
    KpiUnit,
    Pendencia,
    Project,
    Task,
    WorkItem,
)
from apps.core.tests.factories import ProjectFactory, UserFactory


@pytest.mark.django_db
def test_alterar_o_projeto_depois_nao_altera_o_case() -> None:
    project = ProjectFactory(actual_value=Decimal("180000.00"), cost=Decimal("90000.00"))
    dono = project.owner
    DigitalEmployee.objects.create(
        project=project, name="SDR", kpi_label="Leads/mês", kpi_unit=KpiUnit.COUNT,
        kpi_direction=KpiDirection.UP, kpi_baseline=Decimal("12.00"),
        kpi_current=Decimal("48.00"),
    )
    Task.objects.create(
        project=project, title="Tarefa vencida", owner=dono,
        due_date=project.start_date - timedelta(days=10),
    )
    project.status = Project.Status.COMPLETED
    project.save()

    case = Case.objects.get(project=project)
    congelado = (case.health_snapshot, case.roi_snapshot, case.metrics)

    # Tudo o que aconteceria com um projeto concluído nos meses seguintes.
    Task.objects.filter(project=project).delete()
    Pendencia.objects.create(
        project=project, title="Decisão nova", owner=dono, party=WorkItem.Party.CLIENT,
    )
    DigitalEmployee.objects.filter(project=project).update(kpi_current=Decimal("999.00"))
    project.actual_value = Decimal("10.00")
    project.cost = Decimal("500000.00")
    project.save()

    case.refresh_from_db()
    assert (case.health_snapshot, case.roi_snapshot, case.metrics) == congelado


@pytest.mark.django_db
def test_a_api_nao_reescreve_os_numeros_congelados() -> None:
    project = ProjectFactory(actual_value=Decimal("180000.00"), cost=Decimal("90000.00"))
    project.status = Project.Status.COMPLETED
    project.save()
    case = Case.objects.get(project=project)
    congelado = (case.health_snapshot, case.roi_snapshot, case.metrics)
    api = APIClient()
    api.force_authenticate(UserFactory(role="admin"))

    resposta = api.patch(
        f"/api/v1/cases/{case.pk}/",
        {
            "title": "Título revisado pelo humano",
            "health_snapshot": {"score": 100, "level": "saudável", "signals": []},
            "roi_snapshot": {"revenue": "999999.00", "cost": "1.00", "roi": 999.0},
            "metrics": [{"name": "Inventado", "baseline": "0", "current": "1000"}],
        },
        format="json",
    )

    assert resposta.status_code == 200
    case.refresh_from_db()
    # O que é do humano muda; o que é fotografia, não.
    assert case.title == "Título revisado pelo humano"
    assert (case.health_snapshot, case.roi_snapshot, case.metrics) == congelado
