"""Assinatura eletrônica atrás de flag (`esign`), agnóstica de fornecedor (ADR 0007).

Dois lados, no mesmo molde do `tasksync.py`:

- **SAÍDA** (Biahflow → fornecedor): `send_for_signature()` cria a solicitação no provedor e
  devolve as referências que ligam a `SignatureRequest` ao documento/signatário de lá.
- **ENTRADA** (fornecedor → Biahflow): o webhook (`/api/v1/esign/webhook/`) valida o HMAC do
  corpo cru, normaliza o evento (`parse_event`) e aplica o status (`apply_event`) — é a
  transição `pending → signed/declined` de verdade. O `mark-signed` do `DocumentViewSet`
  segue como fallback manual para quando não há provedor configurado.

O provedor homologado é o Clicksign; `ESIGN_PROVIDER` escolhe o adaptador e, sem um
reconhecido, cai no `NullProvider` (só registra a intenção, comportamento antigo). As
chamadas HTTP reais ficam fora da cobertura (`# pragma: no cover`), como em `tasksync.py`.
"""

from __future__ import annotations

import hmac
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from . import flags, notifications
from .portal import sign

if TYPE_CHECKING:
    from .models import Document, SignatureRequest

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    return flags.is_enabled("esign")


@dataclass(frozen=True)
class Event:
    """Evento do fornecedor já normalizado para o vocabulário do Biahflow."""

    status: str  # SignatureRequest.Status
    provider_ref: str = ""
    document_ref: str = ""
    signer_email: str = ""


class Provider(Protocol):
    """Contrato do adaptador de fornecedor (Clicksign hoje, DocuSign depois)."""

    def send(self, document: Document, signer_email: str) -> tuple[str, str]:
        """Cria a solicitação e devolve `(provider_ref, document_ref)`."""

    def verify(self, body: bytes, headers: Mapping[str, str]) -> bool:
        """A entrega veio mesmo do fornecedor?"""

    def parse_event(self, payload: dict) -> Event | None:
        """Normaliza a entrega; `None` quando o evento não interessa ao portal."""


class NullProvider:
    """Sem fornecedor homologado: registra a intenção e não promete nada."""

    def send(self, document: Document, signer_email: str) -> tuple[str, str]:
        logger.info(
            "Solicitação de assinatura sem provedor homologado doc=%s signer=%s",
            document.pk, signer_email,
        )
        return "", ""

    def verify(self, body: bytes, headers: Mapping[str, str]) -> bool:
        return False

    def parse_event(self, payload: dict) -> Event | None:
        return None


# De-para explícito de eventos do Clicksign (o ADR exige não perder informação).
# `deadline` e os eventos de upload/visualização não movem a assinatura: ficam pendentes.
_CLICKSIGN_EVENTS: dict[str, str] = {
    "sign": "signed",
    "auto_close": "signed",
    "document_closed": "signed",
    "refusal": "declined",
    "cancel": "declined",
}


