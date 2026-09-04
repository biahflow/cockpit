"""Regressão: webhook do fornecedor e `mark-signed` manual abrem o mandato de Design Partner igual.

A tarefa anterior (`test_os_dois_caminhos_de_assinatura_convergem.py`) uniu os dois caminhos de
assinatura em `esign.apply_decision` justamente para que uma automação nova, pendurada uma única
vez ali, valesse para os dois. Esta tarefa pendura `design_partner.abrir_engagement_do_acordo`
nesse mesmo ponto — e ela regride calada no dia em que alguém automatizar só um dos dois caminhos
(por exemplo, chamando-a direto de `DocumentViewSet.mark_signed` em vez de deixar `apply_decision`
fazer isso pelos dois).

Este teste assina um Design Partner Agreement pelo webhook e outro pelo `mark-signed`, e afirma
que os dois abrem o `Engagement` de parceria, com o mesmo formato.
"""

import json

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Document, Engagement, SignatureRequest, User
from apps.core.portal import sign
from apps.core.tests.factories import AccountFactory, UserFactory

SECRET = "webhook-secret"


def _partner_agreement(user: User, signer_email: str, provider_ref: str, document_ref: str):
    document = Document.objects.create(
        account=AccountFactory(owner=user),
        original_name="acordo-design-partner.pdf",
        uploaded_by=user,
        kind=Document.Kind.DESIGN_PARTNER_AGREEMENT,
    )
    signature = SignatureRequest.objects.create(
        document=document, signer_email=signer_email,
        provider_ref=provider_ref, document_ref=document_ref,
    )
    return document, signature


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
def test_os_dois_caminhos_abrem_o_mandato_igualmente():
    uploader = UserFactory(role=User.Role.ADMIN)

    via_webhook_document, via_webhook_signature = _partner_agreement(
        uploader, "patrocinador-webhook@x.test", provider_ref="req-webhook", document_ref="doc-webhook"
    )
    via_manual_document, via_manual_signature = _partner_agreement(
        uploader, "patrocinador-manual@x.test", provider_ref="req-manual", document_ref="doc-manual"
    )

    body = _webhook_event("patrocinador-webhook@x.test", "req-webhook", "doc-webhook")
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

    for document, account_id in (
        (via_webhook_document, via_webhook_document.account_id),
        (via_manual_document, via_manual_document.account_id),
    ):
        engagement = Engagement.objects.get(originating_design_partner_agreement=document)
        assert engagement.account_id == account_id
        assert engagement.commercial_model == Engagement.CommercialModel.DESIGN_PARTNER
        assert engagement.owner_id == uploader.pk
