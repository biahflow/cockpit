# ADR 0054 — A avaliação de prioridade é imutável, e a fórmula fica congelada na linha

**Status:** aceita
**Data:** 2026-08-29
**Depende de:** ADR 0049 (a ontologia entra pela linguagem) · `docs/ontology/language-map.md` §2, §5
**Implementada por:** FDD 048 · issue #68 (Fase 4 da ontologia)

## Contexto

O PRIORITIZE precisa produzir um número — o Opportunity Score — que ordena o backlog de melhoria
de uma conta e que chega ao cliente no Executive Readout. Um número desses tem duas propriedades
que não são óbvias e que, se não forem decididas aqui, serão decididas por omissão na primeira
tela:

1. **Ele é comparável no tempo, ou não é nada.** "Este item subiu desde a semana passada" só é uma
   afirmação se existir o item da semana passada. Uma avaliação que se sobrescreve apaga o critério
   anterior e transforma toda comparação em memória de quem estava na sala.
2. **Ele é reproduzível, ou é opinião com aparência de cálculo.** Se o score for função de um
   catálogo de pesos que vive no código, ele muda toda vez que alguém ajusta o catálogo — inclusive
   retroativamente, inclusive nas avaliações já apresentadas ao cliente, e sem nada ficar vermelho.

O repositório já tem os dois precedentes. O `Case` congelado (FDD 027) guarda a métrica como ela
era no dia em que virou prova social, e não uma referência viva ao projeto. A instanciação de
blueprint (`blueprints.instantiate`) **copia** do catálogo em vez de referenciá-lo, pelo mesmo
motivo. O que falta é dizer que priorização é do mesmo tipo.

Há uma terceira pressão, e ela vem da issue #68: a lista de campos mínimos inclui `rank`. Um rank
gravado ao lado de um score é a forma mais barata de servir uma tela ordenada — e é uma segunda
definição do mesmo fato.

## Decisão

### A `PriorityAssessment` é imutável; repriorizar cria a versão seguinte

Não existe editar uma avaliação. `PriorityAssessmentViewSet` não expõe `PUT` nem `PATCH`, e a
tentativa responde **405**: "este método não existe aqui", e não 400, que mandaria quem lê corrigir
um corpo perfeitamente bom.

`version` é atribuída pelo servidor, sob `select_for_update` da oportunidade, pela razão exata do
`convert-to-project` (ADR 0050): sem a trava, duas requisições concorrentes leem `max(version)`
juntas e a constraint estoura como 500. A unicidade `(improvement_opportunity, version)` é
**incondicional** ao arquivamento — a versão arquivada continua ocupando o número, porque duas
linhas chamadas "v2" fariam a comparação com a semana passada depender de qual delas alguém abriu.

A imutabilidade mora na **rota**, e não no `save()`: um `save()` que recusasse toda atualização
recusaria junto `archive()`/`unarchive`, que são gravações legítimas da mesma linha.

### Os pesos são copiados para a linha, nunca referenciados

`apps/core/priority.FORMULAS` é o catálogo. Na criação, a avaliação **copia** o conjunto de pesos
para `PriorityAssessment.weights` e calcula `score` a partir dessa cópia. `formula_key` nomeia qual
fórmula produziu o número e sobrevive à linha.

`calcular_score` é função pura e **recebe** os pesos em vez de consultar o catálogo: recalcular um
score antigo com os pesos que aquela linha guardou tem de dar o mesmo número de quando ele foi
gravado. Uma implementação que lesse `FORMULAS` por dentro faria a cópia não servir para nada.

`score` nunca é aceito do cliente. A escala vai de 20 a 100, e o piso não é zero de propósito: é a
**ausência** de avaliação que o produto precisa distinguir, e ela é `null` na API e `—` na tela
(DAP priorização r1). Uma escala que produzisse zero avaliado tornaria os dois casos
indistinguíveis na leitura.

### `rank` é derivado, e não coluna

O rank sai da ordenação por score decrescente da avaliação vigente, dentro da conta, em
`priority.ranking_da_conta` — um lugar só, no molde de `Project.objects.visible_to` (ADR 0010). A
API o publica como campo calculado de `ImprovementOpportunity`, ao lado de `score` e
`assessment_version`.

Isto é um **desvio deliberado** da lista de campos da issue #68, pela razão que o `CLAUDE.md` já dá
para mapa de estado: uma segunda definição do mesmo fato diverge da primeira em silêncio. Basta uma
repriorização que ninguém recalcule.

### "Vigente" é definido uma vez

A avaliação vigente é a de maior `version` não arquivada, e mora em
`ImprovementOpportunity.current_assessment`. Nem a tela, nem o recomendador, nem o ranking
reexpressam a regra em query própria.

## Consequências

- A pergunta "por que este item subiu?" passa a ter resposta auditável: as duas versões existem,
  com as cinco dimensões, os pesos e o autor de cada uma.
- Mudar a fórmula deixa de ser um ato retroativo. `FORMULAS["v2"]` convive com `v1`, e as linhas
  antigas continuam dizendo `v1` — o que as tornou comparáveis foi o critério, não a data.
- O histórico cresce: repriorizar não substitui, acumula. É o custo aceito, e é o mesmo do `Case`
  congelado.
- A tela precisa mostrar a versão ao lado do score (decisão B1 do DAP). Um score sem versão desfaz,
  na leitura, a decisão que o modelo tomou na escrita.
- O rank não pode ser filtrado nem ordenado no banco. Para os volumes desta fase — dezenas de
  oportunidades por conta — é aceitável; se deixar de ser, a saída é uma anotação de queryset, e
  não uma coluna.

## Alternativas consideradas

- **Avaliação editável, com histórico em tabela de auditoria.** Um registro a mais e a mesma
  informação, ao custo de a tela ler de um lugar e o histórico morar em outro — e auditoria que não
  é o dado é auditoria que ninguém abre.
- **Guardar só `formula_key` e recalcular pelo catálogo.** Menos uma coluna, e é exatamente o
  defeito: a edição de um peso reescreveria em silêncio números já apresentados ao cliente.
- **`rank` gravado, recalculado por signal ou por job.** Serve a tela sem query extra, ao custo de
  uma janela em que o campo mente. A janela é curta e é justamente aquela em que alguém reprioriza
  e olha.
- **Escala de 0 a 100 linear (nota 1 → 0).** Mais bonita de ler, e apaga a diferença entre "avaliado
  e vale pouco" e "ninguém avaliou".
