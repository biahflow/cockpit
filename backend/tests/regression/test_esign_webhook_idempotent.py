"""Regressão: reentrega do mesmo evento de assinatura não muda nada (ADR 0007, FDD 009).

Fornecedores de assinatura reentregam o webhook até receber 200 — a segunda entrega não pode
recarimbar `signed_at` nem gerar uma segunda notificação para quem enviou o documento.
"""

import json

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Document, Notification, SignatureRequest
from apps.core.portal import sign
from apps.core.tests.factories import AccountFactory, UserFactory

SECRET = "webhook-secret"


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN="tok",
                   ESIGN_WEBHOOK_SECRET=SECRET)
def test_duplicate_delivery_keeps_signed_at_and_single_notification() -> None:
    user = UserFactory()
    document = Document.objects.create(
        account=AccountFactory(owner=user), original_name="contrato.pdf", uploaded_by=user
    )
    signature = SignatureRequest.objects.create(
        document=document, signer_email="quem@x.test", provider_ref="req-1", document_ref="doc-1"
    )
    body = json.dumps(
        {
            "event": {"name": "sign", "data": {"user": {"email": "quem@x.test"}}},
            "document": {
                "key": "doc-1",
                "signers": [{"email": "quem@x.test", "request_signature_key": "req-1"}],
            },
        }
    ).encode()
    post = lambda: APIClient().post(  # noqa: E731
        reverse("esign-webhook"),
        data=body,
        content_type="application/json",
        HTTP_CONTENT_HMAC=f"sha256={sign(SECRET, body)}",
    )

    assert post().status_code == 200
    signature.refresh_from_db()
    first_signed_at = signature.signed_at

    assert post().status_code == 200
    signature.refresh_from_db()

    assert signature.status == SignatureRequest.Status.SIGNED
    assert signature.signed_at == first_signed_at
    assert Notification.objects.filter(user=user, kind="esign").count() == 1
