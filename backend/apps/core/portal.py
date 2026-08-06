"""Integração com o portal do cliente (ADR 0003).

O Biahflow é a fonte da verdade do status do projeto. Aqui ficam os utilitários que
notificam o portal externo (webhook assinado) e que montam o snapshot read-only que o
portal consome para backfill/reconciliação. Nenhum dado comercial é exposto.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import health
from .models import (
    DigitalEmployee,
    Document,
    Meeting,
    Milestone,
    Pendencia,
    Project,
    ProjectPhase,
)

logger = logging.getLogger(__name__)

# Saúde interna → rótulo amigável + cor para o portal do cliente (sem expor score/sinais).
_HEALTH_LABEL: dict[str, tuple[str, str]] = {
    "saudável": ("No prazo", "green"),
    "atenção": ("Requer atenção", "amber"),
    "crítico": ("Atrasado", "red"),
}


def sign(secret: str, body: bytes) -> str:
    """Assinatura HMAC-SHA256 do corpo do webhook."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _doc_type(name: str) -> str:
    """Tipo do documento derivado da extensão (para o portal exibir PDF/Planilha/…)."""
    _, _, ext = name.rpartition(".")
    return ext.upper() if ext and ext != name else "Arquivo"


def _journey(project: Project) -> list[dict[str, Any]]:
    """Fases da jornada de transformação do projeto, com seus entregáveis (ADR 0003).

    O portal do cliente usa `status` (locked/active/done) para montar o "Você está aqui" e
    para "desbloquear" os entregáveis fase a fase. Só o vocabulário da metodologia e o estado
    cruzam — nada técnico (tasks/PRs) vai para o cliente.
    """
    phases = (
        ProjectPhase.objects.filter(project=project, archived_at__isnull=True)
        .select_related("phase")
        .prefetch_related("deliverables", "deliverables__document")
        .order_by("phase__position", "id")
    )
    return [
        {
            "id": phase.pk,
            "name": phase.phase.name,
            "description": phase.phase.description,
            "position": phase.phase.position,
            "status": phase.status,
            "target_date": phase.target_date.isoformat() if phase.target_date else None,
            "started_at": phase.started_at.isoformat() if phase.started_at else None,
            "completed_at": phase.completed_at.isoformat() if phase.completed_at else None,
            "deliverables": [
                {
                    "id": deliverable.pk,
                    "name": deliverable.name,
                    "status": deliverable.status,
                    "delivered_at": (
                        deliverable.delivered_at.isoformat() if deliverable.delivered_at else None
                    ),
                    "link": deliverable.document.drive_link if deliverable.document else None,
                }
                for deliverable in phase.deliverables.all()
            ],
        }
        for phase in phases
    ]


def ai_score_snapshot(project: Project) -> dict[str, Any] | None:
    """AI Score de maturidade/oportunidade de IA para o portal (FDD 014).

    Só cruza ao cliente depois da revisão humana (`ai_score_reviewed`) — é a narrativa de valor,
    não dado comercial. Sem revisão, retorna None e o portal simplesmente não mostra o índice.
    """
    if not project.ai_score_reviewed or project.ai_scored_at is None:
        return None
    return {
        "maturity": project.ai_maturity,
        "opportunity": project.ai_opportunity,
        "dimensions": project.ai_dimensions,
        "summary": project.ai_score_summary,
        "scored_at": project.ai_scored_at.isoformat(),
    }


