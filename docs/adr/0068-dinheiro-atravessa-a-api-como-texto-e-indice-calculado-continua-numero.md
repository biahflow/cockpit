# ADR 0068 — Dinheiro atravessa a API como texto, e índice calculado continua número

**Status:** aceita
**Data:** 2026-09-04
**Depende de:** ADR 0067 (o ROI continua saindo do contratado) · ADR 0054 (a fórmula congelada e o
`nao_apurado`) · ADR 0055 (`null` é "não medido", nunca zero) · ADR 0066 (a `/api/v2/` e o mapa de
aliases) · `docs/ontology/aliases.md` §2c
**Implementada por:** a fatia que converte os agregadores de `dict` cru

## Contexto

O produto já tinha a regra, escrita três vezes em comentário de código e nenhuma vez como decisão.

`REST_FRAMEWORK["COERCE_DECIMAL_TO_STRING"]` é o padrão do DRF, então todo `ModelSerializer` do
repositório emite dinheiro como string desde sempre: `Invoice.amount`, `Project.actual_value`,
`Project.cost`, `CommercialOpportunity.estimated_value`, `Service.list_price` e os demais
`DecimalField` do domínio. A razão está escrita em `ProcessSerializer.get_custo`, em
`cobranca.painel` e em `frontend/src/dinheiro.ts`, cada um argumentando a mesma coisa com palavras
próprias: o encoder JSON do DRF converte `Decimal` em `float`, `Decimal("40000.00")` chega ao
cliente como `40000.0`, e `10000.01` passa a depender do binário.

Quem escapava da regra eram os **agregadores**. `/analytics/`, `/dashboard/`,
`/clients/overview/` e `/invoices/summary/` não passam por serializer nenhum — montam `dict` e o
devolvem em `Response(...)`, e o `@extend_schema` acima deles descreve a resposta sem serializá-la.
Doze campos monetários atravessavam ali — sete declarações honestas e cinco em duas declarações
que já prometiam texto —, e os dois grupos tinham defeitos diferentes:

| Campo | O que o contrato dizia | O que o corpo emitia |
| --- | --- | --- |
| `PipelineStageRow.estimated_total` (`/analytics/` e `/dashboard/`) | `number` | `number` |
| `RoiBreakdownRow.revenue` / `.cost` | `number` | `number` |
| `FunnelTierRow.estimated_total` | `number` | `number` |
| `FunnelSourceRow.revenue` | `number` | `number` |
| `AnalyticsRoi.revenue` / `.cost` | `number` | `number` |
| `AccountOverviewRoi.revenue` / `.cost` | **`string`** | `number` |
| `InvoiceSummary.open` / `.overdue` / `.paid` | **`string`** | `number` |

As duas últimas linhas não são preferência de formato: são **contrato mentindo**. Um cliente
gerado a partir do `openapi.yaml` quebra na primeira resposta dessas duas rotas hoje, e nenhum
teste do repositório afirmava sobre a forma daqueles valores.

As sete primeiras declarações eram honestas — e foram feitas honestas de propósito.
`_dinheiro_do_agregado`
nasceu no PR #125 justamente para o esquema parar de prometer `string` onde trafegava `number`, e
a docstring dela descrevia o defeito com precisão. O que aquela fatia não podia decidir era a
**direção** do conserto: fazer o contrato concordar com o corpo, ou o corpo concordar com o
contrato. Ela escolheu a primeira porque a segunda é quebra de `/api/v1/`, e quebra exige decisão
escrita. Este documento é essa decisão, e ela vai na outra direção.

### Por que a duplicidade é pior que qualquer um dos dois formatos

O problema não é `number` nem `string`: é **os dois**. `amount` sai texto em `/invoices/` e
`revenue` sai número em `/analytics/`, e cada consumidor precisa saber, campo a campo, qual dos
dois está lendo. `IndicadoresPage` já convivia com isso na mesma tela — `money.format(Number(...))`
em duas linhas e `money.format(...)` cru em outras duas, dependendo de qual agregado alimentava
qual bloco. Nada disso fica vermelho: os dois formatos renderizam.

### A armadilha que decide se o teste vale

Um teste sobre `response.data` **não pega isto**. Ali o valor ainda é `Decimal`; a conversão para
`float` acontece só na renderização, e é por isso que `ProcessSerializer.get_custo` já dizia, na
própria docstring, que a regressão dele afirma sobre o JSON renderizado.

Comparar valor sem comparar tipo também não pega: `Decimal("100.00") == 100` é `True`, então uma
asserção escrita contra o `Decimal` do modelo passa nas **duas** representações e não distingue
nenhuma. Foi assim que `test_delivery_aggregates_are_scoped` ficou agnóstico à representação sem
que ninguém notasse.

