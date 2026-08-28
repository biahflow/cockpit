"""Regressão: o corpus interno nunca é servido a um contexto de cliente (FDD 029).

Terceira cláusula da FDD, e a que não pode ser **só** um teste verde. O corpus é a metodologia da
casa — ADRs, FDDs, runbooks — e ele fala de margem, de decisão interna e de como a operação
funciona por dentro. Nada disso pode alcançar uma proposta, um contrato ou o portal do cliente.

A prova tem duas camadas de propósito. A **comportamental** (a sentinela) pega o vazamento que
existe; a **estrutural** pega o que ainda não existe — porque o jeito de isto quebrar no futuro não
é alguém escrever "vaze o corpus", é alguém pendurar recuperação num construtor de contexto que já
vai ao cliente, e achar que está ajudando.
"""

import inspect

import pytest
from django.test import override_settings

from apps.core import ai, knowledge, portal
from apps.core.models import (
    Account,
    Document,
    KnowledgeArea,
    KnowledgeChunk,
    KnowledgePiece,
    Project,
)
from apps.core.tests.factories import (
    CommercialOpportunityFactory,
    ProjectFactory,
)

SENTINELA = "MARGEM-INTERNA-NAO-PODE-VAZAR-7f3a"


@pytest.fixture
def corpus_com_sentinela():
    area = KnowledgeArea.objects.get(slug="produto")
    peca = KnowledgePiece.objects.create(
        area=area, title="ADR interna", source_path="docs/adr/9999-interna.md"
    )
    vetor = [0.0] * knowledge.EMBEDDING_DIMENSIONS
    vetor[0] = 1.0
    KnowledgeChunk.objects.create(
        piece=peca, position=0, heading_path="ADR interna › Decisão",
        content=f"A margem alvo da casa é {SENTINELA}.", content_hash="h",
        embedding=vetor, embedding_model="text-embedding-3-small",
    )
    return peca


# --- Camada comportamental ----------------------------------------------------


@pytest.mark.django_db
def test_o_snapshot_do_portal_nao_carrega_o_corpus(corpus_com_sentinela):
    projeto = ProjectFactory()
    assert SENTINELA not in str(portal.build_snapshot(projeto))


@pytest.mark.django_db
def test_o_contexto_de_proposta_nao_carrega_o_corpus(corpus_com_sentinela):
    """`build_opportunity_context` alimenta proposta e contrato — o que o **cliente lê**."""
    oportunidade = CommercialOpportunityFactory()
    assert SENTINELA not in ai.build_opportunity_context(oportunidade)


@pytest.mark.django_db
def test_o_contexto_de_projeto_nao_carrega_o_corpus(corpus_com_sentinela):
    projeto = ProjectFactory()
    assert SENTINELA not in ai.build_project_context(projeto)


@pytest.mark.django_db
@override_settings(AI_ENABLED=True, OPENAI_API_KEY="sk-teste")
def test_documento_de_projeto_continua_entrando_so_como_nome(corpus_com_sentinela):
    """O anti-vazamento que já existia não afrouxou: conteúdo de documento nunca entrou, e segue.

    Esta FDD **não** ingere `Document`. O corpus é a metodologia, versionada e revisada — trazer
    arquivo de cliente para cá é outra natureza de problema, e está declarado fora do recorte.
    """
    projeto = ProjectFactory()
    Document.objects.create(
        project=projeto, original_name="contrato-secreto.pdf", uploaded_by=projeto.owner
    )
    contexto = ai.build_project_context(projeto)
    assert "contrato-secreto.pdf" in contexto  # o nome, sim
    assert not KnowledgeChunk.objects.filter(content__icontains="contrato-secreto").exists()


# --- Camada estrutural --------------------------------------------------------


def test_portal_e_ai_nao_alcancam_o_corpus():
    """A guarda para o defeito que **ainda não existe**.

    `portal.py` fala com o cliente; `ai.py` monta o contexto de proposta e contrato. Nenhum dos
    dois pode importar `knowledge` — e conferir isso na fonte custa duas linhas e pega a intenção
    errada antes de ela virar vazamento.
    """
    for modulo in (portal, ai):
        fonte = inspect.getsource(modulo)
        assert "knowledge" not in fonte, (
            f"{modulo.__name__} não pode alcançar o corpus interno (FDD 029)"
        )


def test_o_trecho_nao_tem_vinculo_com_dado_de_cliente():
    """Anti-vazamento em forma de esquema: não há FK por onde conteúdo de cliente entrar."""
    proibidos = {Project, Account, Document}
    relacionados = {
        campo.related_model
        for campo in KnowledgeChunk._meta.get_fields()
        if campo.is_relation and campo.related_model is not None
    }
    assert not (relacionados & proibidos)


def test_a_ingestao_so_aceita_caminho_do_manifesto():
    """O corpus é o que o manifesto declara — não um diretório que alguém apontar."""
    declarados = {alvo for alvo, _, _ in knowledge.KB_SOURCES}
    for caminho in {linha["source_path"] for linha in knowledge.load_corpus()}:
        assert any(caminho == alvo or caminho.startswith(f"{alvo}/") for alvo in declarados), (
            f"{caminho} entrou no corpus sem estar no manifesto"
        )


def test_o_trecho_nao_tem_rota():
    """A única saída do texto do trecho é o `AgentView`; não há endpoint que o sirva cru."""
    from apps.core import urls

    registrados = {rota[0] for rota in urls.router.registry}
    assert not any("chunk" in nome for nome in registrados)
