# FDD 048 — "Onde atuar" não tinha onde morar

> **A cadeia do PRIORITIZE: `PainPoint` → `ImprovementOpportunity` → `PriorityAssessment` →
> `SolutionHypothesis`.** É a quarta fatia da ontologia (ADR 0049, issue #68). A avaliação de
> prioridade é imutável e versionada, com os pesos congelados na linha (ADR 0054); o rank **não é
> campo**; e a oportunidade de melhoria não encosta no funil comercial.

## Jornada

O PRIORITIZE é a segunda pergunta da escada FDE — *"onde devemos atuar?"*
(`docs/metodologia-fde.md`). Até aqui ela não tinha entidade nenhuma no domínio: existia como
fase configurável (`JourneyPhase` com `canonical_stage="prioritize"`) e como prosa em documento.

A consequência prática aparecia em três lugares.

**O "Opportunity Score" que o método promete não tinha onde morar.** O Executive Readout fala dele
ao cliente, e o produto tem dois números que **não** são ele: `Lead.ai_score` é score de aquisição
e `Project.ai_opportunity` é maturidade de IA da conta. O mapa de linguagem §5 lista os dois como
termos banidos para esse papel, exatamente porque a tentação de reaproveitá-los é grande e o erro
é invisível — um número plausível na tela certa não denuncia que mede outra coisa.

**A dor era prosa dentro da evidência.** A Fase 3 (FDD 045) separou o trecho bruto (`Evidence`) da
afirmação (`Finding`), e parou ali. O passo seguinte da metodologia não é nenhum dos dois: um
achado ("o fechamento leva dois dias") não é uma dor; a dor é o custo que aquilo impõe, e é ela
que se agrupa em oportunidade de melhoria. Sem `PainPoint`, o que se agrupava era memória de
reunião — o mesmo defeito que a FDD 039 existe para corrigir, um nível acima.

**E priorizar não deixava rastro.** Priorizar é escolher, e escolha sem critério registrado é
opinião com aparência de método. A pergunta "por que este item subiu desde a semana passada?" não
tinha resposta possível: não havia critério, não havia versão, não havia autor.

## O que esta fatia entrega

**Quatro entidades, e a divisão de trabalho entre elas é a fatia inteira.**

- **`PainPoint`** — a dor observada: onde dói, de que tipo (`financial`/`operational`/
  `experience`/`risk`), quanto custa (opcional), e quais `Finding` a sustentam. Ancora na
  **conta**, como `Process`, `Evidence` e `Finding`, e pelo mesmo motivo: o que se observou sobre
  a operação de uma empresa sobrevive à venda que a descobriu.
- **`ImprovementOpportunity`** — o agrupamento de dores em algo sobre o que se pode decidir: a
  mudança desejada, a hipótese de impacto e as dores que a compõem. É o Opportunity Map do método.
- **`PriorityAssessment`** — a avaliação que produz o Opportunity Score: cinco dimensões de 1 a 5,
  a fórmula que as pesa, os pesos efetivamente usados e a versão.
- **`SolutionHypothesis`** — as apostas concorrentes de solução, das quais **no máximo uma** está
  escolhida por vez.

**Três invariantes com dente:**

1. **`PainPoint` em `confirmed` tem ao menos um `Finding` vivo por baixo** — e a regra tem três
   metades, nas três pontas por onde ela pode vazar. Na **criação** e no **`PATCH`**, o
   `PainPointSerializer.validate` recusa com 400. No **arquivamento do último achado**,
   `FindingViewSet.perform_destroy` recusa com 409. Nada disso cabe no `clean()` do modelo: a
   pergunta é sobre um M2M, que só existe depois do save — é a mesma razão pela qual a metade
   "evidência viva" da invariante §6.9 mora no `FindingSerializer`.
2. **A avaliação é imutável.** Repriorizar cria a versão seguinte; editar não existe.
   `PriorityAssessmentViewSet` não expõe `PUT` nem `PATCH`, e a tentativa é **405** — "este método
   não existe aqui" — e não 400, que mandaria quem lê corrigir um corpo perfeitamente bom.
3. **Uma hipótese escolhida por oportunidade.** `UniqueConstraint` parcial sobre
   `status="chosen"` e `archived_at IS NULL`. Concorrer é o estado normal; escolher duas é
   contradição.

**Os pesos ficam congelados na linha.** `priority.FORMULAS` é o catálogo de hoje; a avaliação
**copia** o conjunto para `weights` no instante em que nasce. Referenciar o catálogo em vez de
copiá-lo faria uma edição de peso amanhã reescrever, em silêncio, o score de toda avaliação de
ontem — inclusive as que já foram apresentadas ao cliente. É a decisão da ADR 0054.

**O recomendador passa a ler a avaliação vigente.** `recommendations.build_recommendations` ganha
uma sugestão que aponta a `ImprovementOpportunity` priorizada de maior score de cada conta, com a
URL da tela de priorização. O número que ordena a sugestão é o mesmo que a tela mostra, com a
fórmula e a versão que o produziram gravadas na linha — e não um campo opaco.

## Critérios de aceite

- `PainPoint` com `status=confirmed` sem `Finding` vivo é 400, na criação **e** no `PATCH`; com um
  achado vivo, passa.
- Arquivar o **último** `Finding` vivo de uma dor confirmada é 409, e a dor não é rebaixada em
  silêncio. Arquivar o penúltimo passa; arquivar o único achado de uma dor **observada** passa; e
  o de uma dor já arquivada também.
- `impact_estimate` ausente fica **nulo** e nunca vira zero; zero informado é preservado.
- Cada avaliação nova incrementa `version`. A versão de uma avaliação arquivada **não** é
  reaproveitada.
- `PUT`/`PATCH` numa avaliação respondem 405.
- `score` é calculado e ignora o valor que vier no corpo; `weights` sai do catálogo na criação e
  não muda depois que `FORMULAS` muda.
- `formula_key` desconhecida é 400; nota fora de 1–5 é 400.
- Duas `SolutionHypothesis` `chosen` vivas na mesma oportunidade são recusadas; a escolhida
  arquivada libera a próxima.
- `engagement` de outra conta é recusado, no serializer **e** no `clean()` do modelo.
- O rank sai da ordenação por score decrescente da avaliação vigente, dentro da conta; a
  oportunidade sem avaliação sai com `rank`, `score` e `assessment_version` **nulos**, nunca zero;
  a descartada sai do ranking.
- `ImprovementOpportunity` não referencia `PipelineStage` em campo nenhum.
- Entrega que não participa de nenhum projeto do cliente não lê e não escreve os quatro recursos,
  e não pendura avaliação nem hipótese em oportunidade de outra conta.

## Contrato

Rotas novas em `/api/v1/`, todas com `?archived=1` e `POST /unarchive/`:

| Rota | Âncora do recorte | Métodos |
| --- | --- | --- |
| `/pain-points/` (`?account=`, `?process=`, `?step=`, `?status=`, `?impact_type=`) | conta | todos |
| `/improvement-opportunities/` (`?account=`, `?engagement=`, `?status=`) | conta | todos |
| `/priority-assessments/` (`?improvement_opportunity=`, `?formula_key=`) | conta da oportunidade | `GET`, `POST`, `DELETE` |
| `/solution-hypotheses/` (`?improvement_opportunity=`, `?status=`) | conta da oportunidade | todos |

Aditivo: nada foi removido nem mudou de forma. **Nomes canônicos e nenhum alias** — alias existe
para não quebrar chave que a `/api/v1/` já prometeu, e aqui não há chave antiga nenhuma.

`improvement-opportunities` no plural qualificado, e nunca `opportunities`: a rota de venda é
`/commercial-opportunities/`, e as duas não se encostam (`language-map` §5).

**Vendas e Entrega escrevem os quatro**, pelo argumento que a FDD 045 herdou da FDD 039: quem
conduz Discovery e prioriza é das duas áreas, e um registro que só metade da casa pode fazer é um
registro que não acontece.

`ImprovementOpportunitySerializer` publica três campos derivados só de leitura: `score`,
`assessment_version` e `rank`. Os três vêm `null` juntos quando não há avaliação vigente.

## Decisões

### `rank` é derivado, e não campo — desvio deliberado da issue

A issue #68 lista `rank` entre os campos mínimos de `PriorityAssessment`. **Ele não foi criado**,
e a razão é a mesma que o `CLAUDE.md` dá para mapa de estado: um `rank` gravado que precisa
concordar com a ordenação por score é uma **segunda definição da mesma coisa**, e ela diverge da
primeira em silêncio — basta uma repriorização que ninguém recalcule, e nada fica vermelho. O rank
sai de `priority.ranking_da_conta`, num lugar só, e o serializer o publica.

O critério de aceite da issue pede preservar "fórmula, dimensões e versão", e as três estão
preservadas: `formula_key`, os cinco campos e `version`, mais os `weights` que a issue não pedia.

Entram no ranking as oportunidades **vivas, não descartadas e com avaliação vigente**. Uma
descartada ocupando o #1 seria uma lista de trabalho que aponta para lugar nenhum; uma sem
avaliação não tem por onde ser ordenada, e é ela que a tela mostra com `—`.

### Por que a imutabilidade mora na rota, e não no `save()`

Um `save()` que recusasse toda atualização recusaria junto `archive()` e `unarchive`, que são
gravações legítimas da mesma linha (`TimestampedModel`). A rota é o lugar em que "editar não
existe" pode ser dito sem apagar o arquivamento — e o 405 diz isso melhor do que qualquer 400.

### Por que `version` é atribuída sob trava

`select_for_update` sobre a oportunidade, pela razão exata do `convert-to-project` (ADR 0050): sem
a trava, duas requisições concorrentes leem `max(version)` ao mesmo tempo, escrevem a mesma versão
e a constraint estoura como 500 — um erro de servidor no lugar de uma sequência.

A constraint de versão é **incondicional** ao arquivamento, ao contrário da hipótese escolhida: a
avaliação arquivada continua ocupando o seu número. Reaproveitá-lo faria duas linhas se chamarem
"v2", e a comparação com a semana passada passaria a depender de qual delas alguém abriu.

### Por que o piso da escala é 20, e não zero

Cinco dimensões de 1 a 5 com nota mínima dão 20 em 100. Fazer o mínimo cair em zero exigiria
tratar "1" como ausência — e é a ausência que o produto precisa distinguir: oportunidade **sem**
avaliação mostra `—`, nunca zero (DAP priorização r1). Uma escala que produzisse zero avaliado
tornaria os dois casos indistinguíveis na leitura, que é o defeito que
`Process.custo_do_estado_atual` já evita com `nao_apurado` e que `DigitalEmployee.kpi_baseline`
evita sendo nulável.

### Por que `impact_estimate` é nulável em vez de `default=0`

Mesma distinção, no campo de dinheiro: nulo é "não estimado", zero é "estimamos e não custa nada".
Um total exibido sem essa diferença vira "custo zero" na leitura rápida, e a casa passa a afirmar
ao cliente o oposto do que sabe.

### Por que a hipótese escolhida é validada à mão

O `CLAUDE.md` pede não escrever à mão a checagem que o DRF deriva das constraints. A exceção aqui
tem motivo verificado: o DRF só deriva o validador de uma `UniqueConstraint` **condicional** quando
todos os campos da condição são campos do serializer (`ModelSerializer.get_unique_together_validators`,
DRF 3.16). A condição cita `archived_at`, que nenhum serializer da casa expõe — então o validador é
descartado em silêncio e o `IntegrityError` subiria como 500. A constraint continua sendo a
garantia; a validação transforma a recusa num 400 legível.

### Por que a fronteira de conta é cobrada também pelo M2M

`PainPoint.findings` e `ImprovementOpportunity.pain_points` são validados contra a conta pela razão
que a FDD 045 deu para validar os quatro vínculos opcionais da `Evidence` em vez de só os dois
caros: é a mesma classe de vínculo cruzado, e deixar um solto faria quem lesse o código depois
concluir que existe uma razão para a exceção. Não há.

### `ImprovementOpportunity` não é venda

Nenhum campo, nenhum filtro e nenhum import de `PipelineStage`. O mapa de linguagem §2 manda nunca
chamá-la de Commercial Opportunity nem de Projeto, e a §5 bane `Opportunity` sem qualificador
exatamente porque as duas colidiam: uma é receita a fechar, a outra é melhoria operacional a
priorizar. Um campo de etapa aqui traria o funil comercial para dentro do backlog de melhoria, e o
funil da casa passaria a somar melhorias que ninguém vendeu. Há teste afirmando isso sobre o
`_meta` do modelo, porque um campo acrescentado por distração não seria pego por mais nada.

### "Ainda não virou trabalho", no recomendador, é "sem hipótese escolhida"

A oportunidade não aponta para projeto, e o gate que a transforma em entrega
(`FeasibilityAssessment`) é da Fase 5. O único sinal observável nesta fatia é a hipótese escolhida
— o passo seguinte da cadeia. Quando o gate existir, é essa condição que muda, e é por isso que
ela está escrita no lugar em que se lê, e não escondida num filtro.

## Testes

- `apps/core/tests/test_priorizacao.py` — as três metades da invariante do `confirmed` (criação,
  `PATCH` e arquivamento, com os três controles simétricos do 409), a distinção nulo/zero do
  impacto, a fronteira de conta nas quatro pontas com controle positivo em cada uma, a sequência
  de versões e o número que a arquivada não devolve, o 405 do `PUT`/`PATCH`, o score conferido à
  mão contra a fórmula, o congelamento dos pesos (com o controle que mostra que o número **seria**
  outro), o rank derivado e o `null` de quem não foi avaliado, a descartada fora do ranking, as
  hipóteses concorrentes e a unicidade da escolhida, o recomendador nas três condições, e o recorte
  da Entrega nos quatro recursos.
- A trava de concorrência é exercida como **presença no caminho** (`select_for_update` chamado
  sobre `ImprovementOpportunity` durante a criação), e não com duas transações reais: a suíte roda
  em SQLite, onde `FOR UPDATE` é no-op.

## Fora deste recorte

- **Tela.** Nenhuma. A superfície tem DAP aprovado (`docs/design/dap-priorizacao-r1/`, decisões
  A1 · B1 · C1 · D1 · E1 mais a primitiva `.row-meta`) e vem na fatia seguinte. Entraram só os
  tipos em `frontend/src/types.ts`, sem consumidor, para a próxima não começar do zero — como a
  Fase 3 fez.
- **A primitiva `.row-meta`.** Nasce em `index.css` com consumidor no mesmo commit, e o consumidor
  é a tela. Classe sem chamador é a mesma dívida de chamador sem classe (ADR 0026).
- **A sugestão de score por IA.** O DAP a deixa desenhada e esmaecida: a IA é insumo, nunca
  decisão, no molde de `Qualification.ai_suggested_outcome` (FDD 044).
- **O Opportunity Map como artefato de cliente.** Vira real quando houver `Artifact(kind=...)` para
  ele.
- **A Fase 5** (`FeasibilityAssessment`, `ProveExperiment`, `KPI`, `Measurement`,
  `ValueLedgerEntry`) — é a issue #69.
- **O One.** Nada aqui projeta para o portal do cliente; `PainPoint` e `ImprovementOpportunity`
  aparecem lá pelo `language-map` §3, e isso é decisão do repo `one`.
- **Renomear tabela.** Não se aplica: os quatro nascem com o nome canônico, e por isso nenhum leva
  `Meta.db_table` — esse é o instrumento de quem renomeia modelo existente (ADR 0052).
