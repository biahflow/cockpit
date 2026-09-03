import io
import json
import logging
from typing import cast

import pypdf
import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import discovery_booking, esign
from apps.core.models import (
    Artifact,
    Document,
    Engagement,
    Notification,
    SignatureRequest,
    User,
)
from apps.core.portal import sign

from .factories import AccountFactory, ArtifactFactory, CommercialOpportunityFactory, UserFactory

SECRET = "webhook-secret"


def _document() -> Document:
    user = UserFactory()
    account = AccountFactory(owner=user)
    return Document.objects.create(account=account, original_name="contrato.pdf", uploaded_by=user)


def _um(email: str) -> list[esign.Signer]:
    """A rodada de um signatário só — o caso que existia antes da issue #115."""
    return [esign.Signer(email=email, role=SignatureRequest.SignerRole.COUNTERPARTY)]


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


# --- aviso de entrega (issue #112) --------------------------------------------------------------


def test_aviso_de_entrega_vazio_com_entrega_por_link():
    with override_settings(ESIGN_SANDBOX=True, ESIGN_DELIVERY="link"):
        assert esign.aviso_de_entrega() == ""


def test_aviso_de_entrega_vazio_com_sandbox_desligado():
    with override_settings(ESIGN_SANDBOX=False, ESIGN_DELIVERY="email"):
        assert esign.aviso_de_entrega() == ""


def test_aviso_de_entrega_avisa_so_na_combinacao_sandbox_com_email():
    """A combinação não observada entregando o convite (issue #112): sandbox ligado **e** entrega
    por e-mail — os dois defaults de fábrica. A frase nomeia o que foi observado, não a causa."""
    with override_settings(ESIGN_SANDBOX=True, ESIGN_DELIVERY="email"):
        aviso = esign.aviso_de_entrega()

    assert aviso != ""
    assert "issue #112" in aviso


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
    """Sem fornecedor não há `provider_ref` nem `sign_url` — mas **há rodada**.

    A referência `local:` é cunhada por `send_for_signature` (ADR 0065): sem ela, todas as
    solicitações do documento cairiam na mesma rodada e uma recusa antiga travaria o documento
    para sempre. Ver `tests/regression/test_a_rodada_existe_mesmo_sem_fornecedor.py`.
    """
    with override_settings(ESIGN_PROVIDER=""):
        (ref,) = esign.send_for_signature(_document(), _um("quem@x.test"))

    assert (ref.provider_ref, ref.sign_url) == ("", "")
    assert ref.document_ref.startswith("local:")


@pytest.mark.django_db
@pytest.mark.parametrize("provider", ["clicksign", "autentique"])
def test_send_without_token_fails_instead_of_pretending(provider: str):
    """Antes isto virava "registrado localmente" — uma solicitação que ninguém assinaria, gravada
    como se estivesse pendente. Com fornecedor configurado, referência vazia é falha (rodada 4).

    Sem fornecedor nenhum o registro local segue valendo; quem faz a distinção é o `NullProvider`.
    """
    with override_settings(ESIGN_PROVIDER=provider, ESIGN_API_TOKEN=""):
        with pytest.raises(esign.EsignProviderError):
            esign.send_for_signature(_document(), _um("quem@x.test"))


@pytest.mark.django_db
@pytest.mark.parametrize("provider", ["clicksign", "autentique"])
def test_send_skips_document_without_content(provider: str):
    """Documento sem arquivo (nem Drive, nem storage local) não vira solicitação no fornecedor.

    A intenção não mudou; o que a pessoa vê, sim: antes sobrava uma linha "pendente" que ninguém
    assinaria, agora o pedido falha alto (rodada 4).
    """
    with override_settings(ESIGN_PROVIDER=provider, ESIGN_API_TOKEN="tok"):
        with pytest.raises(esign.EsignProviderError):
            esign.send_for_signature(_document(), _um("quem@x.test"))


@pytest.mark.django_db
def test_clicksign_send_with_token_calls_the_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(esign, "_document_bytes", lambda document: b"%PDF-1.4")
    monkeypatch.setattr(
        esign.ClicksignProvider,
        "_create_signature_request",
        lambda self, d, e, content: esign.SignatureRef("req-1", "doc-1", "https://x.test/a"),
    )
    with override_settings(ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN="tok"):
        refs = esign.send_for_signature(_document(), _um("quem@x.test"))
    assert refs == [esign.SignatureRef("req-1", "doc-1", "https://x.test/a")]


