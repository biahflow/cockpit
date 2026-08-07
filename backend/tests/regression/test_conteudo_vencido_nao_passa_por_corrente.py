"""Regressão: conteúdo vencido aparece como vencido (FDD 029), segunda cláusula da FDD.

O modo de falha específico é o pior dos dois: um modelo sobre corpus **velho** lava informação
desatualizada com fluência confiante. Servir um runbook de seis meses atrás como corrente é mais
perigoso que não ter runbook, porque quem lê age achando que conferiu.

Isto só é implementável porque o trecho alcança a frescura da peça — se corpus e governança fossem
tabelas sem relação, esta cláusula seria insatisfazível.
"""

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import ai, knowledge
from apps.core.models import KnowledgeArea, KnowledgeChunk, KnowledgePiece
from apps.core.tests.factories import UserFactory

COM_IA = override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")


def _vetor() -> list[float]:
    base = [0.0] * knowledge.EMBEDDING_DIMENSIONS
    base[0] = 1.0
    return base


@pytest.fixture
def peca_vencida():
    area = KnowledgeArea.objects.get(slug="operacao")
    area.owner = UserFactory(role="admin")
    area.save(update_fields=["owner"])
    peca = KnowledgePiece.objects.create(
        area=area, title="Runbook — produção", source_path="docs/runbooks/producao.md",
        kind=KnowledgePiece.Kind.PROCEDURE, review_interval_days=90,
        last_verified_at=timezone.localdate() - timedelta(days=200),
    )
    KnowledgeChunk.objects.create(
        piece=peca, position=0, heading_path="Runbook — produção › HSTS",
        content="Ligue o HSTS por último.", content_hash="h",
        embedding=_vetor(), embedding_model="text-embedding-3-small",
    )
    return peca


@pytest.mark.django_db
def test_o_inventario_diz_que_venceu(peca_vencida):
    assert knowledge.freshness(peca_vencida) == knowledge.VENCIDO


@pytest.mark.django_db
def test_o_material_injetado_vai_marcado(peca_vencida, monkeypatch):
    monkeypatch.setattr(ai, "embed", lambda textos: [_vetor()])
    with COM_IA:
        grounding = knowledge.ground("como ligar o HSTS?")
    assert "VENCIDO" in grounding.block


@pytest.mark.django_db
def test_a_citacao_devolvida_marca_o_vencimento(peca_vencida, monkeypatch):
    """Quem lê a resposta precisa saber que a fonte está vencida — senão a citação legitima o velho."""
    monkeypatch.setattr(ai, "embed", lambda textos: [_vetor()])
    monkeypatch.setattr(ai, "complete", lambda *a, **k: ("Ligue por último [K1].\nFONTE: [K1]", {}))
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))
    with COM_IA:
        resposta = client.post("/api/v1/agents/entrega/", {"question": "como ligar o HSTS?"},
                               format="json")
    assert resposta.data["sources"][0]["stale"] is True


@pytest.mark.django_db
def test_verificar_tira_a_peca_de_vencida(peca_vencida):
    """E o caminho de volta funciona: a disciplina só vale se der para sair do vermelho."""
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))
    client.post(f"/api/v1/knowledge-pieces/{peca_vencida.id}/verify/")
    peca_vencida.refresh_from_db()
    assert knowledge.freshness(peca_vencida) == knowledge.CORRENTE


@pytest.mark.django_db
def test_peca_corrente_nao_vai_marcada(peca_vencida, monkeypatch):
    KnowledgePiece.objects.filter(pk=peca_vencida.pk).update(
        last_verified_at=timezone.localdate()
    )
    monkeypatch.setattr(ai, "embed", lambda textos: [_vetor()])
    with COM_IA:
        grounding = knowledge.ground("como ligar o HSTS?")
    assert "VENCIDO" not in grounding.block
    assert grounding.hits[0].stale is False
