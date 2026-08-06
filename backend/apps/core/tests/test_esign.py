import io
import json
from typing import cast

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core import esign
from apps.core.models import Document, Notification, SignatureRequest
from apps.core.portal import sign

from .factories import ClientFactory, UserFactory

SECRET = "webhook-secret"


def _document() -> Document:
    user = UserFactory()
    client = ClientFactory(owner=user)
    return Document.objects.create(client=client, original_name="contrato.pdf", uploaded_by=user)


def _payload(
    event: str = "sign",
    email: str = "pendente@x.test",
    document_key: str = "doc-1",
    signature_key: str = "req-1",
) -> dict:
    """Entrega no formato do Clicksign."""
    return {
        "event": {"name": event, "data": {"user": {"email": email}}},
        "document": {
            "key": document_key,
            "signers": [{"email": email, "request_signature_key": signature_key}],
        },
    }


def _autentique_payload(
    event: str = "signature.accepted",
    email: str = "pendente@x.test",
    document_key: str = "doc-1",
    signature_key: str = "req-1",
) -> dict:
    """Entrega no formato do Autentique (ver docs/api/integration-basics/webhooks)."""
    return {
        "id": "MjV8OTQ4",
        "object": "webhook",
        "event": {
            "id": "9488ce11-70bf-4db7-858b-d76f1dd290dc",
            "object": "event",
            "type": event,
            "data": {
                "public_id": signature_key,
                "object": "signature",
                "user": {"name": "Quem Assina", "email": email},
                "document": document_key,
                "action": "Sign",
            },
        },
    }


def _post(payload: dict, secret: str = SECRET) -> tuple[int, dict]:
    body = json.dumps(payload).encode()
    response = APIClient().post(
        reverse("esign-webhook"),
        data=body,
        content_type="application/json",
        HTTP_CONTENT_HMAC=f"sha256={sign(secret, body)}",
    )
    return response.status_code, response.json()


def _post_autentique(payload: dict, secret: str = SECRET) -> tuple[int, dict]:
    body = json.dumps(payload).encode()
    response = APIClient().post(
        reverse("esign-webhook"),
        data=body,
        content_type="application/json",
        HTTP_X_AUTENTIQUE_SIGNATURE=sign(secret, body),  # hex puro, sem prefixo
    )
    return response.status_code, response.json()


# --- lembrete ----------------------------------------------------------------


@pytest.mark.django_db
def test_remind_pending_emails_only_pending_and_stamps(mailoutbox):
    document = _document()
    SignatureRequest.objects.create(document=document, signer_email="pendente@x.test")
    SignatureRequest.objects.create(
        document=document, signer_email="assinado@x.test", status=SignatureRequest.Status.SIGNED
    )

    reminded = esign.remind_pending(document)

    assert reminded == 1
    assert [mail.to for mail in mailoutbox] == [["pendente@x.test"]]
    pending = document.signature_requests.get(signer_email="pendente@x.test")
    assert pending.reminded_at is not None


@pytest.mark.django_db
def test_remind_pending_includes_the_signing_link_when_there_is_one(mailoutbox):
    document = _document()
    SignatureRequest.objects.create(
        document=document, signer_email="com@x.test", sign_url="https://assina.ae/abc"
    )
    SignatureRequest.objects.create(document=document, signer_email="sem@x.test")

    assert esign.remind_pending(document) == 2

    bodies = {mail.to[0]: mail.body for mail in mailoutbox}
    assert "Assine aqui: https://assina.ae/abc" in bodies["com@x.test"]
    assert "Assine aqui" not in bodies["sem@x.test"]


@pytest.mark.django_db
def test_remind_pending_returns_zero_without_pending(mailoutbox):
    document = _document()
    SignatureRequest.objects.create(
        document=document, signer_email="ok@x.test", status=SignatureRequest.Status.SIGNED
    )

    assert esign.remind_pending(document) == 0
    assert mailoutbox == []


# --- resolução do provedor ---------------------------------------------------