@pytest.mark.django_db
def test_document_bytes_reads_local_storage_and_drive(monkeypatch: pytest.MonkeyPatch):
    user = UserFactory()
    document = Document.objects.create(
        account=AccountFactory(owner=user),
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
        refs = esign.send_for_signature(_document(), _um("quem@x.test"))

    assert refs == [esign.SignatureRef("sig-1", "doc-99", "https://assina.ae/abc")]
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
        esign.AutentiqueProvider().send(_document(), _um("quem@x.test"))
    by_email = cast(bytes, sent["body"])
    assert b"DELIVERY_METHOD_LINK" not in by_email
    assert b'"name"' not in by_email.split(b'"signers"')[1].split(b'"file"')[0]

    with override_settings(ESIGN_PROVIDER="autentique", ESIGN_API_TOKEN="tok", ESIGN_DELIVERY="link"):
        esign.AutentiqueProvider().send(_document(), _um("quem@x.test"))
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
    pedidos = _um("x@x.test")
    assert esign.AutentiqueProvider._parse_created(None, pedidos) == [esign.SignatureRef()]
    assert esign.AutentiqueProvider._parse_created({"data": {}}, pedidos) == [esign.SignatureRef()]


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
        esign.AutentiqueProvider().send(_document(), _um("quem@x.test"))
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
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="autentique", ESIGN_API_TOKEN="tok",
                   ESIGN_WEBHOOK_SECRET=SECRET)
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
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="autentique", ESIGN_API_TOKEN="tok",
                   ESIGN_WEBHOOK_SECRET=SECRET)
def test_autentique_webhook_401_on_bad_signature():
    code, _ = _post_autentique(_autentique_payload(), secret="outro")
    assert code == 401


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="autentique", ESIGN_API_TOKEN="tok",
                   ESIGN_WEBHOOK_SECRET=SECRET)
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


# --- mark-signed (fallback manual, sem provedor) -----------------------------
#
# `mark-signed` era o único caminho que concluía uma assinatura sem passar por
# `esign.apply_event`: gravava `status`/`signed_at` à mão e parava aí — não fechava o artefato de
# contrato, não notificava e não tinha guarda de idempotência. Os três testes abaixo afirmam que
# ele passou a produzir exatamente os mesmos efeitos que o webhook já produzia.


def _contract_artifact(document: Document, user: User) -> Artifact:
    """Artefato de contrato "Enviado" ligado ao documento, pronto para `_close_contract_artifacts`."""
    return ArtifactFactory(
        kind=Artifact.Kind.CONTRACT,
        commercial_opportunity=CommercialOpportunityFactory(account=document.account),
        document=document,
        status=Artifact.Status.SENT,
        created_by=user,
    )


def _mark_signed(document: Document, signature: SignatureRequest, user: User) -> tuple[int, dict]:
    client = APIClient()
    client.force_authenticate(user)
    response = client.post(
        reverse("document-mark-signed", args=[document.pk]),
        {"signature": signature.pk},
        format="json",
    )
    return response.status_code, response.data


@pytest.mark.django_db
def test_mark_signed_closes_the_contract_artifact():
    user = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=user), original_name="contrato.pdf", uploaded_by=user
    )
    artifact = _contract_artifact(document, user)
    signature = SignatureRequest.objects.create(document=document, signer_email="quem@x.test")

    code, _ = _mark_signed(document, signature, user)

    assert code == 200
    artifact.refresh_from_db()
    assert artifact.status == Artifact.Status.ACCEPTED
    assert artifact.decided_at is not None


@pytest.mark.django_db
def test_mark_signed_notifies_the_uploader():
    user = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=user), original_name="contrato.pdf", uploaded_by=user
    )
    signature = SignatureRequest.objects.create(document=document, signer_email="quem@x.test")

    code, _ = _mark_signed(document, signature, user)

    assert code == 200
    notification = Notification.objects.get(kind="esign")
    assert notification.user_id == user.pk
    assert "quem@x.test" in notification.message
    assert notification.url == "/documentos"


