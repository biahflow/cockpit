"""Health Score do projeto — a saúde da relação, explicável e sem ML.

É o inverso do risco de atraso (`risk.py`): aqui **100 = saudável** e cada sinal ruim
**subtrai** pontos, para a equipe saber onde agir antes de o cliente reclamar. Cada sinal
traz seu peso (quanto tirou), preservando a explicabilidade.

Só usa sinais com dado real no domínio: entregas atrasadas/fora do prazo, reuniões não
realizadas, decisões pendentes (pesa mais quando o cliente é quem trava) e ROI negativo.
Satisfação, bugs e "acessos liberados" ficam de fora até existir onde registrá-los.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import Project


def _level(score: int) -> str:
    if score >= 75:
        return "saudável"
    if score >= 50:
        return "atenção"
    return "crítico"


def assess_project_health(project: Project) -> dict[str, Any]:
    from .models import Meeting, Milestone, Pendencia, Task, WorkItem

    today = date.today()
    signals: list[dict[str, Any]] = []
    score = 100

    items = list(Milestone.objects.filter(project=project, archived_at__isnull=True)) + list(
        Task.objects.filter(project=project, archived_at__isnull=True)
    )
    overdue = [item for item in items if item.is_overdue]
    if overdue:
        weight = min(30, len(overdue) * 8)
        score -= weight
        signals.append({"label": "Entregas atrasadas", "detail": f"{len(overdue)} item(ns) vencido(s)", "weight": weight})

    late_done = [
        item for item in items if item.completed_at and item.completed_at.date() > item.due_date
    ]
    if late_done:
        weight = min(12, len(late_done) * 3)
        score -= weight
        signals.append({"label": "Entregues fora do prazo", "detail": f"{len(late_done)} item(ns) concluído(s) com atraso", "weight": weight})

    missed = Meeting.objects.filter(
        project=project, archived_at__isnull=True, status=Meeting.Status.SCHEDULED, date__lt=today
    ).count()
    if missed:
        weight = min(20, missed * 10)
        score -= weight
        signals.append({"label": "Reuniões não realizadas", "detail": f"{missed} reunião(ões) agendada(s) e vencida(s)", "weight": weight})

    open_pendencias = list(
        Pendencia.objects.filter(project=project, archived_at__isnull=True, status=Pendencia.Status.OPEN)
    )
    if open_pendencias:
        blocking_client = sum(1 for pendencia in open_pendencias if pendencia.party == WorkItem.Party.CLIENT)
        weight = min(25, len(open_pendencias) * 5 + blocking_client * 3)
        score -= weight
        detail = f"{len(open_pendencias)} em aberto"
        if blocking_client:
            detail += f" · {blocking_client} aguardando o cliente"
        signals.append({"label": "Decisões pendentes", "detail": detail, "weight": weight})

    if project.cost and (project.actual_value - project.cost) < 0:
        weight = 15
        score -= weight
        signals.append({"label": "ROI negativo", "detail": "custo acima do valor entregue até aqui", "weight": weight})

    score = max(0, min(score, 100))
    return {
        "project_id": project.pk,
        "name": project.name,
        "score": score,
        "level": _level(score),
        "signals": signals,
    }
