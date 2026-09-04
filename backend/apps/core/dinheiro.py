"""Dinheiro na API: **uma** representação, e ela é texto (ADR 0068).

**Por que texto.** O encoder JSON do DRF converte `Decimal` em `float`
(`rest_framework/utils/encoders.py`) — o comentário de lá diz que aquele ramo existe justamente
para o `Decimal` que escapou de um `DecimalField`, que é o caso de todo agregador. Sem conversão,
`Decimal("40000.00")` chega ao cliente como `40000.0`: perde a forma em que foi digitado, e
`10000.01` passa a depender do binário. O `COERCE_DECIMAL_TO_STRING` do DRF já faz isso por todo
`ModelSerializer` do produto — `Invoice.amount`, `Project.actual_value`,
`CommercialOpportunity.estimated_value` saem como string desde sempre. O que faltava era o dinheiro
que **não** passa por serializer nenhum: os agregadores que devolvem `dict` cru.

**Por que num lugar só.** Duas representações do mesmo campo na mesma API obrigam cada consumidor
a saber qual está lendo — `amount` texto em `/invoices/` e `revenue` número em `/analytics/` é a
classe de defeito que nenhum teste pega, porque os dois formatos são "válidos". A conversão morava
em três lugares que argumentavam a mesma coisa em três docstrings (o fechamento `_dinheiro` de
`cobranca.painel`, `ProcessSerializer.get_custo` e o `frontend/src/dinheiro.ts` do outro lado);
esta função é o lugar único do lado do servidor, e `dinheiro.ts` é o gêmeo dela na borda da tela —
lá o `Number()` é a **última** coisa que acontece com o valor, e formatar não soma.

**Duas casas, e é `:.2f` e não `str()`.** `str(Decimal("4000"))` devolve `"4000"`, e o mesmo campo
sairia ora com centavos ora sem, conforme o que a agregação produziu. A forma é a mesma que o
`DecimalField(decimal_places=2)` do DRF emite, que é o ponto: quem lê a API não distingue o campo
que passou por serializer do que foi montado à mão.

**`None` sobrevive como `None`.** "Não há o que somar" e "somou zero" são fatos diferentes —
`Sum` de queryset vazio é `NULL`, e uma etapa do funil sem oportunidade nenhuma não vale
`"0.00"`. É a mesma regra do `nao_apurado` de `Process.custo_do_estado_atual` e do
`kpi_baseline` nulável: preencher a ausência com zero apaga a distinção que o produto precisa
mostrar.

**O que fica de fora.** Índice calculado não é dinheiro: `roi`, `win_rate`, `acceptance_rate` e
`avg_ticket` nascem de uma divisão, não têm centavo a perder e continuam `float` — o critério está
escrito na ADR 0068. `portal.build_snapshot` também fica fora: é projeção para o One, com contrato
próprio versionado e `float()` explícito.
"""

from __future__ import annotations

from decimal import Decimal
from typing import overload


@overload
def dinheiro(valor: Decimal) -> str: ...


@overload
def dinheiro(valor: None) -> None: ...


def dinheiro(valor: Decimal | None) -> str | None:
    """O valor monetário como o JSON deve levá-lo: texto com duas casas, ou `None`.

    As duas assinaturas acima existem para o chamador que sabe que o número não é nulo não
    precisar tratar um `str | None` que nunca ocorre — `roi.revenue` soma com `Decimal("0")` de
    piso e sempre tem valor, enquanto `PipelineStageRow.estimated_total` é nulo de propósito.

    `Decimal` e não `Decimal | int`: `f"{0:.2f}"` funcionaria, mas aceitar `int` legitimaria o
    `or 0` que os agregados usavam como piso — e piso de dinheiro é `Decimal("0")`, pela mesma
    razão de `process.py` evitar `float` por dentro.
    """
    if valor is None:
        return None
    return f"{valor:.2f}"