def test_provider_defaults_to_null_without_a_known_one():
    with override_settings(ESIGN_PROVIDER=""):
        assert isinstance(esign.get_provider(), esign.NullProvider)
    with override_settings(ESIGN_PROVIDER="fornecedor-x"):
        assert isinstance(esign.get_provider(), esign.NullProvider)


def test_provider_resolves_each_known_vendor():
    with override_settings(ESIGN_PROVIDER="Clicksign"):
        assert isinstance(esign.get_provider(), esign.ClicksignProvider)
    with override_settings(ESIGN_PROVIDER="Autentique"):
        assert isinstance(esign.get_provider(), esign.AutentiqueProvider)


@pytest.mark.django_db
def test_null_provider_registers_intent_without_refs():
    with override_settings(ESIGN_PROVIDER=""):
        assert esign.send_for_signature(_document(), "quem@x.test") == esign.SignatureRef()


@pytest.mark.django_db
@pytest.mark.parametrize("provider", ["clicksign", "autentique"])
def test_send_without_token_fails_instead_of_pretending(provider: str):
    """Antes isto virava "registrado localmente" — uma solicitação que ninguém assinaria, gravada
    como se estivesse pendente. Com fornecedor configurado, referência vazia é falha (rodada 4).

    Sem fornecedor nenhum o registro local segue valendo; quem faz a distinção é o `NullProvider`.
    """
    with override_settings(ESIGN_PROVIDER=provider, ESIGN_API_TOKEN=""):
        with pytest.raises(esign.EsignProviderError):
            esign.send_for_signature(_document(), "quem@x.test")


@pytest.mark.django_db
@pytest.mark.parametrize("provider", ["clicksign", "autentique"])
def test_send_skips_document_without_content(provider: str):
    """Documento sem arquivo (nem Drive, nem storage local) não vira solicitação no fornecedor.

    A intenção não mudou; o que a pessoa vê, sim: antes sobrava uma linha "pendente" que ninguém
    assinaria, agora o pedido falha alto (rodada 4).
    """
    with override_settings(ESIGN_PROVIDER=provider, ESIGN_API_TOKEN="tok"):
        with pytest.raises(esign.EsignProviderError):
            esign.send_for_signature(_document(), "quem@x.test")


@pytest.mark.django_db
def test_clicksign_send_with_token_calls_the_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(esign, "_document_bytes", lambda document: b"%PDF-1.4")
    monkeypatch.setattr(
        esign.ClicksignProvider,
        "_create_signature_request",
        lambda self, d, e, content: esign.SignatureRef("req-1", "doc-1", "https://x.test/a"),
    )
    with override_settings(ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN="tok"):
        ref = esign.send_for_signature(_document(), "quem@x.test")
    assert ref == esign.SignatureRef("req-1", "doc-1", "https://x.test/a")


@pytest.mark.django_db
def test_document_bytes_reads_local_storage_and_drive(monkeypatch: pytest.MonkeyPatch):
    user = UserFactory()
    document = Document.objects.create(
        client=ClientFactory(owner=user),
        original_name="contrato.pdf",
        uploaded_by=user,
        file=SimpleUploadedFile("contrato.pdf", b"%PDF-local", content_type="application/pdf"),
    )
    assert esign._document_bytes(document) == b"%PDF-local"

    document.drive_file_id = "drive-1"
    monkeypatch.setattr(esign.drive, "download_document", lambda doc: io.BytesIO(b"%PDF-drive"))
    assert esign._document_bytes(document) == b"%PDF-drive"


# --- Autentique: saída --------------------------------------------------------