@pytest.mark.django_db
def test_mark_signed_twice_does_not_duplicate_effects():
    user = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=user), original_name="contrato.pdf", uploaded_by=user
    )
    signature = SignatureRequest.objects.create(document=document, signer_email="quem@x.test")

    first_code, _ = _mark_signed(document, signature, user)
    signature.refresh_from_db()
    first_signed_at = signature.signed_at

    second_code, _ = _mark_signed(document, signature, user)
    signature.refresh_from_db()

    assert (first_code, second_code) == (200, 200)
    assert signature.signed_at == first_signed_at
    assert Notification.objects.filter(kind="esign").count() == 1


# --- endpoint do webhook -----------------------------------------------------


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=False)
def test_webhook_503_when_disabled():
    code, _ = _post(_payload())
    assert code == 503


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN="tok",
                   ESIGN_WEBHOOK_SECRET=SECRET)
def test_webhook_401_on_bad_signature():
    code, _ = _post(_payload(), secret="outro-segredo")
    assert code == 401


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN="tok",
                   ESIGN_WEBHOOK_SECRET="")
def test_webhook_recusa_sem_segredo_configurado():
    """Sem `ESIGN_WEBHOOK_SECRET` a entrega não fecha assinatura nenhuma.

    O código mudou de 401 para 503 com a ADR 0018: o segredo do webhook está no `requires` da flag,
    então faltando ele a integração inteira resolve para desligada e o guard de disponibilidade
    responde antes da verificação de HMAC. A garantia que importa é a mesma — entrega não
    autenticada não marca documento como assinado.
    """
    code, _ = _post(_payload(), secret="qualquer")
    assert code == 503


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN="tok",
                   ESIGN_WEBHOOK_SECRET=SECRET)
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
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN="tok",
                   ESIGN_WEBHOOK_SECRET=SECRET)
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
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN="tok",
                   ESIGN_WEBHOOK_SECRET=SECRET)
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


# =================================================================================================
# Assinatura posicionada e rodada de vários signatários (issue #115, ADR 0065)
# =================================================================================================
#
# A primeira assinatura real (03/09/2026) fechou inteira — assinada, auditada, webhook de volta — e
# a assinatura **não apareceu no campo de assinatura**: foi para uma página anexa. A Autentique não
# lê âncora de texto; onde a assinatura aparece é propriedade da solicitação (`positions`), e nós
# nunca mandávamos esse campo. Os testes abaixo afirmam o que passou a ir no payload, e os da última
# seção afirmam os quatro defeitos que só existem com mais de um signatário.


def _pdf(paginas: int = 1) -> bytes:
    """Um PDF de verdade com N páginas em branco — a geometria não importa aqui, a contagem sim."""
    escritor = pypdf.PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=595, height=842)  # A4 em pontos
    buffer = io.BytesIO()
    escritor.write(buffer)
    return buffer.getvalue()


def _instrumento(kind: str = "", *, user: User | None = None) -> Document:
    uploader = user or UserFactory(role=User.Role.ADMIN)
    return Document.objects.create(
        account=AccountFactory(owner=uploader),
        original_name="instrumento.pdf",
        uploaded_by=uploader,
        kind=kind,
    )


def _signers_enviados(body: bytes) -> list[dict]:
    """Os signatários como foram no `operations` do multipart — o payload de verdade."""
    bruto = body.split(b'name="operations"\r\n\r\n')[1].split(b"\r\n--")[0]
    return json.loads(bruto)["variables"]["signers"]


def _enviar(
    monkeypatch: pytest.MonkeyPatch,
    *,
    kind: str,
    conteudo: bytes,
    signers: list[esign.Signer],
) -> list[dict]:
    """Manda a rodada pelo `AutentiqueProvider` e devolve os signatários do payload."""
    capturado: dict[str, bytes] = {}
    monkeypatch.setattr(esign, "_document_bytes", lambda document: conteudo)
    monkeypatch.setattr(
        esign.AutentiqueProvider,
        "_post",
        lambda self, body, content_type: capturado.update(body=body) or {},
    )
    with override_settings(
        ESIGN_PROVIDER="autentique", ESIGN_API_TOKEN="tok", ESIGN_DELIVERY="email"
    ):
        esign.AutentiqueProvider().send(_instrumento(kind), signers)
    return _signers_enviados(capturado["body"])


