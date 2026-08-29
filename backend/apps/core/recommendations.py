"""Recomendações heurísticas (sempre revisáveis por uma pessoa).

Sugestões derivadas dos dados atuais; nunca executam ação — só apontam onde agir.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone


def build_recommendations() -> list[dict[str, Any]]:
    from .models import (
        Account,
        CommercialOpportunity,
        ImprovementOpportunity,
        PipelineStage,
        PriorityAssessment,
        Project,
        SolutionHypothesis,
    )

    today = timezone.localdate()
    recs: list[dict[str, Any]] = []
    # `conta -> (avaliação vigente, oportunidade)` da melhor pontuada de cada conta.
    melhores: dict[int, tuple[PriorityAssessment, ImprovementOpportunity]] = {}

    # Clientes com projetos mas sem oportunidade aberta → oportunidade de novo negócio.
    open_kind = PipelineStage.Kind.OPEN
    for account in Account.objects.filter(archived_at__isnull=True):
        has_project = Project.objects.filter(client=account, archived_at__isnull=True).exists()
        has_open = CommercialOpportunity.objects.filter(
            account=account, archived_at__isnull=True, stage__kind=open_kind
        ).exists()
        if has_project and not has_open:
            recs.append({
                "kind": "upsell",
                "label": f"Novo negócio com {account.name}",
                "detail": "Cliente ativo sem oportunidade aberta — vale um contato.",
                "url": f"/contas/{account.pk}",
            })

    # Oportunidades abertas paradas há mais de 30 dias → follow-up.
    stale_before = timezone.now() - timedelta(days=30)
    for opportunity in CommercialOpportunity.objects.filter(
        archived_at__isnull=True, stage__kind=open_kind, created_at__lt=stale_before
    ).select_related("account"):
        recs.append({
            "kind": "followup",
            "label": f"Follow-up: {opportunity.title}",
            "detail": "Oportunidade aberta parada há mais de 30 dias.",
            "url": "/comercial",
        })

    # A oportunidade de melhoria priorizada de maior score, por conta → próximo passo.
    #
    # **Ela lê a `PriorityAssessment` vigente, e não um campo opaco** (issue #68): o número que
    # ordena esta recomendação é o mesmo que a tela mostra, com a fórmula e a versão que o
    # produziram gravadas na linha. `Lead.ai_score` e `Project.ai_opportunity` não servem aqui e
    # o mapa de linguagem §5 explica por quê — o primeiro é score de aquisição, o segundo é
    # maturidade de IA da conta, e nenhum dos dois mede melhoria operacional.
    #
    # "Ainda não virou trabalho" é lido como **sem hipótese de solução escolhida**, que é o único
    # sinal observável nesta fase: a oportunidade não aponta para projeto, e o gate que a
    # transforma em entrega (`FeasibilityAssessment`) é da fase seguinte. Quando ele existir, é
    # esta condição que muda — e é por isso que ela está escrita aqui, e não escondida num filtro.
    for oportunidade in (
        ImprovementOpportunity.objects.filter(
            archived_at__isnull=True, status=ImprovementOpportunity.Status.PRIORITIZED
        )
        .exclude(
            hypotheses__status=SolutionHypothesis.Status.CHOSEN,
            hypotheses__archived_at__isnull=True,
        )
        .select_related("account")
    ):
        vigente = oportunidade.current_assessment
        if vigente is None:
            continue
        melhor = melhores.get(oportunidade.account_id)
        if melhor is None or vigente.score > melhor[0].score:
            melhores[oportunidade.account_id] = (vigente, oportunidade)
    for vigente, oportunidade in melhores.values():
        recs.append({
            "kind": "prioritization",
            "label": f"Próximo passo em {oportunidade.account.name}: {oportunidade.title}",
            "detail": (
                f"Opportunity Score {vigente.score} (v{vigente.version}) — priorizada e ainda "
                "sem hipótese de solução escolhida."
            ),
            "url": f"/contas/{oportunidade.account_id}/priorizacao",
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
