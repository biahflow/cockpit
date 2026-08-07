"""Regressão: falha do enriquecimento não impede a criação do lead nem a qualificação (FDD 030).

É a regressão crítica nomeada na FDD 030, e o modo de falha é o mesmo que `qualification.qualify_lead`
já tinha fechado para a OpenAI — repetido aqui porque o enriquecimento acrescentou uma **segunda**
chamada a terceiro dentro do mesmo `POST` público, e um caminho novo não herda a guarda do antigo.

O estrago é maior do que "o lead não foi enriquecido". O `Lead` é gravado **antes** da chamada, então
uma exceção que suba vira 500 para o visitante que acabou de preencher o formulário: ele vê falha,
não tenta de novo, e a casa fica com um cadastro que funcionou e um cliente possível que desistiu.
Um provedor gratuito e sem SLA é exatamente o tipo de dependência que cai sem avisar.

A ordem também está sob teste. O enriquecimento roda **antes** da qualificação porque existe para
melhorar o `ai_fit`; invertido, ele seria um cadastro bonito que a decisão já não usou — e nada
ficaria vermelho, porque o lead continuaria enriquecido ao final.
"""

from __future__ import annotations

import urllib.error

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core import ai, enrichment
from apps.core.models import Lead

pytestmark = pytest.mark.django_db

INTAKE = override_settings(
    LEAD_INTAKE_TOKEN="secret-token", ENRICHMENT_ENABLED=True, ENRICHMENT_PROVIDER="brasilapi"
)

PAYLOAD = {
    "name": "Fulano",
    "email": "f@x.com",
    "company": "ACME",
    "cnpj": "11.222.333/0001-81",
    "message": "quero ajuda",
}


class ProviderQueCai:
    def fetch(self, cnpj: str) -> enrichment.Company | None:
        raise urllib.error.URLError("BrasilAPI fora do ar")


class ProviderQueResponde:
    def fetch(self, cnpj: str) -> enrichment.Company | None:
        return enrichment.Company(cnpj=cnpj, legal_name="ACME LTDA", cnae_code="6201501")


@INTAKE
def test_fornecedor_fora_do_ar_nao_derruba_o_formulario(monkeypatch):
    monkeypatch.setattr(enrichment, "get_provider", lambda: ProviderQueCai())
    resposta = APIClient().post(
        reverse("lead-intake"), PAYLOAD, format="json", HTTP_X_INTAKE_TOKEN="secret-token"
    )

    assert resposta.status_code == 201
    lead = Lead.objects.get()
    assert lead.email == "f@x.com" and lead.cnpj == "11.222.333/0001-81"
    assert lead.enrichment == {}


@INTAKE
def test_fornecedor_fora_do_ar_nao_impede_a_qualificacao(monkeypatch):
    """Sem enriquecimento a qualificação roda igual — com o contexto que sempre teve."""
    monkeypatch.setattr(enrichment, "get_provider", lambda: ProviderQueCai())
    chamadas: list[str] = []

    monkeypatch.setattr(ai, "is_enabled", lambda: True)
    monkeypatch.setattr(
        ai,
        "complete",
        lambda system, context, **kwargs: (
            chamadas.append(context) or ('{"fit":"high","score":90,"summary":"s","recommended_action":"r"}', {})
        ),
    )

    resposta = APIClient().post(
        reverse("lead-intake"), PAYLOAD, format="json", HTTP_X_INTAKE_TOKEN="secret-token"
    )

    assert resposta.status_code == 201
    lead = Lead.objects.get()
    assert lead.ai_fit == "high" and lead.qualified_at is not None
    assert len(chamadas) == 1 and "Empresa: ACME" in chamadas[0]


@INTAKE
def test_o_cadastro_chega_ao_contexto_da_qualificacao(monkeypatch):
    """A ordem é o ponto: enriquecer depois de qualificar não mudaria nada e nada ficaria vermelho."""
    monkeypatch.setattr(enrichment, "get_provider", lambda: ProviderQueResponde())
    chamadas: list[str] = []

    monkeypatch.setattr(ai, "is_enabled", lambda: True)
    monkeypatch.setattr(
        ai,
        "complete",
        lambda system, context, **kwargs: (
            chamadas.append(context) or ('{"fit":"high","score":90,"summary":"s","recommended_action":"r"}', {})
        ),
    )

    APIClient().post(
        reverse("lead-intake"), PAYLOAD, format="json", HTTP_X_INTAKE_TOKEN="secret-token"
    )

    assert "Razão social: ACME LTDA" in chamadas[0]
    # E o CNPJ continua fora do prompt, mesmo tendo sido a chave da consulta.
    assert "11222333000181" not in chamadas[0]


@INTAKE
def test_lead_sem_cnpj_segue_o_caminho_de_sempre(monkeypatch):
    """Manter o CNPJ opcional é decisão de produto, e o caminho sem ele tem de continuar inteiro."""
    monkeypatch.setattr(enrichment, "get_provider", lambda: ProviderQueCai())
    resposta = APIClient().post(
        reverse("lead-intake"),
        {"name": "Fulano", "email": "f@x.com"},
        format="json",
        HTTP_X_INTAKE_TOKEN="secret-token",
    )

    assert resposta.status_code == 201
    assert Lead.objects.get().enrichment == {}