def _papeis(*papeis: str) -> list[esign.Signer]:
    return [esign.Signer(email=f"{papel}{i}@x.test", role=papel) for i, papel in enumerate(papeis)]


# --- contar as páginas -------------------------------------------------------


def test_paginas_do_pdf_conta_o_pdf_e_nunca_levanta():
    """Ela é auxílio de posicionamento, não a operação: PDF ilegível vira assinatura sem posição,
    e **nunca** uma solicitação que falha — o fluxo real de hoje manda `.docx`."""
    assert esign.paginas_do_pdf(_pdf(4)) == 4
    assert esign.paginas_do_pdf(_pdf(1)) == 1
    # Reconhecimento pelo conteúdo, não pela extensão: o `.docx` do fluxo real cai aqui.
    assert esign.paginas_do_pdf(b"PK\x03\x04isto-e-um-docx") is None
    assert esign.paginas_do_pdf(b"") is None
    # PDF truncado: o `pypdf` levanta, e quem chama não pode ver a exceção.
    assert esign.paginas_do_pdf(b"%PDF-1.4 truncado no meio") is None
    assert esign.paginas_do_pdf(_pdf(2)[:120]) is None


# --- os papéis e as posições -------------------------------------------------


def test_o_mapa_de_posicoes_cobre_exatamente_os_papeis_declarados():
    """A geometria mora em `esign.py` e o vocabulário em `models.py`; este teste é a ponte.

    Sem ele, um papel novo em `SignerRole` nasceria sem posição e a assinatura dele voltaria calada
    para a página anexa — que é o defeito que esta issue existe para consertar.
    """
    com_posicao = set(esign._POSICAO_POR_PAPEL) | {SignatureRequest.SignerRole.WITNESS.value}
    assert com_posicao == set(SignatureRequest.SignerRole.values)
    assert len(esign._POSICOES_DA_TESTEMUNHA) == 2


def test_os_kinds_com_bloco_de_assinatura_existem_no_document_kind():
    assert esign.DOCUMENT_KINDS_COM_BLOCO_DE_ASSINATURA <= set(Document.Kind.values)
    assert Document.Kind.PROPOSAL not in esign.DOCUMENT_KINDS_COM_BLOCO_DE_ASSINATURA


@pytest.mark.django_db
def test_o_contrato_em_pdf_posiciona_na_ultima_pagina(monkeypatch: pytest.MonkeyPatch):
    enviados = _enviar(
        monkeypatch,
        kind=Document.Kind.COMMERCIAL_CONTRACT,
        conteudo=_pdf(4),
        signers=_papeis("house", "counterparty", "witness"),
    )

    posicoes = [signer["positions"] for signer in enviados]
    assert [len(p) for p in posicoes] == [1, 1, 1]
    assert {p[0]["z"] for p in posicoes} == {"4"}  # a última página, contada do PDF
    assert {p[0]["element"] for p in posicoes} == {"SIGNATURE"}
    # Cada papel assina no **seu** lugar: três assinaturas no mesmo ponto seriam ilegíveis.
    assert len({(p[0]["x"], p[0]["y"]) for p in posicoes}) == 3


@pytest.mark.django_db
def test_documento_que_nao_e_pdf_vai_sem_posicao_e_diz_por_que(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """O fluxo real de hoje manda `.docx`. Recusar quebraria o que funciona; o que não pode é o
    silêncio — sem posição, alguém precisa poder descobrir por quê."""
    with caplog.at_level(logging.INFO, logger="apps.core.esign"):
        enviados = _enviar(
            monkeypatch,
            kind=Document.Kind.COMMERCIAL_CONTRACT,
            conteudo=b"PK\x03\x04isto-e-um-docx",
            signers=_papeis("counterparty"),
        )

    assert "positions" not in enviados[0]
    assert "não é um PDF legível" in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["", Document.Kind.PROPOSAL])
