"""A busca vetorial contra um Postgres de verdade (FDD 029, ADR 0022).

Estes testes existem porque a suíte roda em **SQLite** e a produção em **Postgres**: sem eles, o
único caminho de busca exercitado seria justamente o que nunca roda no ar. Pulam limpo fora do
Postgres e são o alvo do job `backend-pgvector` do CI.
"""

import pytest
from django.db import connection

from apps.core import knowledge
from apps.core.models import KnowledgeArea, KnowledgeChunk, KnowledgePiece

pytestmark = [
    pytest.mark.pgvector,
    pytest.mark.django_db,
    pytest.mark.skipif(
        connection.vendor != "postgresql", reason="exige Postgres com a extensão vector"
    ),
]


def _vetor(a: float, b: float) -> list[float]:
    base = [0.0] * knowledge.EMBEDDING_DIMENSIONS
    base[0], base[1] = a, b
    return base


@pytest.fixture
def indexados():
    area = KnowledgeArea.objects.get(slug="produto")
    peca = KnowledgePiece.objects.create(area=area, title="ADR", source_path="docs/adr/x.md")
    for posicao, (a, b) in enumerate([(1.0, 0.0), (0.7, 0.7), (0.0, 1.0), (-1.0, 0.0)]):
        KnowledgeChunk.objects.create(
            piece=peca, position=posicao, heading_path=f"ADR › {posicao}", content=f"t{posicao}",
            content_hash=f"h{posicao}", embedding=_vetor(a, b),
            embedding_model="text-embedding-3-small",
        )
    return peca


def test_a_extensao_existe_e_a_coluna_e_vetor(indexados):
    with connection.cursor() as cursor:
        cursor.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        assert cursor.fetchone() is not None
        cursor.execute(
            "SELECT udt_name FROM information_schema.columns "
            "WHERE table_name = 'core_knowledgechunk' AND column_name = 'embedding'"
        )
        assert cursor.fetchone()[0] == "vector"


def test_o_vetor_faz_round_trip_no_postgres(indexados):
    chunk = KnowledgeChunk.objects.get(position=0)
    assert len(chunk.embedding) == knowledge.EMBEDDING_DIMENSIONS
    assert abs(float(chunk.embedding[0]) - 1.0) < 1e-6


def test_ordena_pelo_mais_proximo(indexados):
    hits = knowledge.search(_vetor(1.0, 0.0), limit=3)
    assert [h.heading_path for h in hits] == ["ADR › 0", "ADR › 1", "ADR › 2"]


def test_os_dois_rankers_concordam(indexados):
    """**O teste que torna o caminho do SQLite confiável em vez de apenas verde.**

    Duas implementações da mesma regra é o preço de a suíte rodar num banco e a produção noutro.
    O que impede a segunda de divergir em silêncio é comparar as duas com os mesmos vetores — e é
    aqui, contra o Postgres de verdade, que a comparação vale alguma coisa.
    """
    consulta = KnowledgeChunk.objects.filter(
        embedding__isnull=False, embedding_model="text-embedding-3-small",
        piece__archived_at__isnull=True,
    ).select_related("piece", "piece__area", "piece__area__owner")

    for alvo in (_vetor(1.0, 0.0), _vetor(0.5, 0.5), _vetor(0.0, 1.0)):
        sql = knowledge._rank_sql(consulta, alvo, 4)
        python = knowledge._rank_python(consulta, alvo, 4)
        assert [h.chunk_id for h in sql] == [h.chunk_id for h in python]
        for a, b in zip(sql, python, strict=True):
            assert abs(a.similarity - b.similarity) < 1e-5
