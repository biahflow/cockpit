"""Avaliação heurística de risco de atraso de projeto, com explicação dos sinais.

Sem ML nem dependências: só regras sobre os dados atuais. Cada sinal traz seu peso, para
que a pessoa entenda o porquê do escore (explicabilidade). Evoluir para ML fica atrás de
uma decisão futura.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import Project


def _level(score: int) -> str:
    if score >= 60:
        return "alto"
    if score >= 30:
        return "médio"
    return "baixo"


def assess_project(project: Project) -> dict[str, Any]:
    from .models import Milestone, Task

    today = date.today()
    signals: list[dict[str, Any]] = []
    score = 0

    milestones = list(Milestone.objects.filter(project=project, archived_at__isnull=True))
    tasks = list(Task.objects.filter(project=project, archived_at__isnull=True))
    overdue = [item for item in milestones + tasks if item.is_overdue]
    if overdue:
        weight = min(40, len(overdue) * 10)
        score += weight
        signals.append({"label": "Itens atrasados", "detail": f"{len(overdue)} item(ns) vencido(s)", "weight": weight})

    days_left = (project.due_date - today).days
    if project.status != "completed":
        if days_left < 0:
            score += 30
            signals.append({"label": "Projeto vencido", "detail": f"{abs(days_left)} dia(s) além do prazo", "weight": 30})
        elif days_left <= 7:
            score += 15
            signals.append({"label": "Prazo próximo", "detail": f"faltam {days_left} dia(s)", "weight": 15})

    if project.status == "on_hold":
        score += 15
        signals.append({"label": "Em espera", "detail": "projeto pausado", "weight": 15})

    forecast: dict[str, Any] | None = None
    if milestones:
        done = sum(1 for m in milestones if m.status == "done")
        completion = done / len(milestones)
        total = (project.due_date - project.start_date).days or 1
        elapsed = (today - project.start_date).days
        expected = min(max(elapsed / total, 0), 1)
        if project.status != "completed" and completion + 0.25 < expected:
            score += 20
            signals.append({
                "label": "Ritmo abaixo do esperado",
                "detail": f"{round(completion * 100)}% concluído para {round(expected * 100)}% do tempo",
                "weight": 20,
            })
        # Previsão de término pelo ritmo atual (heurística explicável, sem ML).
        if project.status != "completed" and completion > 0 and elapsed > 0:
            predicted_total = round(elapsed / completion)
            predicted_finish = project.start_date + timedelta(days=predicted_total)
            forecast = {
                "predicted_finish_date": predicted_finish.isoformat(),
                "delay_days": (predicted_finish - project.due_date).days,
                "basis": f"{round(completion * 100)}% concluído em {elapsed} dia(s) de execução",
            }

    score = min(score, 100)
    return {
        "project_id": project.pk,
        "name": project.name,
        "score": score,
        "level": _level(score),
        "signals": signals,
        "forecast": forecast,
    }