def test_proposta_e_documento_sem_kind_vao_sem_posicao(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, kind: str
):
    """A Proposta não tem bloco de assinatura desenhado, e o `kind` vazio não diz nada. Carimbar
    uma assinatura no meio de um texto corrido é pior que mandá-la para a página anexa."""
    with caplog.at_level(logging.INFO, logger="apps.core.esign"):
        enviados = _enviar(
            monkeypatch, kind=kind, conteudo=_pdf(3), signers=_papeis("counterparty")
        )

    assert "positions" not in enviados[0]
    assert "não tem bloco de assinatura" in caplog.text


@pytest.mark.django_db
def test_as_duas_testemunhas_ocupam_as_duas_linhas_e_a_terceira_fica_sem(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """As linhas de testemunha são de quem for, na ordem em que chegam. A terceira não tem linha:
    empilhar duas assinaturas no mesmo ponto produz um documento ilegível."""
    with caplog.at_level(logging.INFO, logger="apps.core.esign"):
        enviados = _enviar(
            monkeypatch,
            kind=Document.Kind.NDA,
            conteudo=_pdf(2),
            signers=_papeis("witness", "witness", "witness"),
        )

    primeira, segunda = esign._POSICOES_DA_TESTEMUNHA
    assert (enviados[0]["positions"][0]["x"], enviados[0]["positions"][0]["y"]) == primeira
    assert (enviados[1]["positions"][0]["x"], enviados[1]["positions"][0]["y"]) == segunda
    assert "positions" not in enviados[2]
    assert "linhas de testemunha" in caplog.text


@pytest.mark.django_db
def test_a_testemunha_assina_como_testemunha(monkeypatch: pytest.MonkeyPatch):
    enviados = _enviar(
        monkeypatch,
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
        conteudo=_pdf(1),
        signers=_papeis("house", "counterparty", "witness"),
    )

    assert [signer["action"] for signer in enviados] == ["SIGN", "SIGN", "SIGN_AS_A_WITNESS"]


@pytest.mark.django_db
def test_sem_posicao_o_formato_do_signatario_e_o_de_antes(monkeypatch: pytest.MonkeyPatch):
    """A `/api/v1/` e o modo `link` não podem ter mudado para o documento que não é PDF."""
    enviados = _enviar(
        monkeypatch, kind="", conteudo=b"nao-e-pdf", signers=_papeis("counterparty")
    )
    assert enviados[0] == {"email": "counterparty0@x.test", "action": "SIGN"}


# --- a rodada: um documento, N signatários -----------------------------------


LIGADA = override_settings(
    ESIGN_ENABLED=True, ESIGN_PROVIDER="autentique", ESIGN_API_TOKEN="tok",
    ESIGN_WEBHOOK_SECRET=SECRET, ESIGN_HOUSE_SIGNER_EMAIL="",
)
SEM_PROVEDOR = override_settings(
    ESIGN_ENABLED=True, ESIGN_PROVIDER="", ESIGN_HOUSE_SIGNER_EMAIL="",
)


def _pedir(document: Document, corpo: dict) -> tuple[int, dict]:
    client = APIClient()
    client.force_authenticate(document.uploaded_by)
    response = client.post(
        reverse("document-request-signature", args=[document.pk]), corpo, format="json"
    )
    return response.status_code, response.data


def _resposta_do_autentique(emails: list[str], document_id: str = "doc-77") -> dict:
    return {
        "data": {
            "createDocument": {
                "id": document_id,
                "signatures": [
                    {"public_id": f"sig-{i}", "email": email, "link": {"short_link": ""}}
                    for i, email in enumerate(emails)
                ],
            }
        }
    }


@pytest.mark.django_db
@LIGADA
def test_tres_signatarios_sao_um_documento_e_uma_rodada(monkeypatch: pytest.MonkeyPatch):
    """N chamadas produziriam N documentos separados na Autentique, cada um com uma assinatura —
    e nenhum deles seria o contrato que as três pessoas pensam ter assinado."""
    emails = ["casa@biahflow.test", "cliente@x.test", "testemunha@x.test"]
    chamadas: list[bytes] = []
    monkeypatch.setattr(esign, "_document_bytes", lambda document: _pdf(2))
    monkeypatch.setattr(
        esign.AutentiqueProvider,
        "_post",
        lambda self, body, content_type: chamadas.append(body)
        or _resposta_do_autentique(emails),
    )
    document = _instrumento(Document.Kind.COMMERCIAL_CONTRACT)

    code, data = _pedir(
        document,
        {
            "signers": [
                {"email": emails[0], "role": "house"},
                {"email": emails[1], "role": "counterparty"},
                {"email": emails[2], "role": "witness"},
            ]
        },
    )

    assert code == 201
    assert len(chamadas) == 1  # um `createDocument`, não três
    criadas = list(document.signature_requests.order_by("id"))
    assert [s.signer_email for s in criadas] == emails
    assert [s.signer_role for s in criadas] == ["house", "counterparty", "witness"]
    assert {s.document_ref for s in criadas} == {"doc-77"}  # a rodada é o `document_ref`
    assert [s["id"] for s in data["signatures"]] == [s.pk for s in criadas]


@pytest.mark.django_db
@LIGADA
def test_referencia_que_nao_voltou_derruba_a_rodada_inteira(monkeypatch: pytest.MonkeyPatch):
    """Dois voltarem e um não é o caso em que gravar o que voltou deixa a rodada aberta para
    sempre: a solicitação que falta não existe do lado do fornecedor e não tem como ser assinada.
    E nada é gravado — 502, no molde da rodada 4."""
    monkeypatch.setattr(esign, "_document_bytes", lambda document: _pdf(2))
    monkeypatch.setattr(
        esign.AutentiqueProvider,
        "_post",
        lambda self, body, content_type: _resposta_do_autentique(["cliente@x.test"]),
    )
    document = _instrumento(Document.Kind.COMMERCIAL_CONTRACT)

    code, _ = _pedir(
        document,
        {
            "signers": [
                {"email": "cliente@x.test", "role": "counterparty"},
                {"email": "sumiu@x.test", "role": "witness"},
            ]
        },
    )

    assert code == 502
    assert document.signature_requests.count() == 0


@pytest.mark.django_db
def test_clicksign_recusa_multiplos_signatarios_em_vez_de_fazer_laco():
    """O adaptador faz um upload por chamada: repeti-la criaria N documentos separados. Falhar
    alto é a diferença entre um adaptador incompleto e um adaptador que mente."""
    with override_settings(ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN="tok"):
        with pytest.raises(esign.EsignProviderError) as excecao:
            esign.ClicksignProvider().send(
                Document(original_name="x.pdf"),
                _papeis("counterparty", "witness"),
            )
    assert "múltiplos signatários" in str(excecao.value)


@pytest.mark.django_db
def test_clicksign_com_um_signatario_continua_identico(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(esign, "_document_bytes", lambda document: b"%PDF-1.4")
    monkeypatch.setattr(
        esign.ClicksignProvider,
        "_create_signature_request",
        lambda self, d, e, content: esign.SignatureRef("req-1", "doc-1", "https://x.test/a"),
    )
    with override_settings(ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN="tok"):
        refs = esign.ClicksignProvider().send(_document(), _um("quem@x.test"))
    assert refs == [esign.SignatureRef("req-1", "doc-1", "https://x.test/a")]


@pytest.mark.django_db
@SEM_PROVEDOR
def test_o_corpo_antigo_sem_email_da_casa_produz_o_de_sempre():
    """Reversibilidade: com `ESIGN_HOUSE_SIGNER_EMAIL` vazio, nada muda em relação a antes."""
    document = _instrumento(Document.Kind.COMMERCIAL_CONTRACT)

    code, data = _pedir(document, {"signer_email": "cliente@x.test"})

    assert code == 201
    assert len(data["signatures"]) == 1
    solicitacao = document.signature_requests.get()
    assert solicitacao.signer_email == "cliente@x.test"
    assert solicitacao.signer_role == SignatureRequest.SignerRole.COUNTERPARTY


@pytest.mark.django_db
@override_settings(
    ESIGN_ENABLED=True, ESIGN_PROVIDER="", ESIGN_HOUSE_SIGNER_EMAIL="assina@biahflow.test"
)
def test_a_casa_entra_sozinha_quando_o_email_dela_esta_configurado():
    """Quem envia não digita o próprio e-mail toda vez — e não entra duas vezes se digitar."""
    document = _instrumento(Document.Kind.COMMERCIAL_CONTRACT)

    _pedir(document, {"signer_email": "cliente@x.test"})

    papeis = dict(document.signature_requests.values_list("signer_email", "signer_role"))
    assert papeis == {
        "cliente@x.test": SignatureRequest.SignerRole.COUNTERPARTY,
        "assina@biahflow.test": SignatureRequest.SignerRole.HOUSE,
    }

    outro = _instrumento(Document.Kind.COMMERCIAL_CONTRACT, user=document.uploaded_by)
    _pedir(
        outro,
        {"signers": [{"email": "ASSINA@biahflow.test", "role": "house"},
                     {"email": "cliente@x.test", "role": "counterparty"}]},
    )
    assert outro.signature_requests.count() == 2


@pytest.mark.django_db
@SEM_PROVEDOR
def test_a_forma_nova_vence_quando_as_duas_vem_no_mesmo_corpo():
    document = _instrumento(Document.Kind.COMMERCIAL_CONTRACT)

    _pedir(
        document,
        {
            "signer_email": "antigo@x.test",
            "signers": [{"email": "novo@x.test", "role": "counterparty"}],
        },
    )

    assert [s.signer_email for s in document.signature_requests.all()] == ["novo@x.test"]


@pytest.mark.django_db
@SEM_PROVEDOR
@pytest.mark.parametrize(
    "corpo",
    [
        pytest.param({"signers": []}, id="lista-vazia"),
        pytest.param({"signers": [{"email": "a@x.test", "role": "chefe"}]}, id="papel-desconhecido"),
        pytest.param(
            {"signers": [{"email": "a@x.test", "role": "counterparty"},
                         {"email": "A@x.test", "role": "witness"}]},
            id="email-repetido",
        ),
        pytest.param({}, id="corpo-vazio"),
        pytest.param({"signers": ["a@x.test"]}, id="signatario-que-nao-e-objeto"),
    ],
)
def test_pedido_malformado_e_400_e_nao_grava_nada(corpo: dict):
    """400 e não 409: é o **corpo** que está errado, não o estado. O e-mail repetido entra aqui
    porque o fornecedor casa signatário por e-mail — dois iguais tornam o webhook ambíguo."""
    document = _instrumento(Document.Kind.COMMERCIAL_CONTRACT)

    code, _ = _pedir(document, corpo)

    assert code == 400
    assert document.signature_requests.count() == 0


# --- os quatro defeitos que só aparecem com mais de um signatário -------------


def _rodada(document: Document, ref: str = "doc-1") -> dict[str, SignatureRequest]:
    """A casa, a parte contratante e uma testemunha, todas pendentes, na mesma rodada."""
    return {
        papel: SignatureRequest.objects.create(
            document=document, signer_email=f"{papel}@x.test", signer_role=papel, document_ref=ref
        )
        for papel in ("house", "counterparty", "witness")
    }


def _assinar(signature: SignatureRequest) -> None:
    esign.apply_decision(signature.pk, SignatureRequest.Status.SIGNED)


@pytest.mark.django_db
def test_a_rodada_so_esta_assinada_quando_todos_assinaram():
    """D1. Com um signatário, "alguém assinou" e "está assinado" eram a mesma frase. Com três,
    deixaram de ser: a assinatura da **casa** tornaria o instrumento assinado antes do cliente."""
    document = _document()
    solicitacoes = _rodada(document)

    _assinar(solicitacoes["house"])
    assert document.is_signed is False

    _assinar(solicitacoes["counterparty"])
    assert document.is_signed is False

    _assinar(solicitacoes["witness"])
    assert document.is_signed is True


@pytest.mark.django_db
def test_uma_rodada_fechada_basta_mesmo_com_outra_aberta():
    """Reenviar depois de uma recusa abre rodada nova, com `document_ref` novo. Uma rodada que
    fechou não desfaz porque a seguinte está pendente."""
    document = _document()
    antiga = SignatureRequest.objects.create(
        document=document, signer_email="a@x.test", document_ref="doc-1",
        status=SignatureRequest.Status.SIGNED, signed_at=timezone.now(),
    )
    assert antiga.document.is_signed is True

    SignatureRequest.objects.create(document=document, signer_email="b@x.test", document_ref="doc-2")
    assert document.is_signed is True


@pytest.mark.django_db
def test_status_assinado_sem_data_nao_fecha_a_rodada():
    """A exigência dos dois campos juntos continua valendo: um update cru de status não transforma
    um arquivo em instrumento contratual sem carimbo temporal."""
    document = _document()
    SignatureRequest.objects.create(
        document=document, signer_email="a@x.test", document_ref="doc-1",
        status=SignatureRequest.Status.SIGNED,
    )
    assert document.is_signed is False


@pytest.mark.django_db
def test_o_contrato_so_e_aceito_quando_a_rodada_fecha():
    """D2. A assimetria é deliberada: **aceitar exige todos, recusar exige um.**"""
    user = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=user), original_name="contrato.pdf", uploaded_by=user
    )
    artifact = _contract_artifact(document, user)
    solicitacoes = _rodada(document)

    _assinar(solicitacoes["house"])
    artifact.refresh_from_db()
    assert artifact.status == Artifact.Status.SENT  # o cliente ainda nem abriu o link

    _assinar(solicitacoes["counterparty"])
    _assinar(solicitacoes["witness"])
    artifact.refresh_from_db()
    assert artifact.status == Artifact.Status.ACCEPTED


