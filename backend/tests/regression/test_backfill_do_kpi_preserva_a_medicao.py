"""Regressão: o backfill move a medição para `Measurement` sem inventar nada (migração 0067).

A decisão **C1** (ADR 0055) tira `DigitalEmployee.kpi_baseline`/`kpi_current` do modelo. Se a
`0067` deixar um único número para trás, ele vai embora com a coluna — e o que ele guardava é
justamente o "antes" que a FDD 027 existiu para capturar no instante certo. Não há sintoma: o
`ALTER TABLE` passa, a tela mostra `—`, e ninguém sabe que havia número ali.

O outro alvo é o oposto, e é o que a migração pode **mentir**: nulo não vira zero, e nulo não vira
medição. Um ativo sem baseline tem de sair do backfill **sem** `Measurement(kind=baseline)`
nenhuma. Uma linha com valor zero afirmaria que o processo não custava nada antes.

## Por que este arquivo rola o esquema para trás

Pelo motivo de `test_engagement_backfill.py`: o estado pré-migração é "ativo **com as duas
colunas**", e no HEAD elas não existem — um `DigitalEmployee(kpi_baseline=…)` levanta `TypeError`
antes de o teste começar. Então o esquema volta de verdade para a `0066`, os dados nascem pelos
modelos **daquele** estado, e o esquema volta para o HEAD no fim. É o que torna o teste uma medição
do que a migração faz, e não do que o modelo de hoje permite.

`transaction=True` é consequência disso, não escolha: o SQLite recusa DDL dentro de uma transação.
"""

import importlib
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = pytest.mark.django_db(transaction=True)

MIGRACAO = "apps.core.migrations.0067_backfill_kpi_measurement"
ANTES = ("core", "0066_prove_e_valor")
DEPOIS = ("core", "0067_backfill_kpi_measurement")


@pytest.fixture
def estado_0066():
    """Volta o esquema para a 0066 e devolve os modelos **daquele** estado.

    É exatamente o `from_state.apps` que o Django entrega ao `RunPython` da 0067.
    """
    executor = MigrationExecutor(connection)
    executor.migrate([ANTES])
    yield executor.loader.project_state([ANTES]).apps
    de_volta = MigrationExecutor(connection)
    de_volta.loader.build_graph()
    # Migra até o **HEAD**, não só até `DEPOIS`: a partir da `0069` (renome das tabelas da Fase 6)
    # o nome físico das tabelas muda entre estados de migração, e o `flush` do teardown usa o nome
    # do HEAD. Parar num estado intermediário deixa a tabela com o nome antigo e o flush estoura.
    de_volta.migrate(de_volta.loader.graph.leaf_nodes())


def _rodar_backfill(apps) -> None:
    """Importa a migração pelo nome de módulo (o número no início impede o `import` normal)."""
    importlib.import_module(MIGRACAO).backfill_kpi(apps, None)


def _reverter_backfill(apps) -> None:
    importlib.import_module(MIGRACAO).desfaz_backfill(apps, None)


# --------------------------------------------------------------------- fábricas históricas

_SEQ = {"n": 0}


def _proximo() -> int:
    _SEQ["n"] += 1
    return _SEQ["n"]


def _projeto(apps):
    n = _proximo()
    User = apps.get_model("core", "User")
    dono = User.objects.create(username=f"dono{n}", email=f"dono{n}@exemplo.test")
    conta = apps.get_model("core", "Account").objects.create(
        name=f"Conta {n}", owner=dono, lifecycle_status="active"
    )
    engagement = apps.get_model("core", "Engagement").objects.create(
        account=conta, name=f"Engajamento {n}", owner=dono
    )
    inicio = timezone.localdate()
    return apps.get_model("core", "Project").objects.create(
        client=conta, engagement=engagement, name=f"Projeto {n}", owner=dono,
        start_date=inicio, due_date=inicio + timedelta(days=30),
    )


def _ativo(apps, projeto, *, baseline=None, atual=None, **campos):
    padrao = {
        "name": f"SDR {_proximo()}",
        "kpi_label": "Leads qualificados/mês",
        "kpi_unit": "count",
        "kpi_direction": "up",
    }
    return apps.get_model("core", "DigitalEmployee").objects.create(
        project=projeto, kpi_baseline=baseline, kpi_current=atual, **{**padrao, **campos}
    )


def _kpis(apps):
    return apps.get_model("core", "KPI").objects


def _medicoes(apps):
    return apps.get_model("core", "Measurement").objects


