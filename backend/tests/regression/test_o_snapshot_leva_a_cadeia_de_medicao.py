"""Regressão: `kpis[]` e `value_ledger[]` atravessam para o portal do cliente (FDD 050).

`KPI`, `Measurement` e `ValueLedgerEntry` existem desde a Fase 5 da ontologia (ADR 0055, FDD 049) e
**nenhum atravessava**: a FDD 049 adiou o One de propósito, e o que o cliente via no lugar eram os
quatro campos legados de `DigitalEmployee` e um `roi` que é receita menos custo do projeto. Ele
tinha o dinheiro do contrato e nenhum indicador do trabalho que contratou.

O que este arquivo guarda não é a existência das duas chaves — disso já cuidam as duas guardas do
snapshot. É o conjunto de regras que fazem a projeção ser honesta, e cada uma delas falha em
silêncio se for desfeita:

* **Outcome sem baseline não é emitido.** O critério do outro lado é "todo Outcome renderizado tem
  Baseline no mesmo componente" (`language-map` §6.11). Emitir e deixar o One recusar faz o cliente
  ver lacuna onde há dado.
* **As duas nulidades.** `"baseline": null` é *não há baseline*; `{"value": null, …}` é *a janela
  existe e a medição não foi feita*. Nenhuma das duas é `0` — zero é zero medido.
* **Só `approved` com método de atribuição atravessa.** É a linha que o cliente lê como *valor
  gerado*; sem o método, o que sobra é uma promessa com casas decimais.
* **`kpi_ids` é aditivo.** Os quatro campos legados ficam onde estão até o One parar de lê-los, na
  mesma convivência de `account`/`client`.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core import portal
from apps.core.models import KPI, DigitalEmployee, Measurement, User, ValueLedgerEntry
from apps.core.tests.factories import (
    EngagementFactory,
    KPIFactory,
    MeasurementFactory,
    ProjectFactory,
    UserFactory,
    ValueLedgerEntryFactory,
)

pytestmark = pytest.mark.django_db


def _medicao(kpi: KPI, kind: str, **campos) -> Measurement:  # type: ignore[no-untyped-def]
    """Uma leitura viva do KPI. Sem `value` de propósito quando quem chama omite: é a lacuna."""
    campos.setdefault("period_start", date(2026, 3, 1))
    campos.setdefault("period_end", date(2026, 3, 31))
    campos.setdefault("measured_at", timezone.now())
    return Measurement.objects.create(kpi=kpi, kind=kind, **campos)


def _entrada_aprovada(engagement, **campos) -> ValueLedgerEntry:  # type: ignore[no-untyped-def]
    """Uma entrada de Value Ledger aprovada — o único estado que atravessa."""
    campos.setdefault("approved_by", UserFactory(role=User.Role.ADMIN))
    return ValueLedgerEntryFactory(
        engagement=engagement, status=ValueLedgerEntry.Status.APPROVED, **campos
    )


# --- O KPI e as leituras dele -------------------------------------------------


def test_o_kpi_vivo_do_projeto_atravessa_com_a_definicao_inteira() -> None:
    """Unidade e método vão junto: é o que torna duas leituras do mesmo indicador comparáveis."""
    projeto = ProjectFactory()
    KPIFactory(
        project=projeto,
        name="Tempo de resposta",
        definition="Minutos entre o pedido e a primeira resposta.",
        formula="média(resposta - pedido)",
        unit="hours",
        direction="down",
        data_source="Planilha do atendimento",
        cadence="Mensal",
        target=Decimal("20.00"),
    )

    linha = portal.build_snapshot(projeto)["kpis"][0]

    assert linha["name"] == "Tempo de resposta"
    assert linha["definition"] == "Minutos entre o pedido e a primeira resposta."
    assert linha["formula"] == "média(resposta - pedido)"
    assert linha["unit"] == "hours"
    assert linha["direction"] == "down"
    assert linha["data_source"] == "Planilha do atendimento"
    assert linha["cadence"] == "Mensal"
    assert linha["target"] == 20.0


def test_baseline_e_outcome_saem_aninhados_dentro_do_kpi() -> None:
    """O aninhamento é a decisão da fatia: o pareamento vira invariante por construção.

    Numa lista irmã de medições, casar baseline com outcome seria trabalho do leitor — e um
    pareamento errado (unidade diferente, método diferente) não deixaria nada vermelho.
    """
    projeto = ProjectFactory()
    kpi = KPIFactory(project=projeto)
    agora = timezone.now()
    _medicao(
        kpi, Measurement.Kind.BASELINE, value=Decimal("72.00"), measured_at=agora, confidence=80
    )
    depois = agora + timedelta(days=90)
    _medicao(
        kpi,
        Measurement.Kind.OUTCOME,
        value=Decimal("18.50"),
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
        measured_at=depois,
        confidence=95,
    )
    _medicao(kpi, Measurement.Kind.MONITORING, value=Decimal("30.00"), measured_at=depois)

    linha = portal.build_snapshot(projeto)["kpis"][0]

    assert linha["baseline"] == {
        "value": 72.0,
        "period_start": "2026-03-01",
        "period_end": "2026-03-31",
        "measured_at": agora.isoformat(),
        "confidence": 80,
    }
    assert linha["outcome"] == {
        "value": 18.5,
        "period_start": "2026-07-01",
        "period_end": "2026-07-31",
        "measured_at": depois.isoformat(),
        "confidence": 95,
    }
    assert [medicao["value"] for medicao in linha["monitoring"]] == [30.0]


def test_o_monitoramento_e_lista_vazia_e_nunca_nula() -> None:
    """Ausência de leitura de monitoramento é lista vazia — o consumidor itera sem checar nulo."""
    projeto = ProjectFactory()
    KPIFactory(project=projeto)

    assert portal.build_snapshot(projeto)["kpis"][0]["monitoring"] == []


def test_outcome_sem_baseline_nao_atravessa() -> None:
    """Sem o "antes", o "depois" não é resultado — é um número solto (`language-map` §6.11).

    O One recusaria o par incompleto, e o cliente veria lacuna onde há dado. Quem sabe que falta a
    baseline é quem a consulta: aqui.
    """
    projeto = ProjectFactory()
    kpi = KPIFactory(project=projeto)
    _medicao(kpi, Measurement.Kind.OUTCOME, value=Decimal("18.50"))

    linha = portal.build_snapshot(projeto)["kpis"][0]

    assert Measurement.objects.filter(kpi=kpi, kind=Measurement.Kind.OUTCOME).exists()
    assert linha["baseline"] is None
    assert linha["outcome"] is None


def test_as_duas_nulidades_da_baseline_nunca_viram_zero() -> None:
    """`null` é "não há baseline"; `{"value": null}` é "a janela existe e não se mediu".

    Colapsar qualquer uma das duas em `0` afirmaria que o processo não custava nada antes — a
    lacuna disfarçada de medição que `Measurement.value` guarda sendo nulável.
    """
    projeto = ProjectFactory()
    sem_nenhuma = KPIFactory(project=projeto, name="A — sem medição")
    sem_valor = KPIFactory(project=projeto, name="B — janela sem valor")
    _medicao(sem_valor, Measurement.Kind.BASELINE)  # sem `value`: é a lacuna

    por_nome = {linha["name"]: linha for linha in portal.build_snapshot(projeto)["kpis"]}

    assert por_nome[sem_nenhuma.name]["baseline"] is None
    assert por_nome[sem_nenhuma.name]["baseline"] != 0

    janela = por_nome[sem_valor.name]["baseline"]
    assert janela is not None
    assert janela["value"] is None
    assert janela["value"] != 0
    assert janela["period_start"] == "2026-03-01"


def test_kpi_arquivado_e_medicao_arquivada_saem_do_snapshot() -> None:
    """Arquivado para de contar em todo nível, como todo filho do snapshot (FDD 025)."""
    projeto = ProjectFactory()
    arquivado = KPIFactory(project=projeto, name="Arquivado")
    arquivado.archive()
    vivo = KPIFactory(project=projeto, name="Vivo")
    baseline = _medicao(vivo, Measurement.Kind.BASELINE, value=Decimal("72.00"))
    baseline.archive()

    kpis = portal.build_snapshot(projeto)["kpis"]

    assert [linha["name"] for linha in kpis] == ["Vivo"]
    assert kpis[0]["baseline"] is None


def test_o_kpi_nao_leva_dono_nem_a_medicao_leva_evidencia() -> None:
    """Pessoa interna e evidência bruta não atravessam a fronteira do cliente (§3).

    A asserção é sobre as **chaves** do dicionário e não sobre o valor: uma chave presente com
    `None` continuaria sendo o campo atravessando, e o dia em que ela ganhasse conteúdo ninguém
    ficaria sabendo.
    """
    projeto = ProjectFactory()
    kpi = KPIFactory(project=projeto, owner=UserFactory())
    _medicao(kpi, Measurement.Kind.BASELINE, value=Decimal("72.00"))
    _medicao(kpi, Measurement.Kind.OUTCOME, value=Decimal("18.50"))

    linha = portal.build_snapshot(projeto)["kpis"][0]

    assert "owner" not in linha
    assert "owner_id" not in linha
    assert "prove_experiment" not in linha
    for medicao in (linha["baseline"], linha["outcome"]):
        assert "source_evidence" not in medicao
        # O aninhamento **é** a identidade e o papel da leitura: ela é *a* baseline daquele KPI.
        assert "id" not in medicao
        assert "kind" not in medicao


# --- O Value Ledger -----------------------------------------------------------


def test_o_ledger_leva_so_a_entrada_aprovada() -> None:
    """Rascunho e pendente são deliberação interna — regra 1 da §3, e aqui ela pesa dobrado."""
    projeto = ProjectFactory()
    engagement = projeto.engagement
    ValueLedgerEntryFactory(engagement=engagement, status=ValueLedgerEntry.Status.DRAFT)
    ValueLedgerEntryFactory(engagement=engagement, status=ValueLedgerEntry.Status.PENDING)
    aprovada = _entrada_aprovada(engagement, amount=Decimal("48000.00"))

    ledger = portal.build_snapshot(projeto)["value_ledger"]

    assert [entrada["id"] for entrada in ledger] == [aprovada.pk]
    assert ledger[0]["amount"] == 48000.0
    assert ledger[0]["value_type"] == ValueLedgerEntry.ValueType.COST_SAVING
    assert ledger[0]["kpi_id"] == aprovada.outcome_measurement.kpi_id
    assert (
        ledger[0]["outcome_measured_at"] == aprovada.outcome_measurement.measured_at.isoformat()
    )


def test_entrada_sem_metodo_de_atribuicao_nao_atravessa() -> None:
    """O `clean()` já exige o método — e não roda em shell nem em migração de dados.

    É o campo cuja ausência transforma a linha num número sem procedência, e o snapshot é o último
    ponto antes do cliente. Por isso a regra é verificada aqui também, e não só no modelo.
    """
    projeto = ProjectFactory()
    engagement = projeto.engagement
    sem_metodo = ValueLedgerEntry.objects.create(
        engagement=engagement,
        outcome_measurement=MeasurementFactory(kind=Measurement.Kind.OUTCOME),
        value_type=ValueLedgerEntry.ValueType.REVENUE,
        amount=Decimal("10000.00"),
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
        attribution_method="   ",
        status=ValueLedgerEntry.Status.APPROVED,
        approved_by=UserFactory(role=User.Role.ADMIN),
    )
    com_metodo = _entrada_aprovada(engagement)

    ledger = portal.build_snapshot(projeto)["value_ledger"]

    assert sem_metodo.pk not in [entrada["id"] for entrada in ledger]
    assert [entrada["id"] for entrada in ledger] == [com_metodo.pk]


def test_a_entrada_do_mandato_sai_no_snapshot_de_todos_os_projetos_dele() -> None:
    """Valor é do mandato, não do projeto: `ValueLedgerEntry.project` é opcional de propósito.

    Um resultado que atravessa dois projetos do mesmo programa é uma entrada só, e ela aparece nos
    dois. É a mesma leitura por `Engagement` da tela `/contas/:id/valor`.
    """
    engagement = EngagementFactory()
    um = ProjectFactory(engagement=engagement)
    outro = ProjectFactory(engagement=engagement)
    de_fora = ProjectFactory()
    entrada = _entrada_aprovada(engagement)

    assert [linha["id"] for linha in portal.build_snapshot(um)["value_ledger"]] == [entrada.pk]
    assert [linha["id"] for linha in portal.build_snapshot(outro)["value_ledger"]] == [entrada.pk]
    assert portal.build_snapshot(de_fora)["value_ledger"] == []


def test_entrada_arquivada_sai_do_ledger() -> None:
    projeto = ProjectFactory()
    arquivada = _entrada_aprovada(projeto.engagement)
    arquivada.archive()

    assert portal.build_snapshot(projeto)["value_ledger"] == []


def test_o_ledger_nao_leva_quem_aprovou_nem_o_estado_da_aprovacao() -> None:
    """`approved_by` é pessoa interna; `status` contaria ao cliente sobre uma fila que não é dele.

    Sobre as chaves, e não sobre o valor, pelo motivo do teste gêmeo do KPI.
    """
    projeto = ProjectFactory()
    _entrada_aprovada(projeto.engagement)

    entrada = portal.build_snapshot(projeto)["value_ledger"][0]

    assert "approved_by" not in entrada
    assert "approved_by_id" not in entrada
    assert "approved_at" not in entrada
    assert "status" not in entrada
    assert entrada["attribution_method"]


# --- O ponteiro do ativo de solução, aditivo ----------------------------------


def test_o_funcionario_digital_ganha_kpi_ids_sem_perder_os_quatro_campos_legados() -> None:
    """Convivência, não substituição: o legado sai quando o One parar de ler, e não antes.

    Sem esta asserção, uma varredura atrás de campo morto tiraria os quatro achando que paga
    dívida — quebrando a tela do cliente no único lugar onde nada aqui dentro fica vermelho.
    """
    projeto = ProjectFactory()
    kpi = KPIFactory(project=projeto)
    DigitalEmployee.objects.create(
        project=projeto,
        name="Ana Financeiro",
        kpi=kpi,
        kpi_label="Notas processadas",
        kpi_value="312 notas/mês",
        hours_saved_month=Decimal("40.00"),
        roi_month=Decimal("8000.00"),
    )
    sem_kpi = DigitalEmployee.objects.create(project=projeto, name="Sem indicador")

    por_nome = {
        linha["name"]: linha for linha in portal.build_snapshot(projeto)["digital_employees"]
    }

    assert por_nome["Ana Financeiro"]["kpi_ids"] == [kpi.pk]
    assert por_nome["Ana Financeiro"]["kpi_label"] == "Notas processadas"
    assert por_nome["Ana Financeiro"]["kpi_value"] == "312 notas/mês"
    assert por_nome["Ana Financeiro"]["hours_saved_month"] == 40.0
    assert por_nome["Ana Financeiro"]["roi_month"] == 8000.0
    # Lista vazia e nunca `null`: o consumidor itera sem checar nulo.
    assert por_nome[sem_kpi.name]["kpi_ids"] == []


# --- Os emissores que as chaves novas exigem (ADR 0003) -----------------------


def test_salvar_kpi_e_medicao_avisa_o_portal(monkeypatch: pytest.MonkeyPatch) -> None:
    """A regra que abre a ADR 0003: o que entra no snapshot precisa de emissor.

    A medição pesa mais que o KPI aqui — registrar o Outcome do mês não salva `Project` nem `KPI`,
    então sem receiver próprio ela só chegaria ao cliente de carona no próximo salvamento de outra
    coisa. É o defeito do funcionário digital (emenda de 07/08/2026) por outro eixo.
    """
    projeto = ProjectFactory()
    chamadas: list[tuple] = []
    monkeypatch.setattr(portal, "emit", lambda *args: chamadas.append(args))

    kpi = KPIFactory(project=projeto)
    assert ("updated", "kpi", projeto.pk) in chamadas

    chamadas.clear()
    _medicao(kpi, Measurement.Kind.OUTCOME, value=Decimal("18.50"))
    assert ("updated", "measurement", projeto.pk) in chamadas

    # Arquivar é um `save()`, e arquivado o KPI sai do snapshot — a mudança mais silenciosa.
    chamadas.clear()
    kpi.archive()
    assert ("updated", "kpi", projeto.pk) in chamadas


def test_a_entrada_do_ledger_emite_para_todos_os_projetos_do_mandato(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fan-out no molde do `_emit_engagement`, porque a entrada aparece no snapshot de todos.

    É o contrário do `_emit_artifact`, que escolhe **um** projeto porque só um é afetado.
    """
    engagement = EngagementFactory()
    um = ProjectFactory(engagement=engagement)
    outro = ProjectFactory(engagement=engagement)
    de_fora = ProjectFactory()

    chamadas: list[tuple] = []
    monkeypatch.setattr(portal, "emit", lambda *args: chamadas.append(args))
    _entrada_aprovada(engagement)

    assert ("updated", "value_ledger_entry", um.pk) in chamadas
    assert ("updated", "value_ledger_entry", outro.pk) in chamadas
    assert ("updated", "value_ledger_entry", de_fora.pk) not in chamadas