@pytest.mark.django_db
def test_uma_recusa_rejeita_o_contrato_na_hora():
    """D2, o outro lado: não há o que esperar depois de alguém dizer não."""
    user = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=user), original_name="contrato.pdf", uploaded_by=user
    )
    artifact = _contract_artifact(document, user)
    solicitacoes = _rodada(document)

    esign.apply_decision(solicitacoes["counterparty"].pk, SignatureRequest.Status.DECLINED)

    artifact.refresh_from_db()
    assert artifact.status == Artifact.Status.REJECTED
    assert solicitacoes["house"].document.signature_requests.filter(status="pending").count() == 2


@pytest.mark.django_db
def test_o_mandato_de_design_partner_nao_abre_na_assinatura_da_casa():
    """D3. `abrir_engagement_do_acordo` já é guardada por `document.is_signed` — consertar D1
    conserta este. O teste existe porque a garantia é essa, e ela não pode voltar a depender de
    sorte."""
    user = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=user),
        original_name="acordo-design-partner.pdf",
        uploaded_by=user,
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
    )
    solicitacoes = _rodada(document)

    _assinar(solicitacoes["house"])
    assert Engagement.objects.count() == 0

    _assinar(solicitacoes["counterparty"])
    _assinar(solicitacoes["witness"])
    assert Engagement.objects.filter(originating_design_partner_agreement=document).count() == 1


