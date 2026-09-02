"""Regressão: webhook do fornecedor e `mark-signed` manual concluem a assinatura do mesmo jeito.

Até esta tarefa existiam **dois** caminhos que terminavam uma assinatura, e eles divergiam:
`esign.apply_event` (o webhook) gravava status/`signed_at`, fechava o artefato de contrato ligado
ao documento e notificava quem subiu o documento; `DocumentViewSet.mark_signed` — o fallback usado
sempre que não há provedor homologado — só gravava status/`signed_at`. O mesmo fato de negócio
("este documento foi assinado") produzia efeitos diferentes dependendo da porta por onde entrava.

Os dois caminhos agora passam por `esign.apply_decision`, e este teste afirma que eles deixam o
sistema no mesmo estado: artefato de contrato aceito, `signed_at` preenchido, notificação
`kind="esign"` criada — para um documento fechado pelo webhook e um documento fechado pelo
`mark-signed`, em paridade.
"""

import json

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core import esign
from apps.core.models import Artifact, Document, Notification, SignatureRequest, User
from apps.core.portal import sign
from apps.core.tests.factories import (
    AccountFactory,
    ArtifactFactory,
    CommercialOpportunityFactory,
    UserFactory,
)

SECRET = "webhook-secret"


def _contract(
    user: User, signer_email: str, provider_ref: str, document_ref: str
) -> tuple[Document, Artifact, SignatureRequest]:
    document = Document.objects.create(
        account=AccountFactory(owner=user), original_name="contrato.pdf", uploaded_by=user
    )
    artifact = ArtifactFactory(
        kind=Artifact.Kind.CONTRACT,
        commercial_opportunity=CommercialOpportunityFactory(account=document.account),
        document=document,
        status=Artifact.Status.SENT,
        created_by=user,
    )
    signature = SignatureRequest.objects.create(
        document=document, signer_email=signer_email,
        provider_ref=provider_ref, document_ref=document_ref,
    )
    return document, artifact, signature


def _webhook_event(signer_email: str, provider_ref: str, document_ref: str) -> bytes:
    return json.dumps(
        {
            "event": {"name": "sign", "data": {"user": {"email": signer_email}}},
            "document": {
                "key": document_ref,
                "signers": [{"email": signer_email, "request_signature_key": provider_ref}],
            },
        }
    ).encode()


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN="tok",
                   ESIGN_WEBHOOK_SECRET=SECRET)
def test_webhook_and_mark_signed_leave_the_same_state():
    uploader = UserFactory(role=User.Role.ADMIN)

    via_webhook_document, via_webhook_artifact, via_webhook_signature = _contract(
        uploader, "assina-webhook@x.test", provider_ref="req-webhook", document_ref="doc-webhook"
    )
    via_manual_document, via_manual_artifact, via_manual_signature = _contract(
        uploader, "assina-manual@x.test", provider_ref="req-manual", document_ref="doc-manual"
    )

    body = _webhook_event("assina-webhook@x.test", "req-webhook", "doc-webhook")
    webhook_response = APIClient().post(
        reverse("esign-webhook"),
        data=body,
        content_type="application/json",
        HTTP_CONTENT_HMAC=f"sha256={sign(SECRET, body)}",
    )
    assert webhook_response.status_code == 200

    manual_client = APIClient()
    manual_client.force_authenticate(uploader)
    manual_response = manual_client.post(
        reverse("document-mark-signed", args=[via_manual_document.pk]),
        {"signature": via_manual_signature.pk},
        format="json",
    )
    assert manual_response.status_code == 200

    via_webhook_signature.refresh_from_db()
    via_manual_signature.refresh_from_db()
    via_webhook_artifact.refresh_from_db()
    via_manual_artifact.refresh_from_db()

    for signature in (via_webhook_signature, via_manual_signature):
        assert signature.status == SignatureRequest.Status.SIGNED
        assert signature.signed_at is not None

    for artifact in (via_webhook_artifact, via_manual_artifact):
        assert artifact.status == Artifact.Status.ACCEPTED
        assert artifact.decided_at is not None

    notifications = Notification.objects.filter(kind="esign").order_by("id")
    assert notifications.count() == 2
    assert {n.user_id for n in notifications} == {uploader.pk}
    assert {n.url for n in notifications} == {"/documentos"}


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN="tok",
                   ESIGN_WEBHOOK_SECRET=SECRET)
def test_both_paths_go_through_apply_decision(monkeypatch):
    """Os dois caminhos passam pela função única — e aqui a forma é a invariante.

    O teste acima prova a convergência por **efeito**, que é o que importa para quem usa. Este
    prova que ela vem de haver um lugar só, e não de duas implementações que hoje concordam: é a
    divergência que a tarefa existe para impedir, e ela voltaria calada no dia em que alguém
    gravasse `status` à mão de novo num dos dois caminhos.
    """
    uploader = UserFactory(role=User.Role.ADMIN)
    chamadas: list[tuple[int, str]] = []
    original = esign.apply_decision

    def espiao(signature_pk: int, new_status: str) -> SignatureRequest:
        chamadas.append((signature_pk, new_status))
        return original(signature_pk, new_status)

    monkeypatch.setattr(esign, "apply_decision", espiao)

    pelo_webhook, _artefato_a, assinatura_a = _contract(
        uploader, "assina-webhook@x.test", provider_ref="req-webhook", document_ref="doc-webhook"
    )
    manual, _artefato_b, assinatura_b = _contract(
        uploader, "assina-manual@x.test", provider_ref="req-manual", document_ref="doc-manual"
    )

    body = _webhook_event("assina-webhook@x.test", "req-webhook", "doc-webhook")
    assert APIClient().post(
        reverse("esign-webhook"), data=body, content_type="application/json",
        HTTP_CONTENT_HMAC=f"sha256={sign(SECRET, body)}",
    ).status_code == 200

    manual_client = APIClient()
    manual_client.force_authenticate(uploader)
    assert manual_client.post(
        reverse("document-mark-signed", args=[manual.pk]),
        {"signature": assinatura_b.pk}, format="json",
    ).status_code == 200

    assert chamadas == [
        (assinatura_a.pk, SignatureRequest.Status.SIGNED),
        (assinatura_b.pk, SignatureRequest.Status.SIGNED),
    ]
    assert pelo_webhook.pk != manual.pk
