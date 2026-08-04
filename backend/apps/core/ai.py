"""Camada de IA (OpenAI) atrás de flag.

Mesma estratégia do `apps/core/drive.py`: o SDK é importado de forma lazy e só é chamado
quando `AI_ENABLED`. As funções de montagem de contexto e o limite de uso são puras e
testáveis; a chamada ao modelo fica fora da cobertura (`# pragma: no cover`).

Antivazamento: o contexto passado ao modelo contém apenas dados do recurso em questão
(nunca o conteúdo binário dos documentos — só os nomes) e o system prompt orienta o modelo
a responder somente com base no material fornecido.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone

from . import flags

if TYPE_CHECKING:
    from .models import Lead, Meeting, Opportunity, Project, User

# Limite de caracteres da transcrição enviada ao modelo (controle de tokens/custo).
MEETING_TRANSCRIPT_LIMIT = 12000


def is_enabled() -> bool:
    return flags.is_enabled("ai")


def within_daily_limit(user: User) -> bool:
    from .models import AiInteraction

    today = timezone.localdate()
    used = AiInteraction.objects.filter(user=user, created_at__date=today).count()
    return used < settings.AI_DAILY_LIMIT


def build_project_context(project: Project) -> str:
    from .models import Document, Milestone, Task

    lines = [f"Projeto: {project.name}", f"Status: {project.status}"]
    if project.description:
        lines.append(f"Descrição: {project.description}")
    lines.append(f"Período: {project.start_date} a {project.due_date}")

    milestones = Milestone.objects.filter(project=project, archived_at__isnull=True)
    if milestones:
        lines.append("Marcos:")
        lines += [f"- {m.title} [{m.status}] prazo {m.due_date}" for m in milestones]
    tasks = Task.objects.filter(project=project, archived_at__isnull=True)
    if tasks:
        lines.append("Tarefas:")
        lines += [f"- {t.title} [{t.status}] prazo {t.due_date}" for t in tasks]
    documents = Document.objects.filter(project=project, archived_at__isnull=True)
    if documents:
        lines.append("Documentos (nomes): " + ", ".join(d.original_name for d in documents))
    return "\n".join(lines)


def build_meeting_context(meeting: Meeting) -> str:
    """Contexto de uma reunião para Discovery/Assessment: só dados desta reunião."""
    transcript = meeting.transcript.strip()
    if len(transcript) > MEETING_TRANSCRIPT_LIMIT:
        transcript = transcript[:MEETING_TRANSCRIPT_LIMIT] + "\n[transcrição truncada]"
    lines = [
        f"Projeto: {meeting.project.name}",
        f"Reunião: {meeting.title}",
        f"Data: {meeting.date}",
        f"Situação: {meeting.status}",
        "Transcrição:",
        transcript,
    ]
    return "\n".join(lines)


def build_opportunity_context(opportunity: Opportunity) -> str:
    lines = [
        f"Oportunidade: {opportunity.title}",
        f"Cliente: {opportunity.client.name}",
        f"Valor estimado: {opportunity.estimated_value}",
        f"Etapa: {opportunity.stage.name}",
        f"Previsão de fechamento: {opportunity.expected_close_date}",
    ]
    if opportunity.contact:
        lines.append(f"Contato: {opportunity.contact.name}")
    if opportunity.scope:
        lines.append(f"Escopo: {opportunity.scope}")
    return "\n".join(lines)


def build_lead_context(lead: Lead, answers: dict | None = None) -> str:
    """Contexto de um lead para qualificação: só dados deste lead + respostas de triagem."""
    lines = [
        f"Nome: {lead.name}",
        f"E-mail: {lead.email}",
    ]
    if lead.company:
        lines.append(f"Empresa: {lead.company}")
    if lead.phone:
        lines.append(f"Telefone: {lead.phone}")
    if lead.message:
        lines.append(f"Mensagem: {lead.message}")
    for question, answer in (answers or {}).items():
        if answer:
            lines.append(f"{question}: {answer}")
    return "\n".join(lines)


def _client():  # pragma: no cover - I/O com a OpenAI
    from openai import OpenAI

    if settings.AI_BASE_URL:
        return OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.AI_BASE_URL)
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def complete(system: str, user: str) -> tuple[str, dict]:  # pragma: no cover - I/O
    """Chama o modelo e retorna (texto, uso de tokens)."""
    response = _client().chat.completions.create(
        model=settings.AI_MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    usage = response.usage
    return (
        response.choices[0].message.content or "",
        {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0),
            "completion_tokens": getattr(usage, "completion_tokens", 0),
        },
    )