# ------------------------------------------------------------------------------- testes


def test_o_ativo_com_os_dois_numeros_sai_com_as_duas_medicoes(estado_0066) -> None:
    apps = estado_0066
    projeto = _projeto(apps)
    ativo = _ativo(apps, projeto, baseline=Decimal("12.00"), atual=Decimal("48.00"))

    _rodar_backfill(apps)

    ativo.refresh_from_db()
    kpi = _kpis(apps).get(pk=ativo.kpi_id)
    assert kpi.project_id == projeto.pk
    assert kpi.name == "Leads qualificados/mês"
    assert kpi.unit == "count"
    assert kpi.direction == "up"
    # **Nunca inventado**: o KPI migrado não nasceu de experimento nenhum, e dizer o contrário
    # seria dado fabricado com aparência de histórico.
    assert kpi.prove_experiment_id is None
    medicoes = {m.kind: m.value for m in _medicoes(apps).filter(kpi=kpi)}
    assert medicoes == {"baseline": Decimal("12.00"), "outcome": Decimal("48.00")}


def test_o_ativo_so_com_baseline_nao_ganha_outcome(estado_0066) -> None:
    apps = estado_0066
    ativo = _ativo(apps, _projeto(apps), baseline=Decimal("12.00"), atual=None)

    _rodar_backfill(apps)

    ativo.refresh_from_db()
    assert list(_medicoes(apps).filter(kpi_id=ativo.kpi_id).values_list("kind", flat=True)) == [
        "baseline"
    ]


def test_o_ativo_so_com_atual_nao_ganha_baseline_zerada(estado_0066) -> None:
    """O caso em que a migração poderia mentir **e ainda assim criar linha**, que é o pior dos dois.

    Um ativo medido só depois é a lacuna da FDD 027: ninguém apurou o "antes". Uma
    `Measurement(kind=baseline, value=0)` aqui afirmaria que o processo não custava nada, e a linha
    existiria — a tela mostraria `0 → 12` em vez de `— → 12`, e o case diria `has_baseline: true`.
    O teste do ativo sem número nenhum, logo abaixo, **não** pega isto: aquele ativo nem entra no
    laço do backfill.
    """
    apps = estado_0066
    ativo = _ativo(apps, _projeto(apps), baseline=None, atual=Decimal("12.00"))

    _rodar_backfill(apps)

    ativo.refresh_from_db()
    assert list(_medicoes(apps).filter(kpi_id=ativo.kpi_id).values_list("kind", flat=True)) == [
        "outcome"
    ]
    assert not _medicoes(apps).filter(kpi_id=ativo.kpi_id, kind="baseline").exists()


def test_o_ativo_sem_numero_nenhum_nao_ganha_kpi_nem_medicao(estado_0066) -> None:
    """O ponto exato em que a migração poderia mentir. Ele ganha a **ausência**, que é o que tem."""
    apps = estado_0066
    ativo = _ativo(apps, _projeto(apps), baseline=None, atual=None)

    _rodar_backfill(apps)

    ativo.refresh_from_db()
    assert ativo.kpi_id is None
    assert not _kpis(apps).exists()
    assert not _medicoes(apps).exists()


def test_zero_medido_atravessa_como_zero(estado_0066) -> None:
    """A metade complementar do teste acima: zero **é** medição, e não pode virar ausência."""
    apps = estado_0066
    ativo = _ativo(apps, _projeto(apps), baseline=Decimal("0.00"), atual=Decimal("5.00"))

    _rodar_backfill(apps)

    ativo.refresh_from_db()
    assert _medicoes(apps).get(kpi_id=ativo.kpi_id, kind="baseline").value == Decimal("0.00")


def test_o_kpi_sem_rotulo_ganha_um_nome_legivel(estado_0066) -> None:
    """KPI anônimo na tela é pior que um nome derivado — e a origem fica no `prove_experiment`."""
    apps = estado_0066
    ativo = _ativo(apps, _projeto(apps), baseline=Decimal("3.00"), kpi_label="", name="Cobrador")

    _rodar_backfill(apps)

    ativo.refresh_from_db()
    assert _kpis(apps).get(pk=ativo.kpi_id).name == "KPI — Cobrador"