@pytest.mark.django_db
def test_autentique_send_posts_multipart_and_reads_the_refs(monkeypatch: pytest.MonkeyPatch):
    sent: dict[str, object] = {}

    def fake_post(self, body: bytes, content_type: str):
        sent.update(body=body, content_type=content_type)
        return {
            "data": {
                "createDocument": {
                    "id": "doc-99",
                    "signatures": [
                        {"public_id": "outro", "email": "outro@x.test", "link": {"short_link": "n"}},
                        {
                            "public_id": "sig-1",
                            "email": "quem@x.test",
                            "link": {"short_link": "https://assina.ae/abc"},
                        },
                    ],
                }
            }
        }

    monkeypatch.setattr(esign, "_document_bytes", lambda document: b"%PDF-1.4")
    monkeypatch.setattr(esign.AutentiqueProvider, "_post", fake_post)

    with override_settings(ESIGN_PROVIDER="autentique", ESIGN_API_TOKEN="tok", ESIGN_SANDBOX=True):
        ref = esign.send_for_signature(_document(), "quem@x.test")

    assert ref == esign.SignatureRef("sig-1", "doc-99", "https://assina.ae/abc")
    body = cast(bytes, sent["body"])
    assert cast(str, sent["content_type"]).startswith("multipart/form-data; boundary=")
    assert b'name="operations"' in body and b'name="map"' in body
    assert b'{"file": ["variables.file"]}' in body
    assert b'"sandbox": true' in body
    assert b'"action": "SIGN"' in body
    assert b"%PDF-1.4" in body


@pytest.mark.django_db
def test_autentique_signer_shape_follows_the_delivery_mode(monkeypatch: pytest.MonkeyPatch):
    """Entrega por link exige `name` e não dispara o convite do fornecedor."""
    sent: dict[str, object] = {}
    monkeypatch.setattr(esign, "_document_bytes", lambda document: b"%PDF-1.4")
    monkeypatch.setattr(
        esign.AutentiqueProvider,
        "_post",
        lambda self, body, content_type: sent.update(body=body) or {},
    )
    # Direto no provider: o formato do payload é assunto dele, não do orquestrador (que desde a
    # rodada 4 recusa referência vazia e mascararia o que este teste quer inspecionar).
    with override_settings(ESIGN_PROVIDER="autentique", ESIGN_API_TOKEN="tok", ESIGN_DELIVERY="email"):
        esign.AutentiqueProvider().send(_document(), "quem@x.test")
    by_email = cast(bytes, sent["body"])
    assert b"DELIVERY_METHOD_LINK" not in by_email
    assert b'"name"' not in by_email.split(b'"signers"')[1].split(b'"file"')[0]

    with override_settings(ESIGN_PROVIDER="autentique", ESIGN_API_TOKEN="tok", ESIGN_DELIVERY="link"):
        esign.AutentiqueProvider().send(_document(), "quem@x.test")
    by_link = cast(bytes, sent["body"])
    assert b'"delivery_method": "DELIVERY_METHOD_LINK"' in by_link
    assert b'"name": "quem"' in by_link


@pytest.mark.django_db
def test_invite_signer_only_when_the_portal_delivers(mailoutbox):
    document = _document()
    signature = SignatureRequest.objects.create(
        document=document, signer_email="quem@x.test", sign_url="https://assina.ae/abc"
    )
    without_link = SignatureRequest.objects.create(document=document, signer_email="sem@x.test")

    with override_settings(ESIGN_DELIVERY="email"):
        assert esign.invite_signer(document, signature) is False
    with override_settings(ESIGN_DELIVERY="link"):
        assert esign.invite_signer(document, without_link) is False
        assert esign.invite_signer(document, signature) is True

    assert [mail.to for mail in mailoutbox] == [["quem@x.test"]]
    assert "https://assina.ae/abc" in mailoutbox[0].body


def test_autentique_parse_created_tolerates_missing_pieces():
    assert esign.AutentiqueProvider._parse_created(None, "x@x.test") == esign.SignatureRef()
    assert esign.AutentiqueProvider._parse_created({"data": {}}, "x@x.test") == esign.SignatureRef()


