"""A invariante de início do PROVE e a leitura de um KPI — as duas num lugar só (FDD 049).

O PROVE responde *"funcionou em produção controlada?"* (`docs/metodologia-fde.md`), e a resposta só
é uma resposta se o critério existir **antes**. Daí a invariante desta fatia: um experimento não
começa sem KPI, sem critério de sucesso e sem Baseline — ou com uma lacuna aprovada
explicitamente, que é um ato assinado e não um clique (decisão E1 do DAP
`docs/design/dap-prove-e-valor-r1/`).

`o_que_falta_para_iniciar` é o único lugar em que essa pergunta é feita. A action `start/` a usa
para recusar e a tela a usa para desenhar as três pastilhas `Pronto`/`Falta` — se cada uma
expressasse a regra por conta própria, a tela habilitaria o botão que o servidor recusa, e nada
ficaria vermelho. É o mesmo motivo de `priority.ranking_da_conta` e de `Project.objects.visible_to`
(ADR 0010).

**A função devolve chaves, não frases.** Rótulo é da superfície, e um servidor que devolvesse
"Baseline" em português congelaria a copy do board dentro do backend — o mesmo defeito que
`CLAUDE.md` proíbe em mapa de estado ("devolve variante, nunca a cor"). Os rótulos ficam em
`ROTULOS`, para a mensagem de erro da API ter texto legível sem a tela depender dele.

No fim do módulo, a outra metade da fatia: `baseline_de` e `outcome_mais_recente_de`, que é como
`DigitalEmployeeSerializer` e `cases._metric` continuam publicando `kpi_baseline`/`kpi_current`
depois de as colunas saírem (ADR 0055). Duas expressões de "qual é o antes deste ativo" divergiriam
na primeira correção.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import KPI, ProveExperiment

#: Os três requisitos da invariante, na ordem em que o board os desenha.
REQUISITO_KPI = "kpi"
REQUISITO_CRITERIO = "success_criteria"
REQUISITO_BASELINE = "baseline"

REQUISITOS: tuple[str, ...] = (REQUISITO_KPI, REQUISITO_CRITERIO, REQUISITO_BASELINE)

ROTULOS: dict[str, str] = {
    REQUISITO_KPI: "KPI",
    REQUISITO_CRITERIO: "critério de sucesso",
    REQUISITO_BASELINE: "baseline",
}


def kpis_vivos(experimento: ProveExperiment) -> list[KPI]:
    """Os KPIs não arquivados deste experimento.

    `.all()` e não `.filter()`, pela razão de `ImprovementOpportunity.current_assessment`: um
    `.filter()` emite consulta nova toda vez e **ignora** o `prefetch_related("kpis")` de quem
    chamou — custo de N+1 com aparência de custo resolvido.
    """
    return [kpi for kpi in experimento.kpis.all() if kpi.archived_at is None]


def tem_baseline_viva(kpi: KPI) -> bool:
    """Se este KPI já tem o "antes" registrado. Mesma leitura em Python, mesmo motivo."""
    return baseline_de(kpi) is not None


def o_que_falta_para_iniciar(experimento: ProveExperiment) -> list[str]:
    """As chaves dos requisitos que **faltam** para este PROVE começar. Lista vazia = pode começar.

    A baseline conta como faltando também quando não há KPI nenhum: sem indicador não existe "antes"
    a registrar, e dizer `baseline: Pronto` ali seria afirmar que a lacuna não existe porque não há
    onde ela caber.
    """
    faltas: list[str] = []
    kpis = kpis_vivos(experimento)
    if not kpis:
        faltas.append(REQUISITO_KPI)
    if not (experimento.success_criteria or "").strip():
        faltas.append(REQUISITO_CRITERIO)
    if not kpis or any(not tem_baseline_viva(kpi) for kpi in kpis):
        faltas.append(REQUISITO_BASELINE)
    return faltas


def frase_do_que_falta(faltas: list[str]) -> str:
    """Os rótulos do que falta, para a mensagem de 400. Ordem estável: a de `REQUISITOS`."""
    return ", ".join(ROTULOS[chave] for chave in REQUISITOS if chave in faltas)


# ------------------------------------------------------------------------------------------
# A leitura de um KPI — o que substitui `DigitalEmployee.kpi_baseline`/`kpi_current`
# ------------------------------------------------------------------------------------------


def _medicoes_vivas(kpi: KPI, kind: str) -> list:  # type: ignore[type-arg]
    from .models import Measurement

    return [
        medicao
        for medicao in kpi.measurements.all()
        if medicao.archived_at is None and medicao.kind == Measurement.Kind(kind)
    ]


def baseline_de(kpi: KPI | None) -> Decimal | None:
    """O valor da baseline viva deste KPI, ou `None`.

    **`None` é "não medido", nunca zero** — a distinção que `DigitalEmployee.kpi_baseline` guardava
    sendo nulável e que o `Case` publica como `has_baseline: false` em vez de `0`. A constraint
    parcial garante que existe no máximo uma baseline viva; `max` pelo id resolve o empate
    impossível sem depender dele.
    """
    if kpi is None:
        return None
    vivas = _medicoes_vivas(kpi, "baseline")
    if not vivas:
        return None
    return max(vivas, key=lambda medicao: medicao.pk).value


def outcome_mais_recente_de(kpi: KPI | None) -> Decimal | None:
    """O valor do `Outcome` mais recente deste KPI, ou `None`.

    "Mais recente" é por `measured_at`, e não por `created_at`: quem digita a leitura de outubro em
    novembro está registrando outubro. O id desempata para a ordem ser estável entre duas leituras.
    """
    if kpi is None:
        return None
    vivas = _medicoes_vivas(kpi, "outcome")
    if not vivas:
        return None
    return max(vivas, key=lambda medicao: (medicao.measured_at, medicao.pk)).value
