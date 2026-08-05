import json

import pytest
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


def _post(payload: dict, secret: str = SECRET) -> tuple[int, dict]:
    body = json.dumps(payload).encode()
    response = APIClient().post(
        reverse("esign-webhook"),
        data=body,
        content_type="application/json",
        HTTP_CONTENT_HMAC=f"sha256={sign(secret, body)}",
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


def test_provider_resolves_clicksign():
    with override_settings(ESIGN_PROVIDER="Clicksign"):
        assert isinstance(esign.get_provider(), esign.ClicksignProvider)


@pytest.mark.django_db
def test_null_provider_registers_intent_without_refs():
    with override_settings(ESIGN_PROVIDER=""):
        assert esign.send_for_signature(_document(), "quem@x.test") == ("", "")


@pytest.mark.django_db
def test_clicksign_send_without_token_keeps_local_only():
    with override_settings(ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN=""):
        assert esign.send_for_signature(_document(), "quem@x.test") == ("", "")


@pytest.mark.django_db
def test_clicksign_send_with_token_calls_the_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        esign.ClicksignProvider, "_create_signature_request", lambda self, d, e: ("req-1", "doc-1")
    )
    with override_settings(ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN="tok"):
        assert esign.send_for_signature(_document(), "quem@x.test") == ("req-1", "doc-1")


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