@pytest.mark.django_db
@override_settings(
    DISCOVERY_BOOKING_ENABLED=True, CALENDAR_ENABLED=True, GOOGLE_CALENDAR_ID="cal"
)
def test_o_convite_do_discovery_vai_para_a_contraparte_e_nao_para_quem_fechou():
    """D4. Quem assina por último pode ser a casa ou a testemunha — e o link de marcar o Discovery
    iria para quem não vai marcar nada."""
    user = UserFactory(role=User.Role.ADMIN)
    document = Document.objects.create(
        account=AccountFactory(owner=user),
        original_name="acordo-design-partner.pdf",
        uploaded_by=user,
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
    )
    solicitacoes = _rodada(document)

    _assinar(solicitacoes["counterparty"])
    _assinar(solicitacoes["witness"])
    _assinar(solicitacoes["house"])  # a casa fecha a rodada

    convites = [
        m for m in mail.outbox if m.subject == discovery_booking.CONVITE_DO_DISCOVERY.assunto
    ]
    assert [m.to for m in convites] == [["counterparty@x.test"]]


@pytest.mark.django_db
def test_rodada_sem_contraparte_nao_manda_convite_e_diz_por_que(
    caplog: pytest.LogCaptureFixture,
):
    document = _document()
    SignatureRequest.objects.create(
        document=document, signer_email="casa@x.test",
        signer_role=SignatureRequest.SignerRole.HOUSE, document_ref="doc-1",
    )

    with caplog.at_level(logging.WARNING, logger="apps.core.esign"):
        assert esign.email_da_contraparte(document, "doc-1") == ""

    assert "counterparty" in caplog.text
