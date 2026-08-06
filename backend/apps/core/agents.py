"""Motor de agentes de IA especializados por área (ADR 0006 / RFC 0002).

Cada agente tem um escopo de papéis (RBAC) e um construtor de contexto que só lê os dados da
sua área — ferramentas limitadas, anti-vazamento. Reusa `ai.py`; a resposta é sempre para
**revisão humana** (nunca executa ação). Só faz sentido com `AI_ENABLED`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import Count, Q, Sum
from django.utils import timezone

if TYPE_CHECKING:
    from .models import User


@dataclass(frozen=True)
class Agent:
    key: str
    label: str
    roles: tuple[str, ...]
    system: str
    # Recebe o usuário porque o contexto de entrega é recortado pela equipe do projeto
    # (RFC 0003): sem isso, o agente lia o nome e o risco de todo projeto ativo da casa.
    build_context: Callable[[User], str]


_BASE = (
    "Você é um copiloto interno da consultoria. Responda em português, objetivo e acionável, "
    "usando APENAS os dados fornecidos. Deixe claro quando algo é sugestão para revisão humana; "
    "nunca afirme ter executado ações."
)


def build_commercial_context(user: User) -> str:
    from .models import Lead, Opportunity, PipelineStage

    active = Q(archived_at__isnull=True)
    lines = ["Resumo comercial.", "Pipeline por etapa:"]
    stages = PipelineStage.objects.annotate(
        n=Count("opportunities", filter=Q(opportunities__archived_at__isnull=True)),
        total=Sum("opportunities__estimated_value", filter=Q(opportunities__archived_at__isnull=True)),
    ).order_by("position")
    for stage in stages:
        lines.append(f"- {stage.name} [{stage.kind}]: {stage.n} oportunidade(s), total estimado {stage.total or 0}")
    stale_before = timezone.now() - timedelta(days=30)
    stale = list(
        Opportunity.objects.filter(
            active, stage__kind=PipelineStage.Kind.OPEN, created_at__lt=stale_before
        ).select_related("client")[:20]
    )
    if stale:
        lines.append("Oportunidades abertas paradas há mais de 30 dias:")
        lines += [f"- {o.title} ({o.client.name}), valor {o.estimated_value}" for o in stale]
    lines.append(f"Leads novos (não trabalhados): {Lead.objects.filter(active, status=Lead.Status.NEW).count()}")
    return "\n".join(lines)


# Teto por bloco, como no digest: contexto que vira parede de texto custa token e não ajuda o
# modelo — a linha final diz quantos ficaram de fora.
_MAX_ATRASADOS = 10


def build_delivery_context(user: User) -> str:
    """Contexto do agente de Entrega: o risco de cada projeto **e o que está atrasado**.

    A parte dos itens nasceu da rodada 2 da homologação (FDD 024): perguntado "o que está
    atrasado?", o agente respondia que não tinha os detalhes — e estava certo, porque o contexto
    era um resumo de resumos (`risco médio — Itens atrasados`) sem dizer **quais**. A pergunta mais
    óbvia da área não tinha resposta.

    O recorte é o mesmo de antes e não afrouxa: tudo sai de `visible_to`, que é a única expressão
    da regra (ADR 0010). O que muda é que o vazamento possível deixou de ser o nome do projeto e
    passou a ser o título do item — por isso há um teste de regressão para cada um.
    """
    from . import risk
    from .models import Milestone, Project, Task

    # Materializado: `assessments` e a busca de atrasados usam a mesma lista, e iterar o queryset
    # duas vezes o consultaria duas vezes.
    active = list(
        Project.objects.visible_to(user)
        .filter(archived_at__isnull=True)
        .exclude(status=Project.Status.COMPLETED)
    )
    assessments = sorted(
        (risk.assess_project(project) for project in active), key=lambda a: a["score"], reverse=True
    )
    lines = ["Resumo de entrega (projetos ativos, por risco):"]
    for assessment in assessments[:15]:
        signals = "; ".join(s["label"] for s in assessment["signals"]) or "sem sinais"
        lines.append(f"- {assessment['name']}: risco {assessment['level']} (escore {assessment['score']}) — {signals}")
    if not assessments:
        lines.append("- nenhum projeto ativo")

    hoje = timezone.localdate()
    ids = [project.pk for project in active]
    for label, adjetivo, model in (("Marcos", "atrasados", Milestone), ("Tarefas", "atrasadas", Task)):
        atrasados = list(
            model.objects.filter(project_id__in=ids, archived_at__isnull=True, due_date__lt=hoje)
            .exclude(status=model.Status.DONE)
            .select_related("project")
            .order_by("due_date")
        )
        if not atrasados:
            continue
        lines.append(f"{label} {adjetivo}:")
        # Mesma forma do digest (`- título (venceu data)`) mais o projeto, que aqui é necessário:
        # o digest fala de um contexto pessoal, este agente olha a carteira inteira e "qual
        # projeto" é metade da resposta.
        lines += [
            f"- {item.title} — {item.project.name} (venceu {item.due_date})"
            for item in atrasados[:_MAX_ATRASADOS]
        ]
        if len(atrasados) > _MAX_ATRASADOS:
            lines.append(f"- ... e mais {len(atrasados) - _MAX_ATRASADOS}")
    return "\n".join(lines)


def build_finance_context(user: User) -> str:
    from .models import Project

    active = Project.objects.filter(archived_at__isnull=True)
    revenue = active.aggregate(v=Sum("actual_value"))["v"] or Decimal("0")
    cost = active.aggregate(v=Sum("cost"))["v"] or Decimal("0")
    lines = [f"Financeiro (projetos ativos): receita {revenue}, custo {cost}, resultado {revenue - cost}.",
             "ROI por cliente:"]
    for row in active.values("client__name").annotate(rev=Sum("actual_value"), c=Sum("cost")).order_by("-rev")[:15]:
        rev = row["rev"] or Decimal("0")
        client_cost = row["c"] or Decimal("0")
        roi = round(float((rev - client_cost) / client_cost), 2) if client_cost else None
        lines.append(f"- {row['client__name']}: receita {rev}, custo {client_cost}, ROI {roi if roi is not None else 'n/d'}")
    return "\n".join(lines)


AGENTS: dict[str, Agent] = {
    "comercial": Agent(
        "comercial", "Agente Comercial", ("admin", "sales"),
        _BASE + " Foco: pipeline comercial, oportunidades e leads.", build_commercial_context,
    ),
    "entrega": Agent(
        "entrega", "Agente de Entrega", ("admin", "delivery"),
        _BASE + " Foco: execução de projetos, marcos, tarefas e riscos.", build_delivery_context,
    ),
    "financeiro": Agent(
        "financeiro", "Agente Financeiro", ("admin",),
        _BASE + " Foco: receita, custo e ROI.", build_finance_context,
    ),
}


def can_use(agent: Agent, user: User) -> bool:
    return user.is_admin_role or user.role in agent.roles
