"""A fórmula do Opportunity Score, e a razão de ela ser **copiada** e não referenciada (FDD 048).

O PRIORITIZE responde *"onde devemos atuar?"* (`docs/metodologia-fde.md`), e a resposta é um
número que alguém leva para a reunião. Um número desses só se compara com o da semana passada se
vier junto do critério que o produziu — daí a `PriorityAssessment` guardar `formula_key`, as cinco
dimensões, a `version` **e** os pesos que foram usados.

Os pesos ficam **congelados na linha**. `FORMULAS` é o catálogo de hoje; a avaliação copia o
conjunto para `PriorityAssessment.weights` no instante em que nasce. Referenciar o catálogo em vez
de copiá-lo faria uma edição de peso amanhã reescrever, em silêncio, o score de toda avaliação de
ontem — inclusive as que já foram apresentadas ao cliente. É a mesma decisão do case congelado
(FDD 027) e da cópia do blueprint na instanciação: o que vale é a cópia.

A escala vai de **20 a 100**, e o piso não é zero de propósito. Cinco dimensões de 1 a 5 num
mínimo de 1 dão 20; para o mínimo dar zero seria preciso tratar "1" como ausência, e é justamente
a ausência que o produto precisa saber distinguir — oportunidade **sem** avaliação mostra `—` e
nunca zero (DAP priorização r1). Uma escala que produzisse zero avaliado tornaria os dois casos
indistinguíveis na leitura, que é o defeito que `Process.custo_do_estado_atual` já evita com
`nao_apurado` e que `DigitalEmployee.kpi_baseline` evita sendo nulável.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal

# As cinco dimensões, nesta ordem. Ela é a ordem em que a pergunta é feita na reunião de
# priorização, como o P-S-D-T-E-R do `ProcessStep` — e um formulário fora de ordem faz quem
# preenche pular a que faltou.
DIMENSOES: tuple[str, ...] = (
    "impact",
    "evidence_strength",
    "feasibility",
    "time_to_value",
    "economics",
)

MENOR_NOTA = 1
MAIOR_NOTA = 5

CENTAVOS = Decimal("0.01")

# Catálogo de fórmulas. `formula_key` nomeia qual delas produziu um score, e a chave sobrevive à
# linha: uma avaliação de `v1` continua dizendo `v1` depois que `v2` existir, porque o que a
# tornou comparável foi o critério, não a data.
#
# Os pesos de `v1` dizem o que a metodologia diz: impacto pesa mais que o resto, e a força da
# evidência entra ao lado da viabilidade porque priorizar sobre suposição é o defeito que a
# FDD 045 existe para corrigir. Somam 1 — não por exigência do cálculo, que normaliza pela soma,
# mas para o peso de cada dimensão ser legível como percentual.
FORMULAS: dict[str, dict[str, Decimal]] = {
    "v1": {
        "impact": Decimal("0.30"),
        "evidence_strength": Decimal("0.20"),
        "feasibility": Decimal("0.20"),
        "time_to_value": Decimal("0.15"),
        "economics": Decimal("0.15"),
    },
}

FORMULA_PADRAO = "v1"


def pesos_da_formula(formula_key: str) -> dict[str, str]:
    """Os pesos de uma fórmula prontos para serem **gravados** em `PriorityAssessment.weights`.

    Devolve `str` e não `Decimal` porque o destino é um `JSONField`: `Decimal` não é serializável
    em JSON, e `float` perderia exatidão no caminho de ida e volta — o mesmo motivo pelo qual
    dinheiro trafega como string nesta API.
    """
    return {dimensao: str(peso) for dimensao, peso in FORMULAS[formula_key].items()}


def calcular_score(
    dimensoes: Mapping[str, int | None], pesos: Mapping[str, str | Decimal]
) -> Decimal:
    """A soma ponderada das cinco dimensões, normalizada para a escala de 20 a 100.

    Função pura, e é o ponto: ela recebe os pesos em vez de consultar `FORMULAS`, para que
    recalcular um score antigo com os pesos que **aquela** linha guardou dê o mesmo número de
    quando ele foi gravado. Uma implementação que lesse o catálogo aqui dentro faria a cópia
    congelada em `weights` não servir para nada.
    """
    total_dos_pesos = Decimal(0)
    ponderado = Decimal(0)
    for dimensao in DIMENSOES:
        peso = Decimal(str(pesos[dimensao]))
        nota = dimensoes[dimensao]
        if nota is None:
            raise ValueError(f"A dimensão {dimensao} não foi avaliada.")
        total_dos_pesos += peso
        ponderado += peso * Decimal(nota)
    if total_dos_pesos <= 0:
        raise ValueError("A soma dos pesos precisa ser positiva.")
    bruto = ponderado / total_dos_pesos  # de 1 a 5
    return (bruto / Decimal(MAIOR_NOTA) * Decimal(100)).quantize(
        CENTAVOS, rounding=ROUND_HALF_UP
    )


def ranking_da_conta(account_id: int) -> dict[int, int]:
    """`id da ImprovementOpportunity -> posição`, por score decrescente, dentro de uma conta.

    **O rank não é campo, e esta função é o único lugar em que ele existe** (FDD 048). Um `rank`
    gravado que precisa concordar com a ordenação por score é uma segunda definição da mesma
    coisa, e ela diverge da primeira em silêncio no primeiro reprioritização que ninguém
    recalcular — é o que o `CLAUDE.md` proíbe para mapa de estado, pela mesma razão.

    Entram só as oportunidades **vivas, não descartadas e com avaliação vigente**: uma descartada
    ocupando o #1 seria uma lista de trabalho que aponta para lugar nenhum, e uma sem avaliação
    não tem por onde ser ordenada — ela sai com rank e score nulos, que é o `—` do desenho.
    Empate desempata pelo id, para a ordem ser estável entre duas leituras.
    """
    from .models import ImprovementOpportunity

    oportunidades = (
        ImprovementOpportunity.objects.filter(account_id=account_id, archived_at__isnull=True)
        .exclude(status=ImprovementOpportunity.Status.DISCARDED)
        .prefetch_related("assessments")
    )
    pontuadas: list[tuple[Decimal, int]] = []
    for oportunidade in oportunidades:
        vigente = oportunidade.current_assessment
        if vigente is not None:
            pontuadas.append((vigente.score, oportunidade.pk))
    pontuadas.sort(key=lambda par: (-par[0], par[1]))
    return {pk: posicao for posicao, (_, pk) in enumerate(pontuadas, start=1)}
