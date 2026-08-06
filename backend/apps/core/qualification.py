"""Qualificação de leads por IA (FDD 013, RFC 0002).

Ao entrar um lead pelo intake do site, a IA produz um rascunho de qualificação (fit, score,
resumo e próximo passo sugerido) — para revisão humana, nunca descarta sozinho. Reusa `ai.py`
e é auditado em `AiInteraction`. Desligado (`AI_ENABLED=false`), não qualifica e o lead segue
para contato manual.

O corte para liberar o agendamento é `settings.BOOKING_MIN_FIT` (default: high+medium qualificam).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone

from . import ai

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .models import Lead

# Ordem de fit para comparar com o corte de agendamento.
_FIT_ORDER = {"low": 1, "medium": 2, "high": 3}

_SYSTEM = (
    "Você é um SDR da consultoria que qualifica leads de entrada. Use APENAS os dados fornecidos. "
    "Responda SOMENTE com um JSON válido, sem texto ao redor, no formato: "
    '{"fit": "high|medium|low", "score": 0-100, "summary": "...", "recommended_action": "..."}. '
    "fit e score refletem o quão promissor é o lead; summary e recommended_action são um rascunho "
    "para revisão humana (nunca afirme ter executado ações)."
)


def _parse(text: str) -> dict:
    """Extrai o JSON da resposta do modelo, tolerando cercas de código ou texto ao redor."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        data = json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def qualifies_for_booking(fit: str) -> bool:
    minimum = _FIT_ORDER.get(getattr(settings, "BOOKING_MIN_FIT", "medium"), 2)
    return _FIT_ORDER.get(fit, 0) >= minimum


def qualify_lead(lead: Lead, answers: dict | None = None) -> bool:
    """Qualifica o lead pela IA, persiste o resultado e retorna se passou do corte de agendamento.

    No-op (retorna False) quando a IA está desligada — o lead fica sem qualificação para triagem
    manual.
    """
    from .models import AiInteraction
    from .models import Lead as LeadModel

    if not ai.is_enabled():
        return False

    context = ai.build_lead_context(lead, answers)
    try:
        text, usage = ai.complete(_SYSTEM, context)
    except Exception:  # noqa: BLE001 - o formulário público não pode cair com o fornecedor
        # Isto roda **dentro do POST público** do formulário do site. Sem a guarda, um 429, um
        # timeout ou uma chave vencida da OpenAI viravam 500 para o visitante — e o `Lead` já
        # tinha sido gravado antes da chamada, então ele via um erro para um cadastro que na
        # verdade funcionou. Sem qualificação o lead cai na triagem manual, que é o mesmo
        # comportamento de quando a IA está desligada.
        logger.exception("qualificação do lead %s falhou; segue para triagem manual", lead.pk)
        return False
    data = _parse(text)

    fit = str(data.get("fit", "")).lower()
    if fit not in _FIT_ORDER:
        fit = ""
    raw_score = data.get("score")
    score: int | None = None
    if raw_score is not None:
        try:
            score = max(0, min(100, int(raw_score)))
        except (TypeError, ValueError):
            score = None

    lead.ai_fit = fit
    lead.ai_score = score
    lead.ai_summary = str(data.get("summary", ""))
    lead.ai_recommended_action = str(data.get("recommended_action", ""))
    lead.qualified_at = timezone.now()
    if fit:
        lead.status = LeadModel.Status.QUALIFIED if qualifies_for_booking(fit) else LeadModel.Status.CONTACTED
    lead.save(update_fields=[
        "ai_fit", "ai_score", "ai_summary", "ai_recommended_action",
        "qualified_at", "status", "updated_at",
    ])

    AiInteraction.objects.create(
        user=None, lead=lead, feature="lead_qualification",
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
    )

    return bool(fit) and qualifies_for_booking(fit)