class ClicksignProvider:
    """Adaptador Clicksign: API REST para a saída, webhook `Content-Hmac` para a entrada."""

    def send(self, document: Document, signer_email: str) -> tuple[str, str]:
        if not settings.ESIGN_API_TOKEN:
            logger.info("Clicksign sem ESIGN_API_TOKEN; solicitação só registrada localmente")
            return "", ""
        return self._create_signature_request(document, signer_email)

    def verify(self, body: bytes, headers: Mapping[str, str]) -> bool:
        secret = settings.ESIGN_WEBHOOK_SECRET
        provided = headers.get("Content-Hmac", "")
        if not secret or not provided:
            return False
        return hmac.compare_digest(provided, f"sha256={sign(secret, body)}")

    def parse_event(self, payload: dict) -> Event | None:
        event = payload.get("event") or {}
        status = _CLICKSIGN_EVENTS.get(str(event.get("name", "")).strip().lower())
        if status is None:
            return None
        document = payload.get("document") or {}
        signer = (event.get("data") or {}).get("user") or {}
        # A chave da lista (`request_signature_key`) é o que casa 1:1 com a SignatureRequest;
        # quando ela não vem, o par documento + e-mail do signatário resolve.
        signature_key = ""
        for entry in document.get("signers") or []:
            if str(entry.get("email", "")).lower() == str(signer.get("email", "")).lower():
                signature_key = str(entry.get("request_signature_key", ""))
                break
        return Event(
            status=status,
            provider_ref=signature_key,
            document_ref=str(document.get("key", "")),
            signer_email=str(signer.get("email", "")),
        )

    def _create_signature_request(  # pragma: no cover - I/O com o fornecedor
        self, document: Document, signer_email: str
    ) -> tuple[str, str]:
        base = settings.ESIGN_API_BASE.rstrip("/")
        token = settings.ESIGN_API_TOKEN
        created = _http(
            f"{base}/api/v1/documents?access_token={token}",
            {"document": {"path": f"/{document.original_name}", "content_base64": ""}},
            method="POST",
        )
        document_ref = str(((created or {}).get("document") or {}).get("key", ""))
        if not document_ref:
            return "", ""
        signer = _http(
            f"{base}/api/v1/signers?access_token={token}",
            {"signer": {"email": signer_email, "auths": ["email"]}},
            method="POST",
        )
        signer_key = str(((signer or {}).get("signer") or {}).get("key", ""))
        if not signer_key:
            return "", document_ref
        linked = _http(
            f"{base}/api/v1/lists?access_token={token}",
            {"list": {"document_key": document_ref, "signer_key": signer_key, "sign_as": "sign"}},
            method="POST",
        )
        provider_ref = str(((linked or {}).get("list") or {}).get("request_signature_key", ""))
        return provider_ref, document_ref


_PROVIDERS: dict[str, type] = {"clicksign": ClicksignProvider}


def get_provider() -> Provider:
    """Adaptador escolhido por `ESIGN_PROVIDER`; sem um reconhecido, o `NullProvider`."""
    provider = _PROVIDERS.get(settings.ESIGN_PROVIDER.strip().lower())
    return provider() if provider else NullProvider()


# --- Saída (Biahflow → fornecedor) ------------------------------------------


def send_for_signature(document: Document, signer_email: str) -> tuple[str, str]:
    """Envia o documento para assinatura e devolve `(provider_ref, document_ref)`."""
    return get_provider().send(document, signer_email)


def remind_pending(document: Document) -> int:
    """Envia lembrete a cada signatário ainda pendente do documento e retorna quantos.

    Com provedor homologado o status chega por webhook; o lembrete continua sendo a
    ferramenta de quem acompanha a assinatura (e o único laço quando não há provedor).
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


# --- Entrada (fornecedor → Biahflow) ----------------------------------------


def find_signature(event: Event) -> SignatureRequest | None:
    """Casa o evento com a solicitação: pela referência do fornecedor, ou documento + e-mail."""
    from .models import SignatureRequest

    if event.provider_ref:
        found = SignatureRequest.objects.filter(provider_ref=event.provider_ref).first()
        if found is not None:
            return found
    if event.document_ref and event.signer_email:
        return SignatureRequest.objects.filter(
            document_ref=event.document_ref, signer_email__iexact=event.signer_email
        ).first()
    return None


def apply_event(event: Event) -> SignatureRequest | None:
    """Aplica o status do fornecedor à solicitação. Idempotente: reentrega não muda nada.

    Retorna a `SignatureRequest` afetada (mesmo quando já estava no status alvo) ou `None`
    quando o evento não corresponde a nenhuma solicitação conhecida.
    """
    from .models import SignatureRequest

    signature = find_signature(event)
    if signature is None:
        return None
    if signature.status == event.status:
        return signature
    signature.status = event.status
    if event.status == SignatureRequest.Status.SIGNED:
        signature.signed_at = timezone.now()
    signature.save(update_fields=["status", "signed_at"])
    document = signature.document
    label = "assinou" if event.status == SignatureRequest.Status.SIGNED else "recusou assinar"
    notifications.notify(
        [document.uploaded_by],
        "esign",
        f"{signature.signer_email} {label} o documento {document.original_name}.",
        "/documentos",
    )
    return signature


def _http(  # pragma: no cover - I/O com o fornecedor
    url: str, payload: dict, method: str
) -> dict | None:
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        url, data=body, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            raw = response.read()
        return json.loads(raw) if raw else None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("Falha ao falar com o fornecedor de assinatura (%s): %s", url, exc)
        return None
