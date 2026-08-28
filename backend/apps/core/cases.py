"""O congelamento do case de um projeto concluído (FDD 027, ADR 0020).

Este módulo tem uma função só, e é toda a ideia da FDD: quando o projeto chega a `completed`,
tirar uma **fotografia** dos números daquele instante e gravá-la. Nada aqui é recalculado depois.

A tentação era não ter módulo nenhum — "o dado já existe, é só uma projeção". Não é: o health é
função pura sobre o estado atual (`health.assess_project_health`), então a mesma pergunta feita
seis meses depois responde outra coisa; e `DigitalEmployee.hours_saved_month` é o *delta
declarado*, não um par antes/depois. É por isso que o congelamento é escrita, não leitura.

Fica ao lado de `blueprints.py` pela mesma razão que ele existe: regra de domínio que nasceu de uma
FDD, fora da view, testável sem HTTP.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from .health import assess_project_health

if TYPE_CHECKING:
    from .models import Case, DigitalEmployee, Project


def _decimal(value: Decimal | None) -> str | None:
    """`None` sobrevive ao JSON como `None` — é o que distingue "não medido" de "era zero"."""
    return None if value is None else str(value)


def _metric(employee: DigitalEmployee) -> dict[str, Any]:
    """A linha antes/depois de um Funcionário Digital, com a unidade em que ela se lê.

    `has_baseline` é campo próprio e não uma inferência sobre `baseline is None` do outro lado:
    quem consome o case (tela e prompt) precisa dizer "sem base registrada" em voz alta, e a
    ausência de base **é informação** — preenchê-la com zero seria inventar o "antes" (FDD 027).
    """
    return {
        "employee_id": employee.pk,
        # Procedência do bloco, e o que permite filtrar cases por blueprint na tela sem que ela
        # precise carregar o roster de cada projeto concluído.
        "blueprint_id": employee.blueprint_id,
        "name": employee.name,
        "area": employee.area,
        "kpi_label": employee.kpi_label,
        "kpi_unit": employee.kpi_unit,
        "kpi_direction": employee.kpi_direction,
        "baseline": _decimal(employee.kpi_baseline),
        "current": _decimal(employee.kpi_current),
        "has_baseline": employee.kpi_baseline is not None,
        # A frase livre da era anterior à FDD 027. Vai junto porque é o único "depois" que existe
        # nos Funcionários Digitais entregues antes desta entrega.
        "kpi_value": employee.kpi_value,
        "hours_saved_month": str(employee.hours_saved_month),
    }


def _roi_snapshot(project: Project) -> dict[str, Any]:
    """Receita, custo e razão do projeto no instante do congelamento.

    A aritmética repete a de `views._roi` de propósito: aquela é a agregação viva de Indicadores e
    pode mudar de fórmula amanhã; esta é uma fotografia e não pode mudar de significado depois de
    tirada. Importar de lá também inverteria a direção do import (view → domínio) que o resto do
    pacote respeita.
    """
    revenue, cost = project.actual_value, project.cost
    return {
        "revenue": str(revenue),
        "cost": str(cost),
        "roi": float((revenue - cost) / cost) if cost else None,
    }


def freeze(project: Project) -> Case:
    """Cria o `Case` em rascunho com os números do projeto **congelados** neste instante.

    Rascunho, e não publicado: a governança espelha a do AI Score (FDD 014), que só cruza ao portal
    depois de revisto por gente. Aqui é o mesmo — a máquina apura, o humano decide se vira prova.
    """
    from .models import Case, DigitalEmployee

    employees = DigitalEmployee.objects.filter(
        project=project, archived_at__isnull=True
    ).order_by("name", "id")
    account = project.client
    return Case.objects.create(
        project=project,
        title=f"{account.name} — {project.name}",
        vertical=account.vertical,
        metrics=[_metric(employee) for employee in employees],
        health_snapshot=assess_project_health(project),
        roi_snapshot=_roi_snapshot(project),
        status=Case.Status.DRAFT,
    )


def freeze_if_completed(project: Project) -> Case | None:
    """Congela na conclusão, uma vez só.

    A idempotência é por existência, e não por comparar o status anterior num `pre_save`: um
    projeto reaberto e reconcluído não deve produzir um segundo case, e o `save()` de qualquer
    outro campo de um projeto já concluído não deve produzir nada. A pergunta "já existe case
    deste projeto?" responde aos três casos com uma consulta.
    """
    from .models import Case, Project

    if project.status != Project.Status.COMPLETED:
        return None
    if Case.objects.filter(project=project).exists():
        return None
    return freeze(project)


def record_consent(case: Case, user: Any) -> Case:
    """Registra o consentimento do cliente, com autor e carimbo (FDD 027).

    Fora do serializer de propósito: consentimento não é um campo que se edita junto com o título,
    é um ato — e sem `consent_recorded_by` "o cliente autorizou" é alegação de ninguém. Mesma forma
    de `ProjectMember.added_by`.
    """
    case.client_consent = True
    case.consent_recorded_at = timezone.now()
    case.consent_recorded_by = user
    case.save(update_fields=[
        "client_consent", "consent_recorded_at", "consent_recorded_by", "updated_at",
    ])
    return case
