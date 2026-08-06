"""Regressão: contrato assinado no fornecedor fecha o artefato sozinho (FDD 016, ADR 0007).

A decisão do signatário é a fonte da verdade do contrato — se ela não chegasse ao artefato, o
funil por etapa mostraria contratos eternamente "enviados" e a conversão medida seria falsa.
A reentrega do webhook (que os fornecedores fazem até receber 200) não pode recarimbar a decisão.
"""

import json

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Artifact, Document, SignatureRequest
from apps.core.portal import sign
from apps.core.tests.factories import ClientFactory, OpportunityFactory, UserFactory

SECRET = "webhook-secret"


def _post(body: bytes):  # type: ignore[no-untyped-def]
    return APIClient().post(
        reverse("esign-webhook"),
        data=body,
        content_type="application/json",
        HTTP_CONTENT_HMAC=f"sha256={sign(SECRET, body)}",
    )


def _event(name: str) -> bytes:
    return json.dumps(
        {
            "event": {"name": name, "data": {"user": {"email": "quem@x.test"}}},
            "document": {
                "key": "doc-1",
                "signers": [{"email": "quem@x.test", "request_signature_key": "req-1"}],
            },
        }
    ).encode()


def _contract(user):  # type: ignore[no-untyped-def]
    document = Document.objects.create(
        client=ClientFactory(owner=user), original_name="contrato.pdf", uploaded_by=user
    )
    SignatureRequest.objects.create(
        document=document, signer_email="quem@x.test", provider_ref="req-1", document_ref="doc-1"
    )
    return Artifact.objects.create(
        kind=Artifact.Kind.CONTRACT,
        title="Contrato — Acme",
        opportunity=OpportunityFactory(),
        document=document,
        status=Artifact.Status.SENT,
        created_by=user,
    )


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN="tok",
                   ESIGN_WEBHOOK_SECRET=SECRET)
def test_signature_accepts_the_contract_artifact_once() -> None:
    artifact = _contract(UserFactory())

    assert _post(_event("sign")).status_code == 200
    artifact.refresh_from_db()
    assert artifact.status == Artifact.Status.ACCEPTED
    first_decided_at = artifact.decided_at
    assert first_decided_at is not None

    assert _post(_event("sign")).status_code == 200
    artifact.refresh_from_db()

    assert artifact.status == Artifact.Status.ACCEPTED
    assert artifact.decided_at == first_decided_at


@pytest.mark.django_db
@override_settings(ESIGN_ENABLED=True, ESIGN_PROVIDER="clicksign", ESIGN_API_TOKEN="tok",
                   ESIGN_WEBHOOK_SECRET=SECRET)
def test_refusal_rejects_the_contract_artifact() -> None:
    artifact = _contract(UserFactory())

    assert _post(_event("refusal")).status_code == 200
    artifact.refresh_from_db()

    assert artifact.status == Artifact.Status.REJECTED
    assert artifact.decided_at is not None