## Decisão

### 1. Dinheiro é `string` decimal de duas casas em toda a API, inclusive em `dict` cru

As sete declarações honestas passam a emitir texto; as duas mentirosas, com seus cinco campos,
passam a cumprir o que já prometiam. Depois desta fatia, **nenhum campo monetário da `/api/v1/`
sai como número**.

A conversão mora num lugar só: `apps.core.dinheiro.dinheiro`. Ela substitui o fechamento
`_dinheiro` que morava dentro de `cobranca.painel` — a primeira das três definições da mesma regra
—, e o argumento inteiro (o encoder, os centavos, as duas representações) migra para a docstring
dela. `frontend/src/dinheiro.ts` é o gêmeo na borda da tela, e continua sendo: formatar não soma, e
aritmética de dinheiro é do servidor.

### 2. Índice calculado não é dinheiro, e o critério é a origem do número

`roi`, `win_rate`, `acceptance_rate` e `avg_ticket` continuam `float`. O critério não é "tem
cifrão": é **de onde o número vem**.

- **Dinheiro** é soma de valores gravados. É exato no domínio decimal, tem duas casas por
  construção (os campos de origem são `DecimalField(decimal_places=2)`), e emiti-lo em `float`
  perde informação que existia.
- **Índice** nasce de uma divisão. Não tem representação decimal exata, não tem centavo a perder, e
  fixá-lo em duas casas seria **arredondar** — decisão de produto, não de formatação.

`avg_ticket` é o caso que testa o critério: ele é um valor em reais, e mesmo assim fica `float`,
porque é `Avg` e não `Sum`. Escrever isto é o ponto — sem o critério, a próxima varredura atrás de
"dinheiro que virou texto" o converteria junto, arredondando uma estatística sem que ninguém tivesse
decidido isso. A guarda está em `tests/regression/test_dinheiro_atravessa_como_texto.py`, que afirma
os dois lados da linha.

### 3. `null` continua `null`, e nunca vira `"0.00"`

`PipelineStageRow.estimated_total` é nulo na etapa sem oportunidade nenhuma (`Sum` de queryset
vazio é `NULL`). "Não há o que somar" e "somou zero" são fatos diferentes, e a conversão preserva a
distinção — é a mesma regra do `nao_apurado` de `Process.custo_do_estado_atual` (ADR 0054) e do
`Measurement.value` nulável (ADR 0055).

Os dois casos vizinhos ficam explícitos porque **não** são esse: `FunnelTierRow.estimated_total`
vale `"0.00"` no degrau sem venda (a linha do degrau sai sempre, e ali zero é o total de fato), e
as três faixas de `InvoiceSummary` também (`Sum(..., default=Decimal("0"))`).

### 4. É quebra deliberada da `/api/v1/`, e não se convive com ela

Sete campos mudam de tipo no contrato publicado. Isso é incompatível, é deliberado, e o
`AGENTS.md` exige exatamente que seja as duas coisas.

Não se emite o par (número e texto lado a lado) como se faz com chave legada renomeada. O mecanismo
de alias de `docs/ontology/aliases.md` §2c governa **nome de chave**, não **tipo de valor**: ele
existe para o consumidor migrar de `client` para `account` lendo os dois. Aqui os dois já existem —
e é justamente a coexistência que é o defeito. Emitir `revenue` número e `revenue_text` string
criaria a terceira representação para resolver o problema de haver duas.

Adiar para a `/api/v2/` também foi recusado, por três razões:

1. **Duas das nove declarações corrigidas não são quebra nenhuma.** `AccountOverviewRoi` e
   `InvoiceSummary` já
   publicam `type: string`; o corpo é que diverge. Adiá-las manteria o contrato mentindo por uma
   versão inteira.
2. **Sobrariam sete campos como o único dinheiro-número da API**, o que é precisamente a ambiguidade
   que esta ADR remove. Meia correção é a pior das três posições.
3. **O consumidor é único e mora neste repositório.** A SPA é o único cliente da `/api/v1/`, e ela
   atravessa junto, no mesmo PR, com o tipo corrigido em `types.ts`. Não há integração externa
   pendurada nestes sete campos — a que existe é o portal do cliente, e ela não passa por aqui.

### 5. `portal.build_snapshot` fica de fora, e isso é parte da decisão

A projeção para o One continua convertendo com `float()` explícito. Ela tem contrato próprio e
versionado (`projection_version`, ADR 0051), está fora do `openapi.yaml`, e o One **nunca renomeia**
nem reinterpreta o que recebe (`language-map` §3). Mexer ali é alterar integração externa, com outro
gate e outro comparador do outro lado — é fatia própria, se algum dia for uma.

