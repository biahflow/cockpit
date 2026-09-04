"""O campo derivado `publication_state` (issue `#108`, DAP `dap-publicacao-discovery-r1`,
decisão E1) — os quatro estados que a tela de publicação lê, a paridade de frase com
`publication.py`, e a emissão read-only nos cinco recursos publicáveis.

`publication.estado_de_publicacao` é o único lugar que decide o estado; este arquivo testa a
função diretamente (os quatro estados) e, para as frases, também **através do serializer**
(`GET` na API) — é o segundo nível que pega alguém reescrevendo o rótulo na camada de
apresentação em vez de chamar `publication.py`.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import publication
from apps.core.models import Finding, User
from apps.core.tests.factories import (
    AccountFactory,
    EvidenceFactory,
    FindingFactory,
    ImprovementOpportunityFactory,
    PainPointFactory,
    ProcessFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def autor() -> User:
    return UserFactory(role=User.Role.ADMIN)


@pytest.fixture
def api(autor: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(autor)
    return client


def _publica(obj, autor: User):  # type: ignore[no-untyped-def]
    """O mesmo helper de `test_a_cadeia_de_publicacao_nao_vaza.py`: carimba direto, sem passar
    pela action — os testes daqui montam estados que a action recusaria de propósito (ex.: uma
    dor publicada sem achado publicado embaixo, para testar `estado_de_publicacao` num objeto já
    publicado e depois preso)."""
    obj.published_at = timezone.now()
    obj.published_by = autor
    obj.save(update_fields=["published_at", "published_by", "updated_at"])
    return obj


# --- Os quatro estados que o DAP desenha --------------------------------------------


def test_publicado_e_solto(autor: User) -> None:
    achado = _publica(FindingFactory(account=AccountFactory()), autor)

    estado = publication.estado_de_publicacao(achado)

    assert estado == {
        "state": "published",
        "missing": [],
        "missing_phrase": "",
        "blocked_by": 0,
        "blocked_phrase": "",
    }


def test_publicado_e_preso(autor: User) -> None:
    conta = AccountFactory()
    evidencia = _publica(EvidenceFactory(account=conta), autor)
    fato = FindingFactory(
        account=conta, epistemic_status=Finding.EpistemicStatus.FACT, reviewed_by=autor
    )
    fato.evidences.add(evidencia)
    _publica(fato, autor)
    dor = PainPointFactory(account=conta)
    dor.findings.add(fato)
    _publica(dor, autor)

    estado = publication.estado_de_publicacao(fato)

    presos = publication.dependentes_publicados_de(fato)
    assert estado["state"] == "published"
    assert estado["missing"] == []
    assert estado["missing_phrase"] == ""
    assert estado["blocked_by"] == 1 == len(presos)
    assert estado["blocked_phrase"] == publication.frase_do_impedimento(fato, presos)
    assert estado["blocked_phrase"] != ""


def test_nao_publicado_e_pronto() -> None:
    # Hipótese: não exige evidência publicada, e não cita processo — nada falta.
    achado = FindingFactory(account=AccountFactory())

    estado = publication.estado_de_publicacao(achado)

    assert estado == {
        "state": "ready",
        "missing": [],
        "missing_phrase": "",
        "blocked_by": 0,
        "blocked_phrase": "",
    }


def test_nao_publicado_e_bloqueado(autor: User) -> None:
    conta = AccountFactory()
    fato = FindingFactory(
        account=conta, epistemic_status=Finding.EpistemicStatus.FACT, reviewed_by=autor
    )
    fato.evidences.add(EvidenceFactory(account=conta))  # interna, nunca publicada

    estado = publication.estado_de_publicacao(fato)

    assert estado["state"] == "blocked"
    assert estado["missing"] == [publication.REQUISITO_EVIDENCIA]
    assert estado["missing_phrase"] == publication.frase_do_que_falta(
        [publication.REQUISITO_EVIDENCIA]
    )
    assert estado["missing_phrase"] != ""
    assert estado["blocked_by"] == 0
    assert estado["blocked_phrase"] == ""


# --- A frase é sempre a de publication.py, inclusive vista pela API ------------------


def test_a_frase_do_serializer_bate_com_a_de_publication_py_lado_bloqueado(
    api: APIClient, autor: User
) -> None:
    conta = AccountFactory()
    fato = FindingFactory(
        account=conta, epistemic_status=Finding.EpistemicStatus.FACT, reviewed_by=autor
    )
    fato.evidences.add(EvidenceFactory(account=conta))

    resposta = api.get(reverse("finding-detail", args=[fato.pk]))

    assert resposta.status_code == 200, resposta.data
    faltas = publication.o_que_falta_para_publicar(fato)
    assert resposta.data["publication_state"]["missing"] == faltas
    assert resposta.data["publication_state"]["missing_phrase"] == publication.frase_do_que_falta(
        faltas
    )


def test_a_frase_do_serializer_bate_com_a_de_publication_py_lado_preso(
    api: APIClient, autor: User
) -> None:
    conta = AccountFactory()
    evidencia = _publica(EvidenceFactory(account=conta), autor)
    fato = FindingFactory(
        account=conta, epistemic_status=Finding.EpistemicStatus.FACT, reviewed_by=autor
    )
    fato.evidences.add(evidencia)
    _publica(fato, autor)
    dor = PainPointFactory(account=conta)
    dor.findings.add(fato)
    _publica(dor, autor)

    resposta = api.get(reverse("finding-detail", args=[fato.pk]))

    assert resposta.status_code == 200, resposta.data
    presos = publication.dependentes_publicados_de(fato)
    assert resposta.data["publication_state"]["blocked_by"] == len(presos)
    assert resposta.data["publication_state"][
        "blocked_phrase"
    ] == publication.frase_do_impedimento(fato, presos)


# --- ImprovementOpportunity é o topo da escada: nunca prende nada -------------------


def test_improvement_opportunity_e_o_topo_e_nunca_prende(autor: User) -> None:
    conta = AccountFactory()
    dor = _publica(PainPointFactory(account=conta), autor)
    oportunidade = ImprovementOpportunityFactory(account=conta)
    oportunidade.pain_points.add(dor)
    _publica(oportunidade, autor)

    estado = publication.estado_de_publicacao(oportunidade)

    assert estado["state"] == "published"
    assert estado["blocked_by"] == 0
    assert estado["blocked_phrase"] == ""
    assert publication.dependentes_publicados_de(oportunidade) == []


def test_improvement_opportunity_nao_publicada_tambem_nunca_prende() -> None:
    oportunidade = ImprovementOpportunityFactory(account=AccountFactory())

    estado = publication.estado_de_publicacao(oportunidade)

    assert estado["blocked_by"] == 0
    assert estado["blocked_phrase"] == ""


# --- Os cinco recursos emitem o campo, e ele é read-only -----------------------------

# (basename, factory, campo extra exigido pela fábrica para o objeto existir sozinho)
RECURSOS = [
    ("processo", ProcessFactory),
    ("evidence", EvidenceFactory),
    ("finding", FindingFactory),
    ("painpoint", PainPointFactory),
    ("improvementopportunity", ImprovementOpportunityFactory),
]


@pytest.mark.parametrize(("basename", "fabrica"), RECURSOS)
def test_publication_state_sai_na_listagem_e_no_detalhe(
    api: APIClient, basename: str, fabrica
) -> None:
    objeto = fabrica(account=AccountFactory())

    detalhe = api.get(reverse(f"{basename}-detail", args=[objeto.pk]))
    listagem = api.get(reverse(f"{basename}-list"))

    assert detalhe.status_code == 200, detalhe.data
    assert "publication_state" in detalhe.data
    # Recém-criado e não publicado: "ready" ou "blocked" conforme a sustentação que a fábrica dá
    # por padrão (`PainPoint`/`ImprovementOpportunity` nascem sem achado/dor vivos por baixo,
    # FDD 048) — nunca "published", que é o único ramo que este teste exclui.
    assert detalhe.data["publication_state"]["state"] in ("ready", "blocked")

    assert listagem.status_code == 200, listagem.data
    linha = next(item for item in listagem.data if item["id"] == objeto.pk)
    assert "publication_state" in linha
    assert linha["publication_state"] == detalhe.data["publication_state"]


@pytest.mark.parametrize(("basename", "fabrica"), RECURSOS)
def test_publication_state_e_read_only(api: APIClient, basename: str, fabrica) -> None:
    objeto = fabrica(account=AccountFactory())

    resposta = api.patch(
        reverse(f"{basename}-detail", args=[objeto.pk]),
        {"publication_state": {"state": "published", "missing": [], "missing_phrase": "",
                                "blocked_by": 0, "blocked_phrase": ""}},
        format="json",
    )

    # Campo read-only: o DRF o descarta na entrada, sem 400 de campo desconhecido — o mesmo
    # comportamento já afirmado para `published_at`/`published_by` em
    # `test_a_marca_nao_e_escrita_por_patch` (tests/regression/test_a_cadeia_de_publicacao_nao_vaza.py).
    assert resposta.status_code == 200, resposta.data
    objeto.refresh_from_db()
    assert objeto.published_at is None


# --- Custo de consulta: medido e relatado, sem otimização nesta fatia ----------------


@pytest.mark.parametrize(("basename", "fabrica"), RECURSOS)
def test_custo_de_consulta_da_listagem_e_medido(
    api: APIClient, basename: str, fabrica
) -> None:
    """Não é gate de performance: mede o incremento de queries por item na listagem e reporta.

    O spec da tarefa pede a medida, não a otimização — `CaptureQueriesContext` com uma base de 1
    e de 4 itens, e a diferença dividida por 3 dá o custo marginal por item, sem depender do
    número fixo de queries de setup da própria requisição (auth, CSRF-adjacent, permissão).
    """
    conta = AccountFactory()
    fabrica(account=conta)
    with CaptureQueriesContext(connection) as com_um:
        resposta_um = api.get(reverse(f"{basename}-list"))
    assert resposta_um.status_code == 200, resposta_um.data

    for _ in range(3):
        fabrica(account=conta)
    with CaptureQueriesContext(connection) as com_quatro:
        resposta_quatro = api.get(reverse(f"{basename}-list"))
    assert resposta_quatro.status_code == 200, resposta_quatro.data

    incremento = len(com_quatro.captured_queries) - len(com_um.captured_queries)
    por_item = incremento / 3
    print(f"\n[custo de consulta] {basename}: 1 item={len(com_um.captured_queries)} queries, "
          f"4 itens={len(com_quatro.captured_queries)} queries, incremento/item={por_item}")
    # Sem asserção de limite — é medida, não otimização (fora de escopo desta fatia). O número é
    # reportado no BUILD REPORT via saída do teste (`pytest -q` mostra falha se explodir; sucesso
    # aqui só confirma que a rota não caiu, o custo real está no relatório).
    assert por_item >= 0