def test_a_janela_da_medicao_aproxima_pelos_carimbos_do_ativo(estado_0066) -> None:
    """Aproximação declarada: o modelo antigo não registrava quando a medição foi tomada."""
    apps = estado_0066
    ativo = _ativo(apps, _projeto(apps), baseline=Decimal("12.00"), atual=Decimal("48.00"))

    _rodar_backfill(apps)

    ativo.refresh_from_db()
    baseline = _medicoes(apps).get(kpi_id=ativo.kpi_id, kind="baseline")
    outcome = _medicoes(apps).get(kpi_id=ativo.kpi_id, kind="outcome")
    assert baseline.measured_at == ativo.created_at
    assert outcome.measured_at == ativo.updated_at


def test_o_ativo_arquivado_vem_junto_com_o_carimbo_preservado(estado_0066) -> None:
    apps = estado_0066
    quando = timezone.now()
    ativo = _ativo(apps, _projeto(apps), baseline=Decimal("12.00"), archived_at=quando)

    _rodar_backfill(apps)

    ativo.refresh_from_db()
    assert _kpis(apps).get(pk=ativo.kpi_id).archived_at == quando
    assert _medicoes(apps).get(kpi_id=ativo.kpi_id).archived_at == quando


def test_o_backfill_e_idempotente(estado_0066) -> None:
    """Um deploy reexecutado depois de falhar no meio não pode duplicar KPI nem medição."""
    apps = estado_0066
    ativo = _ativo(apps, _projeto(apps), baseline=Decimal("12.00"), atual=Decimal("48.00"))

    _rodar_backfill(apps)
    _rodar_backfill(apps)

    ativo.refresh_from_db()
    assert _kpis(apps).count() == 1
    assert _medicoes(apps).filter(kpi_id=ativo.kpi_id).count() == 2


def test_o_backfill_nao_reescreve_o_updated_at_do_ativo(estado_0066) -> None:
    """Ele é a aproximação que a medição de "depois" acabou de usar; carimbá-lo apagaria a data."""
    apps = estado_0066
    ativo = _ativo(apps, _projeto(apps), atual=Decimal("48.00"))
    antes = ativo.updated_at

    _rodar_backfill(apps)

    ativo.refresh_from_db()
    assert ativo.updated_at == antes


def test_a_reversa_devolve_os_numeros_e_apaga_o_que_criou(estado_0066) -> None:
    apps = estado_0066
    ativo = _ativo(apps, _projeto(apps), baseline=Decimal("12.00"), atual=Decimal("48.00"))
    _rodar_backfill(apps)

    _reverter_backfill(apps)

    ativo.refresh_from_db()
    assert ativo.kpi_id is None
    assert ativo.kpi_baseline == Decimal("12.00")
    assert ativo.kpi_current == Decimal("48.00")
    assert not _kpis(apps).exists()
    assert not _medicoes(apps).exists()


def test_a_reversa_nao_toca_em_kpi_que_nenhum_ativo_aponta(estado_0066) -> None:
    """O recorte é pelo ponteiro, como a `0054` faz com `legacy_evidencia`."""
    apps = estado_0066
    projeto = _projeto(apps)
    escrito_a_mao = _kpis(apps).create(project=projeto, name="Escrito à mão", direction="up")
    ativo = _ativo(apps, projeto, baseline=Decimal("12.00"))
    _rodar_backfill(apps)

    _reverter_backfill(apps)

    ativo.refresh_from_db()
    assert _kpis(apps).filter(pk=escrito_a_mao.pk).exists()
    assert ativo.kpi_id is None


def test_a_reversa_nao_toca_em_kpi_de_experimento(estado_0066) -> None:
    """A outra metade da assinatura: um KPI que nasceu de um PROVE nunca veio deste backfill."""
    apps = estado_0066
    projeto = _projeto(apps)
    oportunidade = apps.get_model("core", "ImprovementOpportunity").objects.create(
        account_id=projeto.engagement.account_id, title="Automatizar a conferência"
    )
    hipotese = apps.get_model("core", "SolutionHypothesis").objects.create(
        improvement_opportunity=oportunidade, statement="Um leitor de nota fiscal resolve."
    )
    experimento = apps.get_model("core", "ProveExperiment").objects.create(
        project=projeto, solution_hypothesis=hipotese
    )
    kpi = _kpis(apps).create(
        project=projeto, prove_experiment=experimento, name="Tempo", direction="down"
    )
    ativo = _ativo(apps, projeto)
    ativo.kpi = kpi
    ativo.save(update_fields=["kpi"])

    _reverter_backfill(apps)

    ativo.refresh_from_db()
    assert ativo.kpi_id == kpi.pk
    assert _kpis(apps).filter(pk=kpi.pk).exists()
