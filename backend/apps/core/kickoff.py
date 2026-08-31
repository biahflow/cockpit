"""Kickoff automático na conversão de oportunidade em projeto (RFC 0002, FDD 008).

Ao converter uma oportunidade ganha em projeto, semeamos um cronograma inicial
(marcos + tarefas de um template) dentro da transação e, após o commit, disparamos os
efeitos externos best-effort: pasta no Drive (se ligado), e-mail e notificação de kickoff.
Nada aqui bloqueia a conversão — os efeitos externos são tolerantes a falha.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from django.core.mail import send_mail

from . import drive, notifications

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .models import Project

# Cronograma padrão: cada marco tem um deslocamento em dias a partir do início e suas tarefas.
KICKOFF_TEMPLATE: list[dict] = [
    {"title": "Kickoff e alinhamento", "offset": 7,
     "tasks": ["Agendar reunião de kickoff", "Compartilhar plano de trabalho"]},
    {"title": "Descoberta e planejamento", "offset": 21,
     "tasks": ["Levantar requisitos", "Detalhar cronograma"]},
    {"title": "Execução", "offset": 60, "tasks": ["Iniciar entregas do escopo"]},
    {"title": "Encerramento", "offset": 90,
     "tasks": ["Revisar entregáveis", "Coletar feedback do cliente"]},
]

# Um cronograma por degrau da escada FDE: a Qualification Call dura dias e não merece os 90
# do PROVE. Projetos sem nível (ou de serviço avulso) caem no template padrão.
#
# Os textos carregam a metodologia (ADR 0030, `docs/metodologia-fde.md`), e há três lugares em
# que isso não é decoração:
#
# - o Discovery Sprint **termina em Executive Readout**, porque é lá que o custo do estado
#   atual e o ranking por Opportunity Score chegam ao cliente. Sprint pago sem readout é
#   trabalho feito que ninguém viu;
# - a Feasibility define a **meta antes** de rodar a amostra, e o PROVE registra baseline e
#   critérios **antes** de construir. Critério definido depois do resultado não é critério, é
#   narrativa — e é a regra que dá credibilidade ao método inteiro;
# - o gate de saída é tarefa explícita nos dois, com as saídas nomeadas — e são **vocabulários
#   diferentes** (ADR 0053): a Feasibility responde "a tecnologia consegue?" (GO / CONDITIONAL GO
#   / REDESIGN / NO-GO) e o PROVE responde "funcionou em produção controlada?" (SCALE / ITERATE /
#   STOP). O template do PROVE já dizia isso antes de a rota aceitar; desde a ADR 0053 as duas
#   coisas concordam. Gate que não vira item de trabalho é gate que não acontece.
#
# O template padrão continua genérico: serviço avulso não é PROVE.
KICKOFF_TEMPLATES: dict[str, list[dict]] = {
    "qualification_call": [
        {"title": "Qualification Call", "offset": 3,
         "tasks": ["Realizar a call de qualificação (30–45 min)",
                   "Registrar o fit e o próximo passo (avançar para Discovery ou NO-GO)"]},
    ],
    "discovery_sprint": [
        {"title": "Discovery", "offset": 3,
         "tasks": ["Agendar a sessão de discovery", "Mapear o processo com o P-S-D-T-E-R",
                   "Registrar a transcrição da reunião"]},
        {"title": "Baseline e priorização", "offset": 5,
         "tasks": ["Apurar o custo do estado atual",
                   "Rotular os achados (fato / hipótese / desconhecido)",
                   "Calcular o Opportunity Score de cada processo"]},
        {"title": "Executive Readout", "offset": 7,
         "tasks": ["Apresentar o custo do estado atual e o ranking por Opportunity Score",
                   "Registrar o próximo passo recomendado (Feasibility ou PROVE)"]},
    ],
    "feasibility": [
        {"title": "Definição do teste", "offset": 5,
         "tasks": ["Definir a meta **antes** de rodar a amostra",
                   "Selecionar uma amostra real representativa"]},
        {"title": "Execução e classificação", "offset": 15,
         "tasks": ["Rodar a tecnologia contra a amostra",
                   "Classificar cada falha em E1–E5",
                   "Calcular o Ceiling de Input"]},
        {"title": "Decision gate", "offset": 21,
         "tasks": ["Avaliar o T.O.E. pelo elo mais fraco, não pela média",
                   "Registrar o gate (GO / CONDITIONAL GO / REDESIGN / NO-GO)"]},
    ],
    "prove": [
        {"title": "Charter e baseline", "offset": 7,
         "tasks": ["Registrar o baseline e os critérios de sucesso antes de construir",
                   "Definir a meta por KPI e o sentido (menor é melhor?)"]},
        {"title": "Construção", "offset": 30,
         "tasks": ["Construir o piloto", "Integrar com a operação"]},
        {"title": "Produção controlada", "offset": 60,
         "tasks": ["Rodar em produção controlada",
                   "Registrar ao menos 10 casos reais (abaixo disso o scorecard não decide)"]},
        {"title": "Decision gate", "offset": 90,
         "tasks": ["Preencher o scorecard (baseline · meta · medido)",
                   "Registrar a decisão SCALE / ITERATE / STOP",
                   "Coletar feedback do cliente"]},
    ],
    "scale": [
        {"title": "Plano de escala", "offset": 14,
         "tasks": ["Definir o escopo de expansão a partir do que o PROVE sustentou",
                   "Dimensionar operação e suporte"]},
        {"title": "Rollout", "offset": 60,
         "tasks": ["Colocar em produção plena", "Treinar a operação"]},
        {"title": "Captura de valor", "offset": 120,
         "tasks": ["Atualizar o Value Ledger do cliente",
                   "Registrar o caso na biblioteca (prova social para vender o próximo)"]},
    ],
    "transformation": [
        {"title": "Onboarding da parceria", "offset": 14,
         "tasks": ["Definir o ritmo da Monthly Transformation Review",
                   "Abrir o Opportunity Backlog da conta"]},
        {"title": "Primeira revisão mensal", "offset": 30,
         "tasks": ["Revisar o Value Ledger com o cliente",
                   "Priorizar a próxima oportunidade da conta"]},
    ],
}


def template_for(project: Project) -> list[dict]:
    """Escolhe o cronograma inicial pelo nível de produto do projeto."""
    tier = project.service.tier if project.service else ""
    return KICKOFF_TEMPLATES.get(tier, KICKOFF_TEMPLATE)


def seed_work_items(project: Project) -> tuple[int, int]:
    """Cria marcos e tarefas do template, com prazos limitados à janela do projeto."""
    from .models import Milestone, Task

    milestones = tasks = 0
    for spec in template_for(project):
        due = min(project.start_date + timedelta(days=spec["offset"]), project.due_date)
        milestone = Milestone.objects.create(
            project=project, title=spec["title"], owner=project.owner, due_date=due
        )
        milestones += 1
        for task_title in spec["tasks"]:
            Task.objects.create(
                project=project, title=task_title, owner=project.owner,
                due_date=due, milestone=milestone,
            )
            tasks += 1
    return milestones, tasks


def _send_kickoff_email(project: Project) -> None:
    recipient = project.owner.email
    if not recipient:
        return
    send_mail(
        f"Kickoff do projeto {project.name}",
        f"O projeto '{project.name}' foi criado a partir de uma oportunidade ganha.\n\n"
        f"Cliente: {project.engagement.account.name}\n"
        f"Período: {project.start_date} a {project.due_date}\n\n"
        f"Um cronograma inicial de marcos e tarefas já foi criado para revisão.",
        None,
        [recipient],
        fail_silently=True,
    )


def finalize(project: Project) -> None:
    """Efeitos externos best-effort do kickoff (executar após o commit da conversão)."""
    try:
        drive.ensure_project_folder(project)
    except Exception:  # noqa: BLE001 - best-effort: o kickoff não falha porque o Drive caiu
        # Best-effort é a decisão certa; o `pass` mudo é que não era. Sem log, o projeto ficava
        # **sem pasta e ninguém sabendo** — e a pasta é onde a entrega guarda tudo depois.
        logger.exception("kickoff: pasta do Drive não criada para o projeto %s", project.pk)
    _send_kickoff_email(project)
    notifications.notify(
        [project.owner], "kickoff",
        f"Projeto '{project.name}' criado a partir da oportunidade ganha.",
        f"/projetos/{project.id}",
        # No-op aqui pelo invariante `_owner_is_always_a_member`, mas a regra é "URL de projeto ⇒
        # guarda": exceção que depende de um invariante alheio é o que apodrece primeiro.
        project=project,
    )
