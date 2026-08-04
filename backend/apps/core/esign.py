"""Esqueleto de assinatura eletrônica, agnóstico de fornecedor (flag `ESIGN_ENABLED`).

O adapter concreto (Clicksign/DocuSign) será preenchido quando o fornecedor for escolhido;
por ora, apenas registra a intenção. Desligado por padrão.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from . import flags

if TYPE_CHECKING:
    from .models import Document

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    return flags.is_enabled("esign")


def send_for_signature(document: Document, signer_email: str) -> str:  # pragma: no cover - integração futura
    """Envia o documento para assinatura e retorna a referência do fornecedor.

    Enquanto não há fornecedor integrado, só registra a solicitação e retorna vazio.
    """
    logger.info(
        "Solicitação de assinatura (provider=%s) doc=%s signer=%s",
        settings.ESIGN_PROVIDER or "n/d", document.pk, signer_email,
    )
    return ""


def remind_pending(document: Document) -> int:
    """Envia lembrete a cada signatário ainda pendente do documento e retorna quantos.

    Um provedor homologado (Clicksign/DocuSign) atualizaria o status por webhook; enquanto
    isso, o e-mail de lembrete é o gatilho manual (revisão humana) que fecha o laço do esign.
    """
    from .models import SignatureRequest

    pending = document.signature_requests.filter(status=SignatureRequest.Status.PENDING)
    reminded = 0
    for signature in pending:
        send_mail(
            f"Lembrete de assinatura — {document.original_name}",
            f"Consta pendente a sua assinatura do documento '{document.original_name}'.\n"
            f"Por favor, conclua a assinatura eletrônica.",
            None,
            [signature.signer_email],
            fail_silently=True,
        )
        signature.reminded_at = timezone.now()
        signature.save(update_fields=["reminded_at"])
        reminded += 1
    return reminded