@pytest.mark.django_db
def test_autentique_send_respects_sandbox_off(monkeypatch: pytest.MonkeyPatch):
    sent: dict[str, object] = {}
    monkeypatch.setattr(esign, "_document_bytes", lambda document: b"%PDF-1.4")
    monkeypatch.setattr(
        esign.AutentiqueProvider,
        "_post",
        lambda self, body, content_type: sent.update(body=body) or {},
    )
    with override_settings(ESIGN_PROVIDER="autentique", ESIGN_API_TOKEN="tok", ESIGN_SANDBOX=False):
        esign.AutentiqueProvider().send(_document(), "quem@x.test")
    assert b'"sandbox": false' in cast(bytes, sent["body"])


# --- Autentique: entrada ------------------------------------------------------


def test_autentique_parse_event_maps_only_the_two_that_move():
    provider = esign.AutentiqueProvider()
    moves = {
        "signature.accepted": SignatureRequest.Status.SIGNED,
        "signature.rejected": SignatureRequest.Status.DECLINED,
    }
    for name, expected in moves.items():
        assert provider.parse_event(_autentique_payload(name)).status == expected
    for name in (
        "signature.created", "signature.updated", "signature.deleted", "signature.viewed",
        "signature.biometric_approved", "signature.biometric_unapproved",
        "signature.biometric_reset", "signature.biometric_rejected", "signature.delivery_failed",
        "document.created", "document.updated", "document.deleted", "document.finished",
        "member.created", "member.deleted",
    ):
        assert provider.parse_event(_autentique_payload(name)) is None
    assert provider.parse_event({}) is None


def test_autentique_parse_event_extracts_the_three_identifiers():
    event = esign.AutentiqueProvider().parse_event(
        _autentique_payload(document_key="doc-9", signature_key="sig-9")
    )
    assert (event.provider_ref, event.document_ref) == ("sig-9", "doc-9")
    assert event.signer_email == "pendente@x.test"


def test_autentique_verify_uses_plain_hex_header():
    provider = esign.AutentiqueProvider()
    body = b'{"event": "x"}'
    with override_settings(ESIGN_WEBHOOK_SECRET=SECRET):
        assert provider.verify(body, {"x-autentique-signature": sign(SECRET, body)}) is True
        assert provider.verify(body, {"x-autentique-signature": "errado"}) is False
        assert provider.verify(b'{"event":"y"}', {"x-autentique-signature": sign(SECRET, body)}) is False
        assert provider.verify(body, {}) is False
    with override_settings(ESIGN_WEBHOOK_SECRET=""):
        assert provider.verify(body, {"x-autentique-signature": sign(SECRET, body)}) is False


def test_each_provider_rejects_the_others_header():
    """Convivência: o esquema de assinatura do webhook é de cada fornecedor, não da view."""
    body = b'{"event": "x"}'
    with override_settings(ESIGN_WEBHOOK_SECRET=SECRET):
        autentique_header = {"x-autentique-signature": sign(SECRET, body)}
        clicksign_header = {"Content-Hmac": f"sha256={sign(SECRET, body)}"}
        assert esign.AutentiqueProvider().verify(body, clicksign_header) is False
        assert esign.ClicksignProvider().verify(body, autentique_header) is False


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="autentique", ESIGN_WEBHOOK_SECRET=SECRET)
def test_autentique_webhook_signs_and_is_idempotent():
    document = _document()
    signature = SignatureRequest.objects.create(
        document=document, signer_email="pendente@x.test", provider_ref="req-1"
    )

    code, data = _post_autentique(_autentique_payload())
    signature.refresh_from_db()
    first_signed_at = signature.signed_at

    again_code, _ = _post_autentique(_autentique_payload())
    signature.refresh_from_db()

    assert (code, again_code) == (200, 200)
    assert data["status"] == SignatureRequest.Status.SIGNED
    assert signature.signed_at == first_signed_at
    assert Notification.objects.filter(kind="esign").count() == 1


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="autentique", ESIGN_WEBHOOK_SECRET=SECRET)
def test_autentique_webhook_401_on_bad_signature():
    code, _ = _post_autentique(_autentique_payload(), secret="outro")
    assert code == 401


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="autentique", ESIGN_WEBHOOK_SECRET=SECRET)
def test_autentique_webhook_rejects_a_clicksign_delivery():
    """Trocar de fornecedor é trocar o ESIGN_PROVIDER: a entrega do outro não passa."""
    code, _ = _post(_payload())
    assert code == 401


