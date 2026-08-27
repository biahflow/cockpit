"""Regressão: o webhook do GitHub é idempotente nos **dois** níveis (FDD 041, ADR 0037).

O GitHub entrega *at least once* e **não garante ordem**. As duas consequências são diferentes e
precisam das duas guardas:

1. **Reentrega da mesma entrega.** `X-GitHub-Delivery` é único; a segunda não reaplica nada. É o
   nível que os webhooks anteriores deste repositório não têm — eles deduplicam por igualdade de
   estado, o que resolve a reentrega idêntica e não resolve o resto.
2. **Entrega atrasada.** Um `pull_request` de dez minutos atrás pode chegar depois do de agora,
   carregando o SHA anterior. Sem a guarda de ordem, o painel afirmaria com confiança um `head`
   que já não é o `head` — exatamente a mentira que o DAP GH-41 r1 existe para impedir.

Este arquivo entra pelo HTTP, e não pela função: é a rota inteira — assinatura, header e
transação — que precisa continuar valendo.
"""

from __future__ import annotations

import hmac
import json
from hashlib import sha256

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import GithubDelivery, GithubProjection
from apps.core.tests.factories import ProvisionedHandoffFactory

SECRET = "segredo-de-fixture"
REPO = "acme/repo"


def entregar(api: APIClient, payload: dict, *, event: str, delivery: str):
    body = json.dumps(payload).encode()
    return api.post(
        reverse("github-webhook"),
        data=body,
        content_type="application/json",
        headers={
            "X-Hub-Signature-256": "sha256=" + hmac.new(SECRET.encode(), body, sha256).hexdigest(),
            "X-GitHub-Event": event,
            "X-GitHub-Delivery": delivery,
        },
    )


def issue(estado: str, quando: str) -> dict:
    return {
        "repository": {"full_name": REPO},
        "issue": {"number": 41, "state": estado, "title": "T", "updated_at": quando},
    }


def pr(sha: str, quando: str) -> dict:
    return {
        "repository": {"full_name": REPO},
        "pull_request": {
            "number": 90,
            "state": "open",
            "head": {"sha": sha},
            "updated_at": quando,
            "title": "PR",
            "body": "Closes #41",
        },
    }


@pytest.mark.django_db
@override_settings(GITHUB_WEBHOOK_SECRET=SECRET)
def test_a_mesma_entrega_duas_vezes_nao_reaplica_nada() -> None:
    ProvisionedHandoffFactory(repository=REPO, github_issue_number=41)
    api = APIClient()

    primeira = entregar(api, issue("open", "2026-08-27T12:00:00Z"), event="issues", delivery="d-1")
    segunda = entregar(api, issue("closed", "2026-08-27T12:30:00Z"), event="issues", delivery="d-1")

    assert primeira.status_code == 200
    assert segunda.status_code == 200
    assert segunda.json()["detail"] == "Entrega já processada."
    assert GithubDelivery.objects.count() == 1
    assert GithubProjection.objects.get().issue_state == GithubProjection.IssueState.OPEN


@pytest.mark.django_db
@override_settings(GITHUB_WEBHOOK_SECRET=SECRET)
def test_entrega_atrasada_com_sha_velho_nao_derruba_o_sha_atual() -> None:
    ProvisionedHandoffFactory(repository=REPO, github_issue_number=41)
    api = APIClient()
    entregar(api, issue("open", "2026-08-27T12:00:00Z"), event="issues", delivery="d-1")
    entregar(api, pr("b" * 40, "2026-08-27T12:20:00Z"), event="pull_request", delivery="d-2")

    atrasada = entregar(api, pr("a" * 40, "2026-08-27T12:05:00Z"), event="pull_request", delivery="d-3")

    # 200 e não erro: a entrega foi processada — a decisão foi descartá-la, e o GitHub não tem
    # nada a reenviar.
    assert atrasada.status_code == 200
    assert GithubProjection.objects.get().head_sha == "b" * 40
