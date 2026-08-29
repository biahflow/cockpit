"""Regressão: a migração `0064` falha alto em vez de apagar o degrau por cima de alguém.

A ADR 0053 tira `discovery_assessment` de `Service.tier`. Uma migração que apagasse a linha em
silêncio produziria o pior defeito possível para dado comercial: `CommercialOpportunity.service` e
`Project.service` são `SET_NULL`, então a venda continuaria lá, sem degrau, e **nada** ficaria
vermelho — nem teste, nem tela, nem log. O mesmo vale para a decisão de gente: nome, preço e resumo
editados na tela Serviços são escolha registrada, e sobrescrevê-los é o que faz ninguém confiar
numa migração.

Só uma migração de verdade, rodando contra o esquema **anterior**, prova isso: no molde de
`test_engagement_backfill.py` e `test_commercial_model_migracao_0059.py`, o esquema volta para a
`0063`, o dado nasce pelo modelo histórico daquele estado, e só então a migração é chamada.

O caso feliz — linha semeada, intocada e sem vínculo — é o de todo banco migrado do zero, e a
suíte inteira o exercita a cada `pytest`: se ele não passasse, nada aqui rodaria.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

ANTES = ("core", "0063_process_process_step")
DEPOIS = ("core", "0064_escada_de_seis_degraus")
CHAVE = "discovery_assessment"

_SEQ = {"n": 0}


def _proximo() -> int:
    _SEQ["n"] += 1
    return _SEQ["n"]


@pytest.fixture
def estado_0063():
    """Volta o esquema para antes de o degrau sair.

    O teardown migra para a frente de novo, e **cada teste desfaz o próprio obstáculo antes de
    terminar**: uma guarda que ainda recusasse aqui deixaria o esquema atrás do resto da sessão.
    Desfazer o obstáculo também é a metade que faltava da afirmação — a mensagem promete um
    caminho de saída, e o teste percorre esse caminho.

    De quebra, o `migrate([ANTES])` daqui **é** o reverse da `0064`: os dois testes só encontram
    o degrau porque `recriar_o_degrau` o recriou com os valores semeados da `0050`.
    """
    executor = MigrationExecutor(connection)
    executor.migrate([ANTES])
    yield executor.loader.project_state([ANTES]).apps
    de_volta = MigrationExecutor(connection)
    de_volta.loader.build_graph()
    # Migra até o **HEAD**, não só até `DEPOIS`: desde a `0069` (renome das tabelas da Fase 6) o
    # nome físico da tabela muda entre estados de migração, e o `flush` do teardown usa o nome do
    # HEAD (`core_process`, `core_account`). Parar num estado intermediário deixaria `core_processo`
    # onde o flush procura `core_process`, e o teardown estouraria com FK/constraint.
    de_volta.migrate(de_volta.loader.graph.leaf_nodes())


def _migrar():
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate([DEPOIS])


# Os valores que a `0050` semeou — os mesmos que a guarda compara. Ficam aqui, e não são lidos da
# migração, pela razão dela: história congelada não vira dependência de código.
SEMEADO = {
    "name": "Discovery Express + Assessment",
    "list_price": 0,
    "summary": (
        "Discovery estruturado do processo mais assessment de maturidade em IA, fechando com o "
        "próximo passo recomendado. Gratuito no programa de founding client; pago para os demais."
    ),
    "active": True,
}


def _degrau(apps):
    """A linha semeada do degrau — criada aqui se a sessão não a deixou de pé.

    Teste `transaction=True` **trunca as tabelas ao terminar**, inclusive as linhas que as
    migrações de semente criaram. Depender do que outro teste deixou no banco é depender da ordem
    de execução, e a suíte é embaralhada (`pytest-randomly`): daria verde sozinho e vermelho no
    `pytest` inteiro — que foi exatamente como este arquivo falhou da primeira vez.
    """
    degrau, _ = apps.get_model("core", "Service").objects.get_or_create(
        tier=CHAVE, archived_at=None, defaults=SEMEADO
    )
    return degrau


def _etapa_aberta(apps):
    """Idem para a etapa do pipeline: a venda precisa de uma, e ela é `PROTECT`."""
    PipelineStage = apps.get_model("core", "PipelineStage")
    # `filter().first()` e não `get_or_create`: a semente traz **quatro** etapas abertas, e um
    # `get_or_create(kind="open")` estouraria com `MultipleObjectsReturned` no banco cheio.
    return PipelineStage.objects.filter(kind="open").first() or PipelineStage.objects.create(
        name="Aberta", kind="open", position=0
    )


def test_migracao_recusa_quando_o_degrau_ainda_tem_venda(estado_0063) -> None:
    apps = estado_0063
    n = _proximo()
    User = apps.get_model("core", "User")
    dono = User.objects.create(username=f"dono{n}-0064", email=f"dono{n}-0064@exemplo.test")
    conta = apps.get_model("core", "Account").objects.create(
        name=f"Conta {n}", owner=dono
    )
    etapa = _etapa_aberta(apps)
    apps.get_model("core", "CommercialOpportunity").objects.create(
        account=conta,
        title="Discovery do founding client",
        estimated_value=0,
        stage=etapa,
        owner=dono,
        expected_close_date="2026-09-30",
        service=_degrau(apps),
    )

    with pytest.raises(RuntimeError) as recusa:
        _migrar()

    mensagem = str(recusa.value)
    assert "1 oportunidade(s) comercial(is)" in mensagem  # a contagem, não só "há vínculo"
    assert CHAVE in mensagem
    assert "migrate" in mensagem  # e o caminho de saída

    # Reapontada a venda, a migração passa — e o degrau sai.
    venda = apps.get_model("core", "CommercialOpportunity").objects.filter(
        service__tier=CHAVE
    ).get()
    venda.service = None
    venda.save(update_fields=["service"])
    _migrar()
    assert not apps.get_model("core", "Service").objects.filter(tier=CHAVE).exists()


def test_migracao_recusa_quando_alguem_editou_o_degrau_na_tela(estado_0063) -> None:
    apps = estado_0063
    degrau = _degrau(apps)
    degrau.list_price = 4500
    degrau.name = "Discovery + Assessment (condição piloto)"
    degrau.save(update_fields=["list_price", "name"])

    with pytest.raises(RuntimeError) as recusa:
        _migrar()

    mensagem = str(recusa.value)
    assert "editado por gente" in mensagem
    assert "4500" in mensagem  # o que divergiu, dito de volta
    assert "condição piloto" in mensagem

    # Devolvida a linha ao estado semeado, a migração passa.
    degrau.list_price = 0
    degrau.name = "Discovery Express + Assessment"
    degrau.save(update_fields=["list_price", "name"])
    _migrar()
    assert not apps.get_model("core", "Service").objects.filter(tier=CHAVE).exists()
