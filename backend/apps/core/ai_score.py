"""AI Score de maturidade/oportunidade de IA por cliente (Fase 4 — FDD 014, RFC 0002).

A partir da transcrição de uma reunião (as mesmas etapas de Discovery/Assessment — FDD 007),
a IA produz um índice estruturado de **maturidade** e **oportunidade** de IA, com dimensões e
um resumo — rascunho para revisão humana, nunca publicado sozinho. Reusa `ai.py` e é auditado
em `AiInteraction`. Só cruza ao portal do cliente depois que alguém liga `ai_score_reviewed`.

Espelha `qualification.py`: prompt pede JSON, `_parse` tolerante, clamp 0–100, persistência dos
campos `ai_*` (aqui no `Project`, não no `Lead`) e registro em `AiInteraction`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from . import ai

if TYPE_CHECKING:
    from .models import Meeting, User

_SYSTEM = (
    "Você é o agente de Maturidade de IA da consultoria. Use APENAS a transcrição fornecida. "
    "Responda SOMENTE com um JSON válido, sem texto ao redor, no formato: "
    '{"maturity": 0-100, "opportunity": 0-100, '
    '"dimensions": [{"label": "...", "score": 0-100}], "summary": "..."}. '
    "maturity mede o quanto o cliente já usa IA hoje; opportunity mede o potencial de ganho com "
    "IA; dimensions detalha eixos como Dados, Processos, Pessoas/Cultura e Ferramentas; summary é "
    "um rascunho para revisão humana (nunca afirme ter executado ações)."
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


def _clamp(value: Any) -> int | None:
    """Converte para inteiro 0–100; None quando ausente ou inválido."""
    if value is None:
        return None
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return None


def _dimensions(raw: Any) -> list[dict[str, Any]]:
    """Normaliza a lista de dimensões: só entradas com label e score válido (0–100)."""
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        score = _clamp(item.get("score"))
        if label and score is not None:
            result.append({"label": label, "score": score})
    return result


# Teto de saída. A rodada 2 mediu **178** tokens de saída contra o modelo real; 500 dá folga de
# quase 3x para uma transcrição mais rica sem deixar de ser teto. Cabe aqui, e não num teto global,
# porque a saída tem forma fixa: dois inteiros, uma lista curta de dimensões e um resumo.
_MAX_TOKENS = 500


def score_meeting(meeting: Meeting, user: User | None = None) -> dict[str, Any]:
    """Gera o AI Score a partir da transcrição da reunião, persiste no projeto e audita.

    Guardas (flag/limite/transcrição) ficam na view, como em Discovery/Assessment. Grava sempre
    `ai_score_reviewed=False`: publicar ao cliente exige revisão humana explícita.
    """
    from .models import AiInteraction

    context = ai.build_meeting_context(meeting)
    text, usage = ai.complete(_SYSTEM, context, max_tokens=_MAX_TOKENS)
    data = _parse(text)

    project = meeting.project
    project.ai_maturity = _clamp(data.get("maturity"))
    project.ai_opportunity = _clamp(data.get("opportunity"))
    project.ai_dimensions = _dimensions(data.get("dimensions"))
    project.ai_score_summary = str(data.get("summary", ""))
    project.ai_scored_at = timezone.now()
    project.ai_score_reviewed = False
    project.ai_score_meeting = meeting
    project.save(update_fields=[
        "ai_maturity", "ai_opportunity", "ai_dimensions", "ai_score_summary",
        "ai_scored_at", "ai_score_reviewed", "ai_score_meeting", "updated_at",
    ])

    AiInteraction.objects.create(
        user=user, feature="ai_score", project=project,
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
    )

    return {
        "maturity": project.ai_maturity,
        "opportunity": project.ai_opportunity,
        "dimensions": project.ai_dimensions,
        "summary": project.ai_score_summary,
        "scored_at": project.ai_scored_at.isoformat(),
        "reviewed": project.ai_score_reviewed,
    }
