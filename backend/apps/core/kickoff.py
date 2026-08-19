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

# Um cronograma por nível de produto: o Discovery Express dura uma semana e não merece os
# 90 dias da implantação. Projetos sem nível (ou de serviço avulso) caem no template padrão.
# Os textos carregam a leitura FDE dos níveis (ADR 0030, `docs/metodologia-fde.md`): o
# Discovery + Assessment fecha com o gate recomendado, e a implantação é o PROVE — baseline e
# critérios de sucesso antes de construir, evidência de produção controlada e decision gate
# no fim. O template padrão continua genérico: serviço avulso não é PROVE.
KICKOFF_TEMPLATES: dict[str, list[dict]] = {
    "discovery_express": [
        {"title": "Discovery", "offset": 7,
         "tasks": ["Agendar a sessão de discovery", "Registrar a transcrição da reunião",
                   "Compartilhar o resumo com os próximos passos"]},
    ],
    "discovery_assessment": [
        {"title": "Discovery", "offset": 7,
         "tasks": ["Agendar a sessão de discovery", "Registrar a transcrição da reunião"]},
        {"title": "Assessment e recomendações", "offset": 21,
         "tasks": ["Gerar o assessment de maturidade", "Priorizar as recomendações",
                   "Apresentar o plano de ação",
                   "Registrar o próximo passo recomendado (gate: PROVE ou Feasibility)"]},
    ],
    "implantacao": [
        {"title": "Kickoff e alinhamento", "offset": 7,
         "tasks": ["Agendar reunião de kickoff", "Compartilhar plano de trabalho",
                   "Registrar o baseline e os critérios de sucesso antes de construir"]},
        {"title": "Descoberta e planejamento", "offset": 21,
         "tasks": ["Levantar requisitos", "Detalhar cronograma"]},
        {"title": "Execução em produção controlada", "offset": 60,
         "tasks": ["Iniciar entregas do escopo"]},
        {"title": "Encerramento", "offset": 90,
         "tasks": ["Revisar entregáveis contra os critérios de sucesso",
                   "Registrar a evidência de produção controlada e o decision gate",
                   "Coletar feedback do cliente"]},
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
        f"Cliente: {project.client.name}\n"
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
