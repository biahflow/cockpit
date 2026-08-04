"""Resumo diário (digest) por IA — Go-live/Hypercare (RFC 0002, FDD 010).

Reúne os itens do dia de cada usuário (marcos/tarefas atrasados e a vencer) e envia um
resumo por e-mail. Com a IA ligada, o texto é redigido pelo modelo (auditado em
`AiInteraction`); desligada, cai no resumo estruturado. Tudo atrás da flag `email`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.core.mail import send_mail
from django.utils import timezone

from . import ai, flags

if TYPE_CHECKING:
    from .models import User

_SYSTEM = (
    "Você escreve um resumo diário curto e acionável em português a partir dos itens "
    "fornecidos (marcos e tarefas). Priorize o que está atrasado; use apenas o material dado."
)


def build_user_digest_context(user: User) -> str:
    """Itens abertos do usuário: atrasados e a vencer em 7 dias. Vazio se não houver nada."""
    from .models import Milestone, Task

    today = timezone.localdate()
    soon = today + timedelta(days=7)
    lines: list[str] = []
    for label, model in (("Marcos", Milestone), ("Tarefas", Task)):
        items = list(
            model.objects.filter(owner=user, archived_at__isnull=True).exclude(status=model.Status.DONE)
        )
        overdue = [item for item in items if item.due_date < today]
        upcoming = [item for item in items if today <= item.due_date <= soon]
        if overdue:
            lines.append(f"{label} atrasados:")
            lines += [f"- {item.title} (venceu {item.due_date})" for item in overdue]
        if upcoming:
            lines.append(f"{label} a vencer nos próximos 7 dias:")
            lines += [f"- {item.title} (vence {item.due_date})" for item in upcoming]
    return "\n".join(lines)


def send_daily_digest() -> int:
    """Envia o digest a cada usuário ativo com itens a reportar. Retorna quantos foram enviados."""
    from .models import AiInteraction, User

    if not flags.is_enabled("email"):
        return 0
    sent = 0
    for user in User.objects.filter(is_active=True):
        if not user.email:
            continue
        context = build_user_digest_context(user)
        if not context:
            continue
        if ai.is_enabled():
            text, usage = ai.complete(_SYSTEM, context)
            AiInteraction.objects.create(
                user=user, feature="daily_digest",
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            )
        else:
            text = context
        send_mail("Seu resumo diário — Portal Biahflow", text, None, [user.email], fail_silently=True)
        sent += 1
    return sent
