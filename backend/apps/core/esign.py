"""Assinatura eletrônica atrás de flag (`esign`), agnóstica de fornecedor (ADR 0007).

Dois lados, no mesmo molde do `tasksync.py`:

- **SAÍDA** (Biahflow → fornecedor): `send_for_signature()` cria a solicitação no provedor e
  devolve as referências que ligam a `SignatureRequest` ao documento/signatário de lá.
- **ENTRADA** (fornecedor → Biahflow): o webhook (`/api/v1/esign/webhook/`) valida o HMAC do
  corpo cru, normaliza o evento (`parse_event`) e aplica o status (`apply_event`) — é a
  transição `pending → signed/declined` de verdade. O `mark-signed` do `DocumentViewSet`
  segue como fallback manual para quando não há provedor configurado.

O fornecedor em uso é o **Autentique**; o Clicksign fica como segundo adaptador.
`ESIGN_PROVIDER` escolhe qual vale e, sem um reconhecido, cai no `NullProvider` (só registra
a intenção). Cada fornecedor traz seu próprio esquema de assinatura do webhook — header e
formato do HMAC diferem —, por isso `verify()` pertence ao adaptador e não à view. As
chamadas HTTP reais ficam fora da cobertura (`# pragma: no cover`), como em `tasksync.py`.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import urllib.error
import urllib.request
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from . import drive, flags, notifications
from .exceptions import DriveUnavailable
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


class EsignProviderError(Exception):
    """O fornecedor de assinatura não devolveu uma solicitação utilizável.

    `_http_raw` engole a falha de rede e devolve `None` de propósito — o portal não pode cair
    porque o fornecedor caiu. O problema era o degrau seguinte: `None` virava um `SignatureRef`
    vazio, **indistinguível de sucesso**, e a solicitação era gravada assim mesmo. Este tipo existe
    para separar as duas coisas.
    """


@dataclass(frozen=True)
class SignatureRef:
    """O que o fornecedor devolve ao criar a solicitação."""

    provider_ref: str = ""  # identifica o signatário; chave de busca do webhook
    document_ref: str = ""  # identifica o documento; fallback junto com o e-mail
    sign_url: str = ""  # link para o signatário assinar (vai no lembrete)


class Provider(Protocol):
    """Contrato do adaptador de fornecedor (Autentique e Clicksign hoje)."""

    def send(self, document: Document, signer_email: str) -> SignatureRef:
        """Cria a solicitação no fornecedor e devolve as referências dela."""

    def verify(self, body: bytes, headers: Mapping[str, str]) -> bool:
        """A entrega veio mesmo do fornecedor?"""

    def parse_event(self, payload: dict) -> Event | None:
        """Normaliza a entrega; `None` quando o evento não interessa ao portal."""


class NullProvider:
    """Sem fornecedor homologado: registra a intenção e não promete nada."""

    def send(self, document: Document, signer_email: str) -> SignatureRef:
        logger.info(
            "Solicitação de assinatura sem provedor homologado doc=%s signer=%s",
            document.pk, signer_email,
        )
        return SignatureRef()

    def verify(self, body: bytes, headers: Mapping[str, str]) -> bool:
        return False

    def parse_event(self, payload: dict) -> Event | None:
        return None


# De-para explícito de eventos do Autentique (o ADR exige não perder informação). Só estes
# dois movem a assinatura; `signature.viewed`, os biométricos e os de documento
# (`document.finished` etc.) não mudam o estado de nenhum signatário.
_AUTENTIQUE_EVENTS: dict[str, str] = {
    "signature.accepted": "signed",
    "signature.rejected": "declined",
}

# `sandbox` é argumento do `createDocument` (não campo do `DocumentInput` — confirmado por
# introspecção do schema; a documentação sugere o contrário).
_AUTENTIQUE_CREATE = """
mutation CreateDocument(
  $document: DocumentInput!, $signers: [SignerInput!]!, $file: Upload!, $sandbox: Boolean!
) {
  createDocument(document: $document, signers: $signers, file: $file, sandbox: $sandbox) {
    id
    signatures { public_id email link { short_link } }
  }
}
"""


def delivers_by_link() -> bool:
    """O portal entrega o link de assinatura (em vez de o fornecedor mandar o convite)?"""
    return settings.ESIGN_DELIVERY == "link"


def _autentique_signer(signer_email: str) -> dict[str, str]:
    """Signatário no formato do Autentique, conforme quem avisa (ver `ESIGN_DELIVERY`).

    Na entrega por link o fornecedor não manda convite — e exige `name`, que derivamos do
    e-mail — mas devolve o `short_link`, que o portal usa no convite e no lembrete.
    """
    if not delivers_by_link():
        return {"email": signer_email, "action": "SIGN"}
    return {
        "email": signer_email,
        "name": signer_email.split("@")[0],
        "action": "SIGN",
        "delivery_method": "DELIVERY_METHOD_LINK",
    }


class AutentiqueProvider:
    """Adaptador Autentique: GraphQL (multipart) na saída, `x-autentique-signature` na entrada."""

    DEFAULT_BASE = "https://api.autentique.com.br/v2/graphql"

    def send(self, document: Document, signer_email: str) -> SignatureRef:
        if not settings.ESIGN_API_TOKEN:
            logger.info("Autentique sem ESIGN_API_TOKEN; solicitação só registrada localmente")
            return SignatureRef()
        content = _document_bytes(document)
        if not content:
            logger.warning("Documento %s sem conteúdo; nada enviado ao Autentique", document.pk)
            return SignatureRef()
        operations = json.dumps(
            {
                "query": _AUTENTIQUE_CREATE,
                "variables": {
                    "document": {"name": document.original_name},
                    "signers": [_autentique_signer(signer_email)],
                    "file": None,
                    "sandbox": bool(settings.ESIGN_SANDBOX),
                },
            }
        )
        body, content_type = _multipart(
            {"operations": operations, "map": '{"file": ["variables.file"]}'},
            document.original_name,
            content,
        )
        data = self._post(body, content_type)
        return self._parse_created(data, signer_email)

    @staticmethod
    def _parse_ping(data: dict | None) -> tuple[bool, str]:
        """Lê a resposta do `me` (separada do I/O para ficar testável, como `_parse_created`)."""
        me = ((data or {}).get("data") or {}).get("me") or {}
        email = str(me.get("email", ""))
        if not email:
            return False, "o Autentique não reconheceu o token"
        return True, f"conta {email} acessível"

    def ping(self) -> tuple[bool, str]:  # pragma: no cover - I/O com o fornecedor
        """Pergunta de quem é o token, sem criar documento nem cobrar nada.

        O gancho existe em `integrations._probe_esign` desde a FDD 024, mas nenhum adaptador o
        implementava — e o e-sign era a única integração configurada que dizia "sem sonda
        disponível". A rodada 4 confirmou que a query `me` serve.
        """
        # `_http_raw` e não `_http`: este último é o helper do **Clicksign**, que leva o token na
        # URL e por isso não manda header de autorização — usá-lo aqui rende um 401 com um token
        # perfeitamente válido. Foi o que aconteceu na primeira versão desta sonda, e só apareceu
        # porque ela foi rodada contra o fornecedor de verdade.
        return self._parse_ping(
            _http_raw(
                settings.ESIGN_API_BASE or self.DEFAULT_BASE,
                json.dumps({"query": "{ me { email } }"}).encode(),
                {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {settings.ESIGN_API_TOKEN}",
                },
            )
        )

    def verify(self, body: bytes, headers: Mapping[str, str]) -> bool:
        secret = settings.ESIGN_WEBHOOK_SECRET
        provided = headers.get("x-autentique-signature", "")
        if not secret or not provided:
            return False
        return hmac.compare_digest(provided, sign(secret, body))  # hex puro, sem prefixo

    def parse_event(self, payload: dict) -> Event | None:
        event = payload.get("event") or {}
        status = _AUTENTIQUE_EVENTS.get(str(event.get("type", "")).strip().lower())
        if status is None:
            return None
        data = event.get("data") or {}
        return Event(
            status=status,
            provider_ref=str(data.get("public_id", "")),
            document_ref=str(data.get("document", "")),
            signer_email=str((data.get("user") or {}).get("email", "")),
        )

    @staticmethod
    def _parse_created(data: dict | None, signer_email: str) -> SignatureRef:
        """Lê a resposta do `createDocument` (separada do I/O para ficar testável)."""
        created = ((data or {}).get("data") or {}).get("createDocument") or {}
        signatures = created.get("signatures") or []
        chosen = next(
            (s for s in signatures if str(s.get("email", "")).lower() == signer_email.lower()),
            signatures[0] if signatures else {},
        )
        return SignatureRef(
            provider_ref=str(chosen.get("public_id", "")),
            document_ref=str(created.get("id", "")),
            sign_url=str((chosen.get("link") or {}).get("short_link", "")),
        )

    def _post(self, body: bytes, content_type: str) -> dict | None:  # pragma: no cover - I/O
        return _http_raw(
            settings.ESIGN_API_BASE or self.DEFAULT_BASE,
            body,
            {
                "Content-Type": content_type,
                "Authorization": f"Bearer {settings.ESIGN_API_TOKEN}",
            },
        )


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

    DEFAULT_BASE = "https://sandbox.clicksign.com"

    def send(self, document: Document, signer_email: str) -> SignatureRef:
        if not settings.ESIGN_API_TOKEN:
            logger.info("Clicksign sem ESIGN_API_TOKEN; solicitação só registrada localmente")
            return SignatureRef()
        content = _document_bytes(document)
        if not content:
            logger.warning("Documento %s sem conteúdo; nada enviado ao Clicksign", document.pk)
            return SignatureRef()
        return self._create_signature_request(document, signer_email, content)

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
        self, document: Document, signer_email: str, content: bytes
    ) -> SignatureRef:
        base = (settings.ESIGN_API_BASE or self.DEFAULT_BASE).rstrip("/")
        token = settings.ESIGN_API_TOKEN
        mime = "application/pdf" if document.original_name.lower().endswith(".pdf") else "text/plain"
        encoded = base64.b64encode(content).decode()
        created = _http(
            f"{base}/api/v1/documents?access_token={token}",
            {
                "document": {
                    "path": f"/{document.original_name}",
                    "content_base64": f"data:{mime};base64,{encoded}",
                }
            },
            method="POST",
        )
        document_ref = str(((created or {}).get("document") or {}).get("key", ""))
        if not document_ref:
            return SignatureRef()
        signer = _http(
            f"{base}/api/v1/signers?access_token={token}",
            {"signer": {"email": signer_email, "auths": ["email"]}},
            method="POST",
        )
        signer_key = str(((signer or {}).get("signer") or {}).get("key", ""))
        if not signer_key:
            return SignatureRef(document_ref=document_ref)
        linked = _http(
            f"{base}/api/v1/lists?access_token={token}",
            {"list": {"document_key": document_ref, "signer_key": signer_key, "sign_as": "sign"}},
            method="POST",
        )
        listed = (linked or {}).get("list") or {}
        return SignatureRef(
            provider_ref=str(listed.get("request_signature_key", "")),
            document_ref=document_ref,
            sign_url=str(listed.get("url", "")),
        )


_PROVIDERS: dict[str, type] = {
    "autentique": AutentiqueProvider,
    "clicksign": ClicksignProvider,
}


def get_provider() -> Provider:
    """Adaptador escolhido por `ESIGN_PROVIDER`; sem um reconhecido, o `NullProvider`."""
    provider = _PROVIDERS.get(settings.ESIGN_PROVIDER.strip().lower())
    return provider() if provider else NullProvider()


# --- Saída (Biahflow → fornecedor) ------------------------------------------


def has_provider() -> bool:
    """Há fornecedor homologado, ou estamos no registro local do `NullProvider`?"""
    return not isinstance(get_provider(), NullProvider)


def send_for_signature(document: Document, signer_email: str) -> SignatureRef:
    """Envia o documento para assinatura e devolve as referências do fornecedor.

    Levanta `EsignProviderError` quando **havia um fornecedor** e ele não devolveu referência: sem
    `provider_ref` a solicitação não existe do lado dele, e gravá-la aqui produziria uma assinatura
    que ninguém assina, que o webhook nunca fecha (não há o que casar) e que o lembrete ainda
    cobraria de uma pessoa de verdade — sem link, porque `sign_url` também vem vazio.

    Sem fornecedor, referência vazia é **correta**: o `NullProvider` registra a intenção e o
    `mark-signed` manual é o caminho previsto. A distinção é toda esta função.
    """
    ref = get_provider().send(document, signer_email)
    if has_provider() and not ref.provider_ref:
        raise EsignProviderError(
            f"{settings.ESIGN_PROVIDER} não devolveu referência para {document.pk}"
        )
    return ref


def _document_bytes(document: Document) -> bytes:
    """Conteúdo do arquivo, venha ele do Drive ou do storage local (mesma regra do download)."""
    if document.drive_file_id:
        # Mesmo download da action de documento, mesmo tratamento: falha do Drive é do fornecedor.
        try:
            return drive.download_document(document).read()
        except drive.DriveProviderError as exc:
            raise DriveUnavailable() from exc
    if not document.file:
        return b""
    with document.file.open("rb") as handle:
        return handle.read()


def _mail_signer(document: Document, signature: SignatureRequest, subject: str, lead: str) -> None:
    """E-mail do portal ao signatário, com o link quando somos nós que entregamos."""
    link = f"\nAssine aqui: {signature.sign_url}" if signature.sign_url else ""
    send_mail(
        f"{subject} — {document.original_name}",
        f"{lead}{link}",
        None,
        [signature.signer_email],
        fail_silently=True,
    )


def invite_signer(document: Document, signature: SignatureRequest) -> bool:
    """Convida o signatário quando a entrega é nossa (`ESIGN_DELIVERY=link`).

    Na entrega por e-mail quem convida é o fornecedor — o portal não duplica o aviso.
    """
    if not delivers_by_link() or not signature.sign_url:
        return False
    _mail_signer(
        document,
        signature,
        "Documento para assinatura",
        f"Você tem um documento para assinar: '{document.original_name}'.",
    )
    return True


def remind_pending(document: Document) -> int:
    """Envia lembrete a cada signatário ainda pendente do documento e retorna quantos.

    Com provedor homologado o status chega por webhook; o lembrete continua sendo a
    ferramenta de quem acompanha a assinatura (e o único laço quando não há provedor).
    """
    from .models import SignatureRequest

    pending = document.signature_requests.filter(status=SignatureRequest.Status.PENDING)
    reminded = 0
    for signature in pending:
        _mail_signer(
            document,
            signature,
            "Lembrete de assinatura",
            f"Consta pendente a sua assinatura do documento '{document.original_name}'.\n"
            f"Por favor, conclua a assinatura eletrônica.",
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


def _close_contract_artifacts(document, signature_status: str) -> None:  # type: ignore[no-untyped-def]
    """Fecha o artefato de contrato ligado ao documento com a decisão do signatário (FDD 016)."""
    from .models import Artifact, SignatureRequest

    if signature_status == SignatureRequest.Status.SIGNED:
        decision = Artifact.Status.ACCEPTED
    elif signature_status == SignatureRequest.Status.DECLINED:
        decision = Artifact.Status.REJECTED
    else:
        return
    contracts = document.artifacts.filter(
        kind=Artifact.Kind.CONTRACT, archived_at__isnull=True
    ).exclude(status=decision)
    for contract in contracts:
        contract.status = decision
        contract.save(update_fields=["status", "decided_at", "updated_at"])


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
    # O contrato do documento acompanha a decisão do signatário (FDD 016). A idempotência vem
    # do retorno antecipado acima: reentrega não chega até aqui.
    _close_contract_artifacts(document, event.status)
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
    return _http_raw(
        url, json.dumps(payload).encode(), {"Content-Type": "application/json"}, method=method
    )


def _multipart(fields: Mapping[str, str], filename: str, content: bytes) -> tuple[bytes, str]:
    """Corpo `multipart/form-data` (upload GraphQL) e o Content-Type com o boundary.

    Formato do graphql-multipart-request-spec: os campos `operations` e `map` descrevem a
    mutation e onde o arquivo entra nas variáveis.
    """
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            + value.encode()
            + b"\r\n"
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n".encode()
    )
    parts.append(content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _http_raw(  # pragma: no cover - I/O com o fornecedor
    url: str, body: bytes, headers: Mapping[str, str], method: str = "POST"
) -> dict | None:
    request = urllib.request.Request(url, data=body, method=method, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            raw = response.read()
        return json.loads(raw) if raw else None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("Falha ao falar com o fornecedor de assinatura (%s): %s", url, exc)
        return None