# --- de-para e verificação ---------------------------------------------------


def test_parse_event_maps_known_events():
    provider = esign.ClicksignProvider()
    assert provider.parse_event(_payload("sign")).status == SignatureRequest.Status.SIGNED
    assert provider.parse_event(_payload("auto_close")).status == SignatureRequest.Status.SIGNED
    assert provider.parse_event(_payload("refusal")).status == SignatureRequest.Status.DECLINED
    assert provider.parse_event(_payload("cancel")).status == SignatureRequest.Status.DECLINED
    assert provider.parse_event(_payload("deadline")) is None
    assert provider.parse_event({}) is None


def test_parse_event_extracts_refs():
    event = esign.ClicksignProvider().parse_event(_payload(signature_key="req-9"))
    assert event.provider_ref == "req-9"
    assert event.document_ref == "doc-1"
    assert event.signer_email == "pendente@x.test"


def test_parse_event_without_matching_signer_leaves_ref_empty():
    """Sem a chave da lista, o casamento fica por documento + e-mail."""
    payload = _payload()
    payload["document"]["signers"] = [{"email": "outro@x.test", "request_signature_key": "req-9"}]
    event = esign.ClicksignProvider().parse_event(payload)
    assert event.provider_ref == ""
    assert (event.document_ref, event.signer_email) == ("doc-1", "pendente@x.test")


def test_verify_accepts_only_the_right_hmac():
    provider = esign.ClicksignProvider()
    body = b'{"event": "x"}'
    with override_settings(ESIGN_WEBHOOK_SECRET=SECRET):
        assert provider.verify(body, {"Content-Hmac": f"sha256={sign(SECRET, body)}"}) is True
        assert provider.verify(body, {"Content-Hmac": "sha256=errado"}) is False
        assert provider.verify(b'{"event": "y"}', {"Content-Hmac": f"sha256={sign(SECRET, body)}"}) is False
        assert provider.verify(body, {}) is False
    with override_settings(ESIGN_WEBHOOK_SECRET=""):
        assert provider.verify(body, {"Content-Hmac": f"sha256={sign(SECRET, body)}"}) is False


def test_null_provider_never_verifies():
    assert esign.NullProvider().verify(b"{}", {"Content-Hmac": "x"}) is False
    assert esign.NullProvider().parse_event(_payload()) is None


# --- aplicação do evento -----------------------------------------------------


@pytest.mark.django_db
def test_apply_event_signs_by_provider_ref_and_notifies():
    document = _document()
    signature = SignatureRequest.objects.create(
        document=document, signer_email="pendente@x.test", provider_ref="req-1"
    )

    applied = esign.apply_event(
        esign.Event(status=SignatureRequest.Status.SIGNED, provider_ref="req-1")
    )

    signature.refresh_from_db()
    assert applied == signature
    assert signature.status == SignatureRequest.Status.SIGNED
    assert signature.signed_at is not None
    assert Notification.objects.filter(user=document.uploaded_by, kind="esign").count() == 1


@pytest.mark.django_db
def test_apply_event_falls_back_to_document_and_email():
    document = _document()
    SignatureRequest.objects.create(
        document=document, signer_email="Pendente@x.test", document_ref="doc-1"
    )

    applied = esign.apply_event(
        esign.Event(
            status=SignatureRequest.Status.DECLINED,
            document_ref="doc-1",
            signer_email="pendente@x.test",
        )
    )

    assert applied is not None
    assert applied.status == SignatureRequest.Status.DECLINED
    assert applied.signed_at is None