def build_snapshot(project: Project) -> dict[str, Any]:
    """Projeção read-only e segura do projeto para o portal do cliente."""
    milestones = [
        {
            "id": milestone.pk,
            "title": milestone.title,
            "status": milestone.status,
            "party": milestone.party,
            "due_date": milestone.due_date.isoformat(),
            "completed_at": milestone.completed_at.isoformat() if milestone.completed_at else None,
            "is_overdue": milestone.is_overdue,
        }
        for milestone in Milestone.objects.filter(project=project, archived_at__isnull=True)
    ]
    documents = [
        {
            "id": document.pk,
            "name": document.original_name,
            "type": _doc_type(document.original_name),
            "author": document.uploaded_by.get_full_name() or document.uploaded_by.username,
            "link": document.drive_link,
            "created_at": document.created_at.isoformat(),
        }
        for document in Document.objects.filter(
            project=project, archived_at__isnull=True
        ).select_related("uploaded_by")
    ]
    meetings = [
        {
            "id": meeting.pk,
            "title": meeting.title,
            "date": meeting.date.isoformat(),
            "recording_url": meeting.recording_url,
            "has_transcript": bool(meeting.transcript),
            "status": meeting.status,
        }
        for meeting in Meeting.objects.filter(project=project, archived_at__isnull=True)
    ]
    pendencias = [
        {
            "id": pendencia.pk,
            "title": pendencia.title,
            "status": pendencia.status,
            "party": pendencia.party,
            "created_at": pendencia.created_at.isoformat(),
            "resolved_at": pendencia.resolved_at.isoformat() if pendencia.resolved_at else None,
        }
        for pendencia in Pendencia.objects.filter(project=project, archived_at__isnull=True)
    ]
    done = sum(1 for milestone in milestones if milestone["status"] == Milestone.Status.DONE)
    completion = round(done / len(milestones) * 100) if milestones else 0
    overdue = sum(1 for milestone in milestones if milestone["is_overdue"])
    on_time_pct = round((len(milestones) - overdue) / len(milestones) * 100) if milestones else 100

    journey = _journey(project)
    current_phase = next(
        (phase["name"] for phase in journey if phase["status"] == ProjectPhase.Status.ACTIVE), None
    )
    health_label, health_level = _HEALTH_LABEL.get(
        health.assess_project_health(project)["level"], ("Em acompanhamento", "amber")
    )
    digital_employees = [
        {
            "id": employee.pk,
            "name": employee.name,
            "area": employee.area,
            "description": employee.description,
            "status": employee.status,
            "kpi_label": employee.kpi_label,
            "kpi_value": employee.kpi_value,
            "hours_saved_month": float(employee.hours_saved_month),
            "roi_month": float(employee.roi_month),
        }
        for employee in DigitalEmployee.objects.filter(project=project, archived_at__isnull=True)
    ]
    revenue, cost = project.actual_value, project.cost
    next_meeting = (
        Meeting.objects.filter(
            project=project, archived_at__isnull=True, status=Meeting.Status.SCHEDULED
        )
        .order_by("date", "id")
        .first()
    )
    return {
        "project": {
            "id": project.pk,
            "name": project.name,
            "description": project.description,
            "status": project.status,
            "start_date": project.start_date.isoformat(),
            "due_date": project.due_date.isoformat(),
            "is_overdue": (
                project.status != Project.Status.COMPLETED
                and project.due_date < timezone.localdate()
            ),
            "client": {"id": project.client_id, "name": project.client.name},
        },
        "completion": completion,
        "health": {"label": health_label, "level": health_level},
        "digital_employees": digital_employees,
        "journey": {"current_phase": current_phase, "phases": journey},
        "ai_score": ai_score_snapshot(project),
        "milestones": milestones,
        "documents": documents,
        "meetings": meetings,
        "pendencias": pendencias,
        "next_meeting": (
            {"id": next_meeting.pk, "title": next_meeting.title, "date": next_meeting.date.isoformat()}
            if next_meeting
            else None
        ),
        "roi": {
            "revenue": float(revenue),
            "cost": float(cost),
            "net": float(revenue - cost),
            "roi": float((revenue - cost) / cost) if cost else None,
        },
        "resultados": {
            "conclusao_pct": completion,
            "marcos_total": len(milestones),
            "marcos_done": done,
            "atrasados": overdue,
            "no_prazo_pct": on_time_pct,
            "status": project.status,
        },
    }


def _post(url: str, body: bytes, signature: str) -> None:
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Biahflow-Signature": f"sha256={signature}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            response.read()
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:  # pragma: no cover
        logger.warning("Falha ao entregar webhook ao portal do cliente: %s", exc)


def emit(event: str, object_type: str, project_id: int | None) -> None:
    """Agenda a entrega de um webhook fino ao portal após o commit da transação.

    Best-effort e não bloqueante — mas **sem rede de segurança automática**: o portal tem a task
    de backfill (`sync_biahflow_project`) e não a agenda, então uma entrega perdida só se recupera
    pelo próximo evento do mesmo projeto ou por backfill manual. Vale a pena emitir em todo caminho
    que muda o projeto, e não contar com reconciliação. Não faz nada quando a integração não está
    configurada.
    """
    url = settings.PORTAL_WEBHOOK_URL
    secret = settings.PORTAL_WEBHOOK_SECRET
    if not url or not secret or not project_id:
        return
    body = json.dumps({"event": event, "object_type": object_type, "project_id": project_id}).encode()
    signature = sign(secret, body)
    transaction.on_commit(
        lambda: threading.Thread(target=_post, args=(url, body, signature), daemon=True).start()
    )