A assimetria é consciente e fica registrada: `revenue` sai texto em `/analytics/` e número no
snapshot do portal. São **dois contratos**, não dois formatos do mesmo contrato.

### 6. `_dinheiro_do_agregado` morre aqui

Com a conversão feita no corpo, o que sobrava do invólucro era um `DecimalField` padrão. Um
invólucro que não acrescenta nada é a mesma dívida de uma classe CSS sem consumidor, e as
declarações passam a dizer `serializers.DecimalField(max_digits=14, decimal_places=2)` por
extenso — a mesma linha que `AccountOverviewRoiSerializer` e `InvoiceSummary` já usavam, o que é o
ponto de "uma representação só".

Ela nasceu no PR #125 descrevendo honestamente o defeito e é substituída pela correção dele, não
apagada por engano: o comentário que fica no lugar diz de onde ela veio e por que o argumento dela
morreu.

## Consequências

- Sete propriedades, em cinco componentes do `openapi.yaml` e do `openapi-v2.yaml`, trocam
  `type: number` por `type: string, format: decimal`: `AnalyticsRoi`, `RoiBreakdownRow`,
  `FunnelTierRow`, `FunnelSourceRow` e `PipelineStageRow`. `AccountOverviewRoi` e `InvoiceSummary`
  **não aparecem no diff do contrato** — é assim que se verifica que elas pararam de mentir sem que
  o contrato delas mudasse.
- A SPA converte na borda com `Number()`, que é o que `FinanceiroPage` e `CobrancaPage` já faziam
  para os campos que sempre foram texto. `IndicadoresPage` deixa de ter duas convenções na mesma
  tela.
- `RoiTable` passa a converter a receita **uma vez por linha** e reusar o número na barra e no
  rótulo: `Math.max(...)` sobre string compararia lexicograficamente, e `"9000"` ganharia de
  `"80000"` sem nada quebrar.
- A regressão nova afirma sobre JSON renderizado **e** sobre tipo, nas quatro rotas. Sem a segunda
  metade, o teste passaria nas duas representações e não protegeria nenhuma.
- `test_delivery_aggregates_are_scoped` deixa de comparar com o `Decimal` do modelo e passa a
  comparar a string. O que ele mede continua sendo o recorte; a forma do número ganhou guarda
  própria.
- **A mudança é incompatível e depende do gate humano** que o `AGENTS.md` e a
  `workflows/feature.md` exigem para alteração de contrato. Ela é aceitável porque o único
  consumidor atravessa no mesmo PR — e não seria, no dia em que um consumidor externo se pendurar
  nestes campos.
- O que **não** foi feito, de propósito: a formatação no SPA continua não uniformizada (há
  `Intl.NumberFormat` à mão com casas decimais diferentes por tela, e trocá-las mudaria número
  exibido em painel fora do escopo — a razão já escrita em `frontend/src/dinheiro.ts`).

## Alternativas consideradas

**Manter `number` e deixar o contrato descrevê-lo** — o que o PR #125 fez, e que era a escolha
certa para uma fatia que não podia decidir contrato. Recusada agora porque ela conserta a
declaração e preserva o defeito: dinheiro continuaria em ponto flutuante, `40000.00` continuaria
chegando `40000.0`, e a API continuaria com dois formatos para o mesmo conceito. Corrigir o
documento para descrever o erro não é o mesmo que corrigir o erro.

**Emitir as duas representações lado a lado**, com a nova sob nome próprio. Recusada pelo motivo do
próprio problema: a doença é haver duas, e a cura não pode ser uma terceira. O mecanismo de alias da
`/api/v1/` existe para nome de chave, e usá-lo para tipo de valor inventaria um segundo mecanismo
para uma correção que acontece uma vez.

**Quebrar só na `/api/v2/`.** Recusada pelos três motivos da decisão 4 — duas das correções não são
quebra, meia correção é pior que qualquer extremo, e o único consumidor mora aqui e atravessa junto.

**Converter no SPA, tratando `number` como o formato de entrada.** Recusada porque empurra
aritmética de dinheiro para o cliente, que é exatamente o que `dinheiro.ts` recusa por escrito. O
erro de centavo já teria acontecido no servidor, na serialização; converter depois não o desfaz.

**Converter `avg_ticket` junto, por ser um valor em reais.** Recusada pelo critério da decisão 2:
ele é quociente, e fixá-lo em duas casas é arredondar uma estatística. Se algum dia a média
precisar de casas fixas, isso é decisão de produto sobre o que a tela mostra — e ganha linha
própria, não carona.
