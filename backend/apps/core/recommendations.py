"""Recomendações heurísticas (sempre revisáveis por uma pessoa).

Sugestões derivadas dos dados atuais; nunca executam ação — só apontam onde agir.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone


def build_recommendations() -> list[dict[str, Any]]:
    from .models import Client, Opportunity, PipelineStage, Project

    today = timezone.localdate()
    recs: list[dict[str, Any]] = []

    # Clientes com projetos mas sem oportunidade aberta → oportunidade de novo negócio.
    open_kind = PipelineStage.Kind.OPEN
    for client in Client.objects.filter(archived_at__isnull=True):
        has_project = Project.objects.filter(client=client, archived_at__isnull=True).exists()
        has_open = Opportunity.objects.filter(
            client=client, archived_at__isnull=True, stage__kind=open_kind
        ).exists()
        if has_project and not has_open:
            recs.append({
                "kind": "upsell",
                "label": f"Novo negócio com {client.name}",
                "detail": "Cliente ativo sem oportunidade aberta — vale um contato.",
                "url": f"/clientes/{client.pk}",
            })

    # Oportunidades abertas paradas há mais de 30 dias → follow-up.
    stale_before = timezone.now() - timedelta(days=30)
    for opportunity in Opportunity.objects.filter(
        archived_at__isnull=True, stage__kind=open_kind, created_at__lt=stale_before
    ).select_related("client"):
        recs.append({
            "kind": "followup",
            "label": f"Follow-up: {opportunity.title}",
            "detail": "Oportunidade aberta parada há mais de 30 dias.",
            "url": "/comercial",
        })

    # Projetos ativos vencendo em até 7 dias → atenção.
    soon = today + timedelta(days=7)
    for project in Project.objects.filter(
        archived_at__isnull=True, due_date__gte=today, due_date__lte=soon
    ).exclude(status="completed"):
        recs.append({
            "kind": "deadline",
            "label": f"Prazo próximo: {project.name}",
            "detail": f"Vence em {(project.due_date - today).days} dia(s).",
            "url": f"/projetos/{project.pk}",
        })

    return recs