@pytest.mark.django_db
def test_apply_event_is_idempotent():
    document = _document()
    signature = SignatureRequest.objects.create(
        document=document, signer_email="pendente@x.test", provider_ref="req-1"
    )
    event = esign.Event(status=SignatureRequest.Status.SIGNED, provider_ref="req-1")

    esign.apply_event(event)
    signature.refresh_from_db()
    first_signed_at = signature.signed_at

    esign.apply_event(event)
    signature.refresh_from_db()
    assert signature.signed_at == first_signed_at
    assert Notification.objects.filter(kind="esign").count() == 1


@pytest.mark.django_db
def test_apply_event_returns_none_without_match():
    assert esign.apply_event(esign.Event(status="signed", provider_ref="nada")) is None
    assert esign.apply_event(esign.Event(status="signed")) is None


# --- endpoint do webhook -----------------------------------------------------


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=False)
def test_webhook_503_when_disabled():
    code, _ = _post(_payload())
    assert code == 503


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="clicksign", ESIGN_WEBHOOK_SECRET=SECRET)
def test_webhook_401_on_bad_signature():
    code, _ = _post(_payload(), secret="outro-segredo")
    assert code == 401


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="clicksign", ESIGN_WEBHOOK_SECRET="")
def test_webhook_401_without_configured_secret():
    code, _ = _post(_payload(), secret="qualquer")
    assert code == 401


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="clicksign", ESIGN_WEBHOOK_SECRET=SECRET)
def test_webhook_marks_signature_as_signed():
    document = _document()
    signature = SignatureRequest.objects.create(
        document=document, signer_email="pendente@x.test", provider_ref="req-1"
    )

    code, data = _post(_payload())

    signature.refresh_from_db()
    assert code == 200
    assert data["status"] == SignatureRequest.Status.SIGNED
    assert signature.status == SignatureRequest.Status.SIGNED


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="clicksign", ESIGN_WEBHOOK_SECRET=SECRET)
def test_webhook_ignores_unknown_event_and_unlinked_signature():
    document = _document()
    SignatureRequest.objects.create(
        document=document, signer_email="pendente@x.test", provider_ref="req-1"
    )

    unknown_code, unknown = _post(_payload(event="deadline"))
    orphan_code, orphan = _post(_payload(signature_key="outra", document_key="outro"))

    assert (unknown_code, orphan_code) == (200, 200)
    assert unknown["detail"] == orphan["detail"] == "Evento ignorado."
    assert SignatureRequest.objects.get(provider_ref="req-1").status == "pending"


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="clicksign", ESIGN_WEBHOOK_SECRET=SECRET)
def test_webhook_400_on_invalid_body():
    body = b"nao-e-json"
    response = APIClient().post(
        reverse("esign-webhook"),
        data=body,
        content_type="application/json",
        HTTP_CONTENT_HMAC=f"sha256={sign(SECRET, body)}",
    )
    assert response.status_code == 400


# --- sonda do Autentique (rodada 4) ------------------------------------------


def test_ping_le_a_conta_do_token():
    """A sonda pergunta ao Autentique de quem é o token, sem criar documento.

    O gancho existia em `integrations._probe_esign` desde a FDD 024 (`getattr(provider, "ping")`),
    mas nenhum adaptador o implementava — e o e-sign era a única integração configurada que
    respondia "sem sonda disponível". A rodada 4 mostrou que a query `me` do Autentique serve:
    valida o token, é só leitura e não cobra nada.
    """
    dados = {"data": {"me": {"id": "abc", "name": "Fulano", "email": "conta@x.test"}}}

    ok, detalhe = esign.AutentiqueProvider._parse_ping(dados)

    assert ok is True
    assert "conta@x.test" in detalhe


def test_ping_reprova_quando_o_token_nao_e_reconhecido():
    """`_http_raw` devolve `None` em falha de rede/401 — e `data.me` vem nulo quando o token não
    vale. Os dois têm de reprovar, senão a sonda mentiria justamente sobre o que existe para dizer.
    """
    for resposta in (None, {}, {"data": {"me": None}}, {"data": {}}):
        ok, detalhe = esign.AutentiqueProvider._parse_ping(resposta)
        assert ok is False, resposta
        assert detalhe
