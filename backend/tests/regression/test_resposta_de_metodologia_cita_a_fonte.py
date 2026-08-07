"""Regressão: o agente não afirma metodologia sem citar, e declara a lacuna (FDD 029, ADR 0023).

É a primeira cláusula da "Regressão crítica" da FDD, e a razão de a citação existir: um humano que
não sabe diz "não tenho certeza"; **um modelo sobre corpus incompleto inventa resposta plausível**.
Resposta sem fonte é defeito, não estilo.

O ponto destes testes é que a regra vale **independentemente do que o modelo alegou** — a imposição
é código, não instrução. Um dublê que devolve marcador inventado prova isso de forma direta.
"""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.core import ai, knowledge
from apps.core.models import AiInteraction, KnowledgeArea, KnowledgeChunk, KnowledgePiece
from apps.core.tests.factories import UserFactory

COM_IA = override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")


def _vetor(semente: float) -> list[float]:
    base = [0.0] * knowledge.EMBEDDING_DIMENSIONS
    base[0], base[1] = semente, 1.0 - abs(semente)
    return base


@pytest.fixture
def corpus():
    area = KnowledgeArea.objects.get(slug="operacao")
    area.owner = UserFactory(role="admin")
    area.save(update_fields=["owner"])
    peca = KnowledgePiece.objects.create(
        area=area, title="Runbook — backup", source_path="docs/runbooks/backup.md",
        kind=KnowledgePiece.Kind.PROCEDURE, review_interval_days=0,
    )
    KnowledgeChunk.objects.create(
        piece=peca, position=0, heading_path="Runbook — backup › Restaurar",
        content="restore.sh --latest --yes", content_hash="h",
        embedding=_vetor(1.0), embedding_model="text-embedding-3-small",
    )
    return peca


@pytest.fixture
def perguntar(monkeypatch):
    def _perguntar(resposta_do_modelo: str, pergunta: str = "como restauro o backup?"):
        monkeypatch.setattr(ai, "embed", lambda textos: [_vetor(1.0)])
        monkeypatch.setattr(ai, "complete", lambda *a, **k: (resposta_do_modelo, {}))
        client = APIClient()
        client.force_authenticate(UserFactory(role="admin"))
        with COM_IA:
            return client.post("/api/v1/agents/entrega/", {"question": pergunta}, format="json")
    return _perguntar


@pytest.mark.django_db
def test_citacao_valida_preserva_a_resposta(corpus, perguntar):
    resposta = perguntar("Rode restore.sh --latest --yes.\nFONTE: [K1]")
    assert "restore.sh" in resposta.data["text"]
    assert resposta.data["sources"][0]["title"] == "Runbook — backup"
    assert resposta.data["sources"][0]["path"] == "docs/runbooks/backup.md"


@pytest.mark.django_db
def test_marcador_forjado_nao_sustenta_a_resposta(corpus, perguntar):
    """O buraco central: o modelo alega ter citado, e o marcador não corresponde a nada enviado."""
    resposta = perguntar("O backup roda aos domingos.\nFONTE: [K7]")
    assert resposta.data["text"].startswith(knowledge.LACUNA)
    assert "domingos" not in resposta.data["text"]
    assert resposta.data["sources"] == []


@pytest.mark.django_db
def test_a_lacuna_substitui_em_vez_de_anotar(corpus, perguntar):
    """Anotar deixaria a resposta sem fonte **na tela**, que é o que a FDD chama de pior que nada."""
    inventado = "A política da casa manda backup semanal aos domingos, às 3h."
    resposta = perguntar(f"{inventado}\nFONTE: [K9]")
    assert inventado not in resposta.data["text"]


@pytest.mark.django_db
def test_a_trilha_da_citacao_fica_gravada(corpus, perguntar):
    """Torna "resposta sem citação é defeito" auditável depois do fato, não só no instante."""
    resposta = perguntar("Rode restore.sh.\nFONTE: [K1]")
    interacao = AiInteraction.objects.get(pk=resposta.data["interaction"])
    assert interacao.sources
    assert interacao.sources[0]["ref"] == "K1"


@pytest.mark.django_db
def test_a_declaracao_nao_vaza_para_a_tela(corpus, perguntar):
    """`FONTE:` é protocolo entre o código e o modelo; quem lê não tem nada com isso."""
    resposta = perguntar("Rode restore.sh.\nFONTE: [K1]")
    assert "FONTE:" not in resposta.data["text"]


@pytest.mark.django_db
def test_pergunta_sem_material_nao_muda_o_comportamento_de_antes(corpus, monkeypatch):
    """Abaixo do piso nada é injetado, e o agente responde como respondia antes desta FDD.

    É o que impede que uma pergunta operacional vire lacuna — e a rodada 5 mostrou que isso não é
    hipotético: as faixas de similaridade de "método" e "dados" se sobrepõem.
    """
    monkeypatch.setattr(ai, "embed", lambda textos: [_vetor(-1.0)])
    monkeypatch.setattr(ai, "complete", lambda *a, **k: ("Nada atrasado.", {}))
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))
    with COM_IA:
        resposta = client.post("/api/v1/agents/entrega/", {"question": "o que atrasou?"},
                               format="json")
    assert resposta.data["text"] == "Nada atrasado."
    assert "sources" not in resposta.data
