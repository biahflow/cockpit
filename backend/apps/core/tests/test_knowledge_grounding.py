"""Recuperação, ancoragem e citar-ou-declarar-lacuna (FDD 029, ADR 0023).

O modelo é dublado de propósito: o que estes testes protegem **não** é a qualidade da recuperação
— isso é pergunta de homologação —, é que a regra valha **independentemente do que o modelo
alegou**. Um dublê que devolve um marcador inventado é a forma direta de provar isso.
"""

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import ai, knowledge
from apps.core.models import KnowledgeArea, KnowledgeChunk, KnowledgePiece

from .factories import UserFactory

COM_IA = override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")


def _vetor(semente: float) -> list[float]:
    """Vetor com direção controlada, para a similaridade ser previsível no teste."""
    base = [0.0] * knowledge.EMBEDDING_DIMENSIONS
    base[0] = semente
    base[1] = 1.0 - abs(semente)
    return base


@pytest.fixture
def peca_indexada():
    area = KnowledgeArea.objects.get(slug="operacao")
    area.owner = UserFactory(role="admin")
    area.save(update_fields=["owner"])
    peca = KnowledgePiece.objects.create(
        area=area, title="ADR 0013 — Backup lógico", kind=KnowledgePiece.Kind.DECISION,
        source_path="docs/adr/0013.md", review_interval_days=0,
    )
    KnowledgeChunk.objects.create(
        piece=peca, position=0, heading_path="ADR 0013 — Backup lógico › Decisão",
        content="Dump lógico com pg_dump --format=custom, num sidecar próprio.",
        content_hash="h1", embedding=_vetor(1.0), embedding_model="text-embedding-3-small",
    )
    return peca


# --- Busca --------------------------------------------------------------------


@pytest.mark.django_db
def test_busca_devolve_o_mais_proximo(peca_indexada):
    hits = knowledge.search(_vetor(1.0))
    assert len(hits) == 1
    assert hits[0].heading_path.endswith("Decisão")
    assert hits[0].similarity > 0.99


@pytest.mark.django_db
def test_busca_ignora_trecho_de_outro_modelo_de_embedding(peca_indexada):
    """Índice metade num espaço vetorial e metade noutro é defeito que não dá erro."""
    KnowledgeChunk.objects.update(embedding_model="modelo-antigo")
    assert knowledge.search(_vetor(1.0)) == []


@pytest.mark.django_db
def test_busca_ignora_peca_arquivada(peca_indexada):
    peca_indexada.archive()
    assert knowledge.search(_vetor(1.0)) == []


# --- Roteamento por limiar ----------------------------------------------------


@pytest.mark.django_db
def test_pergunta_irrelevante_nao_ancora_nada(peca_indexada, monkeypatch):
    """O `None` é a peça central: sem ele, toda pergunta operacional viraria lacuna."""
    monkeypatch.setattr(ai, "embed", lambda textos: [_vetor(-1.0)])
    with COM_IA:
        assert knowledge.ground("o que está atrasado?") is None


@pytest.mark.django_db
def test_pergunta_relevante_ancora(peca_indexada, monkeypatch):
    monkeypatch.setattr(ai, "embed", lambda textos: [_vetor(1.0)])
    with COM_IA:
        grounding = knowledge.ground("como restaurar o backup?")
    assert grounding is not None
    assert "[K1]" in grounding.block
    assert "pg_dump" in grounding.block


@pytest.mark.django_db
def test_ia_desligada_nao_ancora(peca_indexada):
    with override_settings(AI_ENABLED=False):
        assert knowledge.ground("qualquer coisa") is None


@pytest.mark.django_db
def test_falha_no_embedding_degrada_em_vez_de_derrubar(peca_indexada, monkeypatch):
    """A pergunta ainda pode ser respondida pelos dados da área."""
    def estoura(textos):
        raise ai.AiProviderError("429")

    monkeypatch.setattr(ai, "embed", estoura)
    with COM_IA:
        assert knowledge.ground("como restaurar?") is None


@pytest.mark.django_db
def test_trecho_vencido_vai_marcado(peca_indexada, monkeypatch):
    """A segunda cláusula da regressão: vencido aparece como vencido, e não como corrente."""
    KnowledgePiece.objects.filter(pk=peca_indexada.pk).update(
        review_interval_days=30, last_verified_at=timezone.localdate() - timedelta(days=90)
    )
    monkeypatch.setattr(ai, "embed", lambda textos: [_vetor(1.0)])
    with COM_IA:
        grounding = knowledge.ground("como restaurar o backup?")
    assert "VENCIDO" in grounding.block
    assert grounding.hits[0].stale is True


# --- Citar ou declarar a lacuna -----------------------------------------------


def _grounding_falso():
    hit = knowledge.Hit(
        chunk_id=1, piece_id=2, title="ADR 0013", heading_path="Decisão",
        content="…", source_path="docs/adr/0013.md", similarity=0.9, stale=False,
    )
    return knowledge.Grounding(hits=[hit], block="[K1] ADR 0013 › Decisão\n…")


def test_marcador_valido_preserva_o_texto_e_resolve_a_fonte():
    texto, fontes = knowledge.enforce_citations("O backup é um dump lógico [K1].", _grounding_falso())
    assert texto == "O backup é um dump lógico [K1]."
    assert len(fontes) == 1
    assert fontes[0]["path"] == "docs/adr/0013.md"
    assert fontes[0]["stale"] is False


