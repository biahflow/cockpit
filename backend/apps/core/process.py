"""O custo do estado atual de um processo mapeado (FDD 039).

A fórmula é do material, literal (`docs/metodologia-fde.md:87-88`):
`Volume × Tempo × Pessoas × Custo + Retrabalho + Erros + Perdas + Espera + Risco`.

Função pura e explicável, no molde de `health.assess_project_health`: devolve **as parcelas**
junto do total, e não só o número. Um custo de estado atual é argumento que a casa leva ao
cliente; um número sem a conta que o produziu não se discute, se aceita ou se rejeita — e é
justamente o que a metodologia proíbe ao exigir que todo achado seja rotulado.

**Ausência é dita, nunca preenchida com zero.** É a decisão inteira deste módulo: o que faltou
sai em `nao_apurado`, e não como parcela de valor zero. Somar zero afirmaria que aquela perda não
existe — e "não medimos o retrabalho" e "não há retrabalho" são conclusões opostas. Mesmo
movimento do KPI sem base registrada em `ai.py` (FDD 027).

Toda a aritmética é `Decimal`. `float` aqui somaria centavos com erro e o total de uma reunião
não fecharia com o da seguinte por motivo nenhum.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import Process

#: O rótulo do núcleo multiplicativo — as quatro perguntas que, juntas, dizem quanto custa
#: simplesmente executar o processo como ele é hoje.
ROTULO_NUCLEO = "Execução do processo"

#: Os cinco aditivos mensais, na ordem da fórmula. Campo → rótulo legível, e não string solta em
#: cada consumidor: a tela e o teste leem daqui, senão "Retrabalho" e "retrabalho" viram dois
#: rótulos diferentes para a mesma parcela no dia em que alguém redigitar.
ADITIVOS: tuple[tuple[str, str], ...] = (
    ("retrabalho_mes", "Retrabalho"),
    ("erros_mes", "Erros"),
    ("perdas_mes", "Perdas"),
    ("espera_mes", "Espera"),
    ("risco_mes", "Risco"),
)

#: Os seis rótulos possíveis, na ordem em que aparecem.
ROTULOS_CUSTO: tuple[str, ...] = (ROTULO_NUCLEO, *(rotulo for _, rotulo in ADITIVOS))

#: Os quatro fatores do núcleo. Multiplicativos: **basta um faltar** para a parcela inteira não
#: poder ser apurada, porque o produto com um fator desconhecido é desconhecido.
FATORES_NUCLEO: tuple[str, ...] = ("volume_mes", "tempo_horas", "pessoas", "custo_hora")

SUSTENTADO = "sustentado"
HIPOTESE = "hipotese"

#: Duas casas, porque é dinheiro. O núcleo é um produto de quatro fatores e `Decimal` **soma
#: expoentes** na multiplicação: `0.50 × 100 × 1 × 80.00` sai como `4000.0000`. Deixar as quatro
#: casas atravessarem faria a API devolver um valor com uma forma que ninguém digitou, diferente
#: da de `Invoice.amount`, e obrigaria cada consumidor a arredondar por conta — que é como dois
#: lugares passam a arredondar diferente.
CENTAVOS = Decimal("0.01")


def _centavos(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def custo_do_estado_atual(processo: Process) -> dict[str, Any]:
    """Quanto o processo custa por mês como ele é hoje — com a conta à vista.

    Devolve `parcelas` (o que foi possível apurar, com rótulo e valor), `total` (a soma delas),
    `nao_apurado` (os rótulos que ficaram de fora por falta de insumo) e `sustentacao`.

    **`total = 0` com `nao_apurado` cheio não significa "custa zero".** Significa "não há insumo
    para dizer". Quem consome distingue os dois casos por `nao_apurado`, e não pelo total: um
    processo recém-cadastrado devolve zero com seis entradas em `nao_apurado`, e apresentá-lo como
    "custo zero" seria a casa afirmando ao cliente o oposto do que ela sabe.

    `sustentacao` responde à outra metade da metodologia: o número vale mais ou menos conforme
    exista evidência rotulada como **fato** por trás dele (`docs/metodologia-fde.md:86`). É
    `"sustentado"` quando há pelo menos uma evidência viva com `rotulo=fato` no processo, e
    `"hipotese"` caso contrário — inclusive quando o único fato registrado foi arquivado, porque
    registro desfeito não sustenta número.
    """
    from .models import Evidencia

    parcelas: list[dict[str, Any]] = []
    nao_apurado: list[str] = []

    fatores = [getattr(processo, campo) for campo in FATORES_NUCLEO]
    if all(fator is not None for fator in fatores):
        volume, tempo, pessoas, custo_hora = fatores
        # `Decimal * int` continua `Decimal`; o que não pode entrar aqui é `float`.
        parcelas.append(
            {"label": ROTULO_NUCLEO, "valor": _centavos(tempo * volume * pessoas * custo_hora)}
        )
    else:
        nao_apurado.append(ROTULO_NUCLEO)

    for campo, rotulo in ADITIVOS:
        valor = getattr(processo, campo)
        if valor is None:
            nao_apurado.append(rotulo)
        else:
            # Arredondado como o núcleo, e não porque o campo permita mais casas — ele é
            # `decimal_places=2`. É que a parcela precisa ter **a mesma forma** venha de onde
            # vier: uma instância ainda não salva (a prévia da tela, o rascunho da extração)
            # carrega o que lhe deram, e uma parcela com três casas no meio de cinco com duas é a
            # linha que faz a soma exibida não fechar.
            parcelas.append({"label": rotulo, "valor": _centavos(valor)})

    # O total é a soma das parcelas **já arredondadas**, e não o arredondamento da soma. Só assim
    # a conta que a tela mostra fecha: somar em precisão cheia e arredondar no fim produz um total
    # que difere em um centavo da soma das linhas exibidas, numa tela cujo propósito inteiro é
    # mostrar a conta. Quem vê parcela que não bate com total para de confiar nas duas.
    total = sum((parcela["valor"] for parcela in parcelas), Decimal("0"))

    # `processo.pk` primeiro porque o gerente reverso recusa instância não salva: quem quiser a
    # conta antes de gravar (uma prévia na tela, um rascunho vindo de extração) recebe o cálculo e
    # `"hipotese"` — que é a resposta certa, já que evidência nenhuma foi registrada ainda.
    sustentado = bool(processo.pk) and processo.evidencias.filter(
        archived_at__isnull=True, rotulo=Evidencia.Rotulo.FATO
    ).exists()

    return {
        "parcelas": parcelas,
        "total": total,
        "nao_apurado": nao_apurado,
        "sustentacao": SUSTENTADO if sustentado else HIPOTESE,
    }
