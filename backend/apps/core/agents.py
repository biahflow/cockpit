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

from . import satisfaction as satisfaction_module

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
    from .models import CommercialOpportunity, Lead, PipelineStage

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
        CommercialOpportunity.objects.filter(
            active, stage__kind=PipelineStage.Kind.OPEN, created_at__lt=stale_before
        ).select_related("account")[:20]
    )
    if stale:
        lines.append("Oportunidades abertas paradas há mais de 30 dias:")
        lines += [f"- {o.title} ({o.account.name}), valor {o.estimated_value}" for o in stale]
    lines.append(f"Leads novos (não trabalhados): {Lead.objects.filter(active, status=Lead.Status.NEW).count()}")
    return "\n".join(lines)


# Teto por bloco, como no digest: contexto que vira parede de texto custa token e não ajuda o
# modelo — a linha final diz quantos ficaram de fora.
_MAX_POR_BLOCO = 10


def build_delivery_context(user: User) -> str:
    """Contexto do agente de Entrega: o risco de cada projeto, **o que está atrasado**, os riscos
    declarados que seguem abertos e a satisfação vigente de cada cliente.

    A parte dos itens nasceu da rodada 2 da homologação (FDD 024): perguntado "o que está
    atrasado?", o agente respondia que não tinha os detalhes — e estava certo, porque o contexto
    era um resumo de resumos (`risco médio — Itens atrasados`) sem dizer **quais**. A pergunta mais
    óbvia da área não tinha resposta.

    O bloco de riscos veio com a FDD 034, e fecha a mesma lacuna por outro lado: o escore do
    `risk.py` só enxerga o que **já** escorregou (prazo estourado, item parado), enquanto o Risk
    Register guarda o que a equipe teme e ainda não aconteceu. Perguntado "quais são os riscos
    deste portfólio?", o agente respondia com sintoma; agora responde também com o que foi
    declarado — que é o que a Delivery Sync semanal da metodologia pede.

    O bloco de satisfação entrou com a FDD 037 e é o único que fala do **cliente** e não da
    entrega: os três acima medem o nosso trabalho, e este diz se a outra parte da relação está
    conosco. Entram as duas fontes, `declarada` e `percebida` — ao contrário do Health Score e da
    régua de cobrança, que leem só a declarada (ADR 0032), porque aqui nada vira número.

    O recorte é o mesmo de antes e não afrouxa: tudo sai de `visible_to`, que é a única expressão
    da regra (ADR 0010). O que muda é que o vazamento possível deixou de ser o nome do projeto e
    passou a ser o título do item — por isso há um teste de regressão para cada um, e o risco
    declarado e a satisfação ganharam o seu.
    """
    from . import risk
    from .models import Milestone, Project, Risco, Task

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
            for item in atrasados[:_MAX_POR_BLOCO]
        ]
        if len(atrasados) > _MAX_POR_BLOCO:
            lines.append(f"- ... e mais {len(atrasados) - _MAX_POR_BLOCO}")

    # Só os abertos: mitigado, aceito e materializado já foram tratados, e enchê-los aqui gastaria
    # o teto do bloco com o que não pede ação. A mitigação entra junto porque é ela que transforma
    # "há um risco" em "há um risco e alguém está fazendo algo" — sem isso o agente só repete o
    # medo de volta.
    riscos = list(
        Risco.objects.filter(
            project_id__in=ids, archived_at__isnull=True, status=Risco.Status.OPEN
        ).select_related("project")
    )
    if riscos:
        lines.append("Riscos abertos (registro do projeto):")
        for risco in riscos[:_MAX_POR_BLOCO]:
            mitigacao = risco.mitigation.strip() or "sem mitigação registrada"
            lines.append(
                f"- {risco.title} — {risco.project.name} "
                f"(probabilidade {risco.get_probability_display().lower()}, "
                f"impacto {risco.get_impact_display().lower()}; mitigação: {mitigacao})"
            )
        if len(riscos) > _MAX_POR_BLOCO:
            lines.append(f"- ... e mais {len(riscos) - _MAX_POR_BLOCO}")

    # Satisfação vigente (FDD 037), e aqui entram **as duas fontes**.
    #
    # O Health Score e a régua de cobrança leem só a `declarada`, porque as duas produzem número e
    # comportamento (ADR 0032). Este bloco é texto para uma pessoa ler: a leitura de quem entrega é
    # justamente o que existe **antes** de alguém ter perguntado ao cliente, e é ela que faz alguém
    # perguntar. Esconder a percebida aqui apagaria o único uso legítimo dela.
    #
    # Por cliente e não por projeto: a satisfação é da relação. O recorte continua saindo de
    # `visible_to` (ADR 0010), pela lista `active` que o bloco de riscos já usa.
    vigentes = satisfaction_module.vigentes_por_cliente(
        {project.engagement.account_id for project in active}, hoje
    )
    if vigentes:
        lines.append("Satisfação registrada (o mais recente por cliente, últimos 90 dias):")
        registros = sorted(vigentes.values(), key=lambda registro: registro.account.name)
        for registro in registros[:_MAX_POR_BLOCO]:
            nota = registro.note.strip() or "sem nota"
            lines.append(
                f"- {registro.account.name}: {registro.get_nivel_display().lower()} "
                f"({registro.get_fonte_display().lower()}, em {registro.happened_on}) — {nota}"
            )
        if len(registros) > _MAX_POR_BLOCO:
            lines.append(f"- ... e mais {len(registros) - _MAX_POR_BLOCO}")
    return "\n".join(lines)


def build_finance_context(user: User) -> str:
    from .models import Project

    active = Project.objects.filter(archived_at__isnull=True)
    revenue = active.aggregate(v=Sum("actual_value"))["v"] or Decimal("0")
    cost = active.aggregate(v=Sum("cost"))["v"] or Decimal("0")
    lines = [f"Financeiro (projetos ativos): receita {revenue}, custo {cost}, resultado {revenue - cost}.",
             "ROI por cliente:"]
    for row in active.values("engagement__account__name").annotate(rev=Sum("actual_value"), c=Sum("cost")).order_by("-rev")[:15]:
        rev = row["rev"] or Decimal("0")
        client_cost = row["c"] or Decimal("0")
        roi = round(float((rev - client_cost) / client_cost), 2) if client_cost else None
        lines.append(f"- {row['engagement__account__name']}: receita {rev}, custo {client_cost}, ROI {roi if roi is not None else 'n/d'}")
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