def test_marcador_inventado_some_e_nao_conta():
    """O buraco que o repositório vizinho já achou: o que o modelo alegou não vale."""
    texto, fontes = knowledge.enforce_citations("O backup é semanal [K9].", _grounding_falso())
    assert fontes == []
    assert texto.startswith(knowledge.LACUNA)
    assert "[K9]" not in texto


def test_alegar_metodologia_sem_sustentar_vira_lacuna():
    """Substituída, não anotada: texto sem fonte pendurado na tela é o modo de falha da FDD."""
    texto, fontes = knowledge.enforce_citations(
        "A política de backup da casa é semanal e roda aos domingos.\nFONTE: [K4]",
        _grounding_falso(),
    )
    assert texto.startswith(knowledge.LACUNA)
    assert "domingos" not in texto
    assert fontes == []


def test_a_lacuna_diz_o_que_foi_consultado():
    """Quem lê precisa julgar se o corpus é raso ou se a pergunta é que estava fora dele."""
    texto, _ = knowledge.enforce_citations("Resposta sem fonte.\nFONTE: [K3]", _grounding_falso())
    assert "ADR 0013" in texto


def test_citacao_so_na_linha_de_fonte_conta(caplog):
    """**Achado da rodada 5**, e o mais caro: a resposta certa era destruída pela regra.

    O prompt manda terminar com `FONTE: [K1]`, e o `gpt-4o-mini` faz exatamente isso — cita **só**
    ali. A primeira versão removia a linha antes de procurar marcador, então nada resolvia e a
    lacuna substituía uma resposta correta, com os comandos exatos do runbook. Nenhum dublê acharia
    isto: ele citaria onde o teste mandasse.
    """
    texto, fontes = knowledge.enforce_citations(
        "O backup é um dump lógico num sidecar próprio.\nFONTE: [K1]", _grounding_falso()
    )
    assert texto == "O backup é um dump lógico num sidecar próprio."
    assert [f["ref"] for f in fontes] == ["K1"]
    assert "FONTE:" not in texto  # a declaração é máquina, não vai para a tela


def test_resposta_operacional_declarada_passa_intacta():
    """**Achado da rodada 5**: a medição mostrou que limiar nenhum separa método de dados.

    Faixas reais contra este corpus: metodologia 51–69%, operacional 47–56%. Elas **se sobrepõem**,
    então o desenho original — em que o limiar decidia se a regra valia — transformaria "o que está
    atrasado?" em "não encontrei isso no material". Quem sabe qual pergunta está respondendo é o
    modelo, e é ele que declara.
    """
    texto, fontes = knowledge.enforce_citations(
        "Não há projetos ativos, portanto nada atrasado.\nFONTE: dados da área", _grounding_falso()
    )
    assert texto == "Não há projetos ativos, portanto nada atrasado."
    assert fontes == []


def test_sem_declaracao_e_sem_marcador_passa_mas_fica_registrado(caplog):
    """O modelo não seguiu a instrução. Passa — pode ser operacional — e o log denuncia a deriva."""
    texto, fontes = knowledge.enforce_citations("Uma resposta qualquer.", _grounding_falso())
    assert texto == "Uma resposta qualquer."
    assert fontes == []
    assert "sem declaração de FONTE" in caplog.text


def test_marcador_valido_entre_invalidos_sobrevive():
    grounding = _grounding_falso()
    texto, fontes = knowledge.enforce_citations("Um [K1] e outro [K7].", grounding)
    assert "[K1]" in texto and "[K7]" not in texto
    assert [f["ref"] for f in fontes] == ["K1"]


# --- Ponta a ponta pela rota do agente ---------------------------------------


@pytest.mark.django_db
def test_agente_devolve_citacoes_e_grava_a_trilha(peca_indexada, monkeypatch):
    monkeypatch.setattr(ai, "embed", lambda textos: [_vetor(1.0)])
    monkeypatch.setattr(ai, "complete", lambda *a, **k: ("Use pg_dump [K1].", {}))
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))

    with COM_IA:
        resposta = client.post("/api/v1/agents/entrega/", {"question": "como restaurar?"},
                               format="json")
    assert resposta.status_code == 200
    assert resposta.data["sources"][0]["title"] == "ADR 0013 — Backup lógico"

    from apps.core.models import AiInteraction
    assert AiInteraction.objects.get(pk=resposta.data["interaction"]).sources


@pytest.mark.django_db
def test_pergunta_operacional_segue_como_antes(peca_indexada, monkeypatch):
    """Sem ancoragem não há `sources` e nada muda — é o contrato dos agentes que já existiam."""
    monkeypatch.setattr(ai, "embed", lambda textos: [_vetor(-1.0)])
    monkeypatch.setattr(ai, "complete", lambda *a, **k: ("Três tarefas atrasadas.", {}))
    client = APIClient()
    client.force_authenticate(UserFactory(role="admin"))

    with COM_IA:
        resposta = client.post("/api/v1/agents/entrega/", {"question": "o que está atrasado?"},
                               format="json")
    assert resposta.data["text"] == "Três tarefas atrasadas."
    assert "sources" not in resposta.data
