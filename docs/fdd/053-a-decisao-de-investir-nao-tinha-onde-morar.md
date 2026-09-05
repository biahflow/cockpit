# FDD 053 — A decisão de investir não tinha onde morar

> **`BusinessCase`: a justificativa do investimento.** É a primeira das três peças que a ADR 0069
> liberou sem o gatilho da ADR 0030. Ela cita a hipótese escolhida e a avaliação vigente da mesma
> `ImprovementOpportunity`, **congela** o custo do estado atual no instante em que nasce, e a
> decisão de investir é uma **action** com autor e carimbo — nunca um `PATCH` de `status`. Não
> atravessa para o One.

## Jornada

A cadeia do PRIORITIZE chega até a aposta: `PainPoint` → `ImprovementOpportunity` →
`PriorityAssessment` → `SolutionHypothesis` (FDD 048). A Fase 5 continua do outro lado do gate, com
o laudo de viabilidade e o experimento (FDD 049). Entre uma coisa e outra existe um ato que o
produto não registrava: **alguém decide gastar dinheiro**.

O material da casa nunca descreveu esse passo, e a ADR 0034 registrou a ausência como "não passa no
teste da 0030" — a peça não aparece como regra pronta. A ADR 0069 mostra que a leitura estava
invertida: *a operação nunca teve onde registrar a decisão, e é a ausência do registro que causa a
ausência do material*, não o contrário. Esperar o material seria esperar que a prática estabilizasse
sem instrumento.

A consequência prática aparecia em três lugares.

**O número de "quanto custa hoje" não parava no tempo.** `Process.custo_do_estado_atual` é função
pura sobre os nove insumos de agora (FDD 039). Um Discovery apura R$ 12.000/mês em março; em maio
alguém corrige o volume e o mesmo processo passa a dizer R$ 19.000. O business case apresentado em
março não pode passar a citar o número de maio — e, sem registro, era exatamente o que acontecia,
porque o único jeito de contar a história era recalcular.

**"Business case" e "case" eram a mesma palavra para duas coisas opostas.** O `Case` (FDD 027) é
prova social congelada: vem *depois* da entrega, é da casa e só sai com autorização do cliente. O
business case vem *antes*, é do cliente, e é interno. Sem os dois nomeados, a conversa comercial
usava um termo para os dois, e a primeira tela que os juntasse mostraria margem a quem não deve
vê-la. O `language-map` v1.5 cunhou `BusinessCase` e pôs cada um no "nunca chamar de" do outro.

**E investir não deixava rastro.** Aprovar era uma frase em ata. A pergunta "quem decidiu isto, e
com que conta na mão?" não tinha resposta — o mesmo defeito que o trio de consentimento do `Case`
existe para corrigir, com dinheiro em cima.

## O que esta fatia entrega

**Uma entidade, e a divisão do que ela referencia e do que ela copia é a fatia inteira.**

`BusinessCase` pende de uma `ImprovementOpportunity` e carrega:

- **`solution_hypothesis`** (`PROTECT`) — a aposta que está sendo orçada. Sem hipótese não há o que
  orçar, e apagá-la por baixo deixaria um número sem objeto.
- **`priority_assessment`** (`PROTECT`) — **referenciada, nunca copiada** (ver as decisões).
- **`investment`, `expected_return_year`, `payback_months`** — os três números do argumento.
- **`current_state_cost` e `current_state_cost_source`** — o custo do estado atual **congelado na
  criação**, e a proveniência do congelamento.
- **`rationale` e `assumptions`** — o argumento e o que ele assume.
- **`status`** (`draft`/`approved`/`rejected`), **`decided_at`, `decided_by`** — a decisão como ato.

**Quatro invariantes com dente:**

1. **O custo do estado atual é congelado na criação, e só ela.** `BusinessCase.save()` chama
   `business_case.custo_congelavel` quando `self._state.adding` — o único instante em que o número
   ainda é medição e não memória. Mesmo movimento de `cases.freeze` (FDD 027) e da cópia dos pesos
   em `PriorityAssessment.save()` (ADR 0054).
2. **Só o fato sustenta número.** Entra na soma apenas o processo cuja conta volta
   `sustentacao == "sustentado"` — isto é, com ao menos um `Finding` vivo em `epistemic_status=fact`
   (ADR 0034) — **e que tenha alguma parcela apurada**. Nada somado devolve **`null`**, nunca `0`.
3. **Decidir é ato com autor e carimbo.** `POST /business-cases/{id}/decide/`, e não um `PATCH` de
   `status`. `clean()` recusa `approved` sem `decided_by` **e** `decided_at`, para o shell e o admin
   caírem na mesma regra.
4. **Decidido é imutável, e um aprovado vivo por oportunidade.** `PUT`/`PATCH` sobre linha decidida
   é **409**; a unicidade do aprovado é `UniqueConstraint` parcial sobre `status="approved"` e
   `archived_at IS NULL`, no molde de `unique_chosen_solution_hypothesis`.

**A proveniência existe para a lacuna ser dita.** `current_state_cost_source` guarda `processos`
(uma linha por processo alcançado, com `id`, `sustentacao`, `total` em texto e `nao_apurado`) e
`somados` (os ids que entraram na conta). Sem ela, um `current_state_cost` nulo seria indistinguível
de um levantamento que ninguém fez, e um total baixo não explicaria que metade dos processos ficou
de fora por ainda ser hipótese.

## Critérios de aceite

- `POST /business-cases/` cria em `draft` e congela o custo. Oportunidade sem processo sustentado
  **ou sem nenhuma parcela apurada** nasce com `current_state_cost = null` e a proveniência
  preenchida, dizendo processo por processo o que faltou.
- **Rejeitar não exige `investment` nem `expected_return_year`; aprovar exige os dois.**
- Editar os insumos do processo depois **não muda** o `current_state_cost` já gravado — e um
  business case criado *depois* da correção lê o número novo.
- O processo alcançado por duas dores conta **uma vez**. Dor arquivada, processo arquivado e dor sem
  processo não entram.
- `decide` grava `status`, `decided_by` e `decided_at`; o segundo `decide` é **409**; `outcome` fora
  de `approved`/`rejected` é **400**; faltando `investment` ou `expected_return_year` é **400**.
- `PATCH` em business case decidido é **409**; em rascunho, passa. `status` não muda por `PATCH`.
- Só um aprovado vivo por `ImprovementOpportunity`: o segundo `decide` com `approved` é **409**, o
  aprovado arquivado libera o próximo, e rejeitar não concorre.
- Hipótese ou avaliação de outra oportunidade é **400** no serializer **e** `ValidationError` no
  `clean()`.
- Vendas e Entrega escrevem; a visibilidade por objeto resolve pela conta da oportunidade; um
  usuário de Entrega sem projeto na conta não lê (lista vazia, 404 no detalhe) e não escreve (403).
- Dinheiro sai como **texto** no JSON, inclusive o `total` de cada linha da proveniência.

## Contrato

Rota nova em `/api/v1/` e em `/api/v2/`, com `?archived=1` e `POST /unarchive/`:

| Rota | Âncora do recorte | Métodos |
| --- | --- | --- |
| `/business-cases/` (`?account=`, `?improvement_opportunity=`, `?status=`) | conta da oportunidade | todos, mais `POST /{id}/decide/` |

Aditivo: nada foi removido nem mudou de forma. **Nome canônico e nenhum alias** — alias existe para
não quebrar chave que a `/api/v1/` já prometeu, e aqui não há chave antiga nenhuma.

`business-cases` e nunca `cases`: `/cases/` já é a prova social congelada, e o `language-map` §2 põe
cada um no "nunca chamar de" do outro.

`BusinessCaseSerializer` publica `account` derivado (só de leitura, a conta chega pela oportunidade)
e mantém read-only o par congelado (`current_state_cost`, `current_state_cost_source`) e o trio da
decisão (`status`, `decided_at`, `decided_by`) — os mesmos dois grupos, pelas mesmas duas razões, do
`CaseSerializer`.

`?account=` fica **fora** de `filter_fields`: naquele mixin o nome do parâmetro **é** o caminho do
ORM, e a conta não é campo deste modelo — `filter(account=…)` estouraria `FieldError`. A tradução
para `improvement_opportunity__account_id` mora no `get_queryset` do viewset, num lugar só.

## Decisões

### Por que a avaliação é **referenciada** e o custo é **copiado**

É a mesma pergunta feita a dois números, com respostas opostas — e a diferença é quem garante que o
número não muda.

`PriorityAssessment` **já é imutável e versionada** (ADR 0054): repriorizar cria a versão seguinte, e
a v2 não reescreve a v1. Gravar o `score` aqui criaria a segunda definição que aquela ADR recusou; as
duas divergiriam em silêncio no dia em que alguém corrigisse a linha, e nada ficaria vermelho.
Referenciar preserva o histórico *e* diz exatamente qual versão sustentou a decisão.

`Process.custo_do_estado_atual` é o inverso: função pura sobre os nove insumos de **agora**, sem
versão nenhuma. Referenciá-la faria o business case de ontem citar a conta de amanhã — que é o
defeito que o `Case` congelado (FDD 027) existe para impedir. Por isso ele é copiado, e por isso o
serializer não expõe caminho de escrita para ele: **não há por onde**, em vez de haver um caminho que
ninguém usa.

### Por que sustentado **e** apurado, e não só sustentado

As duas perguntas são independentes, e confundi-las produz o número errado no caso mais comum de
todos. `sustentacao` pergunta se há `Finding(fact)` vivo por baixo; `nao_apurado` pergunta se há
insumo preenchido. **O processo recém-mapeado numa reunião de Discovery satisfaz a primeira sem a
segunda** — alguém confirmou o que acontece ali antes de alguém medir quanto custa.

Somar aquele processo grava `current_state_cost = 0`, e a tela o exibe como número em vez da lacuna
que a decisão F1 do DAP manda mostrar. O efeito é o pior possível para a peça: um aprovador olhando
um investimento de dezenas de milhares contra um custo do estado atual de "R$ 0,00" — a casa
afirmando o oposto do que ela sabe, exatamente o que `process.py` proíbe por escrito (*"quem consome
distingue os dois casos por `nao_apurado`, e não pelo total"*).

A condição é `parcelas` não-vazio, e não `nao_apurado` vazio: um processo com três dos nove insumos
apurados **entra**, com a lacuna registrada na proveniência. O que não entra é o que não tem conta
nenhuma.

### Por que `null` não é zero

A regra do `nao_apurado` de `process.py`, do `kpi_baseline` nulável e do `impact_estimate` do
`PainPoint`, aplicada ao custo do estado atual: "não apuramos" e "não custa nada" são conclusões
opostas. Zero afirmaria a segunda — e é a afirmação errada exatamente na tela em que alguém decide
gastar dinheiro. O que faltou sai na proveniência, que é para isso que ela existe.

O mesmo vale um degrau adiante: `investment` e `expected_return_year` são **nuláveis**, porque o
business case se escreve em rascunho e um zero ali seria um investimento que ninguém orçou. Quem
cobra os dois é a action `decide/`.

### Por que aprovar exige os dois números e rejeitar não

A assimetria é a regra, não uma frouxidão. **Aprovar** sem saber quanto se investe e quanto se espera
de volta é precisamente a decisão que a exigência existe para impedir. **Rejeitar** sem os números é
como a maior parte das recusas acontece: recusa-se o que não fechou conta, ou o que nem chegou a ser
orçado.

Cobrá-los na rejeição obrigaria alguém a inventar dois valores para registrar que **não** vai
investir — e dado inventado para satisfazer validação é pior que campo vazio, porque depois ninguém
distingue um do outro. Vale a mesma regra do `nao_apurado`, um degrau acima.

### Por que a decisão é action, e não `PATCH`

O motivo de `journey.apply_gate` (ADR 0053) e de `prove.start` (FDD 049): **o que vale depende do
estado corrente**. Se já houve decisão, se os dois números existem, se outra aprovação viva já ocupa
esta oportunidade — nenhuma dessas perguntas cabe num serializer que só vê o corpo. Um `PATCH`
gravaria `approved` sem fazê-las, e a invariante viraria sugestão. É também o motivo de o trio
`status`/`decided_at`/`decided_by` ser read-only, como o trio do consentimento do `Case`.

As quatro recusas usam o status que cada uma merece: **400** (`InvalidInput`) quando o pedido está
malfeito — `outcome` fora do vocabulário, número faltando —, e **409** (`StateConflict`) quando o
corpo está bom e o que impede é o estado — já decidido, ou já existe aprovado vivo.

### Por que a unicidade do aprovado é checada também na action

A garantia é a `UniqueConstraint`; a checagem existe para a recusa ser legível. É a exceção que a
FDD 048 já documentou para `SolutionHypothesis`: o DRF só deriva o validador de uma constraint
condicional quando **todos** os campos da condição são campos do serializer, e a condição cita
`archived_at`, que nenhum serializer da casa expõe. Sem a checagem, o `IntegrityError` subiria como
500. Aqui ela devolve **409** e não o 400 daquela, porque o corpo (`{"outcome": "approved"}`) está
perfeitamente correto — o que impede é o estado.

Rejeitados não concorrem: recusar é resultado normal e repetível de várias tentativas; aprovar duas
vezes a mesma oportunidade é contradição.

### Por que o processo alcançado por duas dores conta uma vez

Agrupar dores é o que a `ImprovementOpportunity` faz — é o Opportunity Map. Duas dores no mesmo
processo são o caso comum, e somar a conta daquele processo duas vezes dobraria o número sem nada
ficar vermelho. `processos_da_oportunidade` deduplica por id e ordena por id, para a proveniência
gravada ser estável entre duas leituras: um dicionário de congelamento que muda de ordem sozinho é
um diff que ninguém consegue revisar.

### Por que ele não atravessa para o One

`language-map` §3: investimento e retorno esperado são internos, como preço de tabela e margem já
são. O One mostra o que o cliente pode ver — Process, Finding revisado, ImprovementOpportunity com
Opportunity Score, KPI, Baseline, Outcome —, e a justificativa do investimento fica deste lado.
`portal.py` não é tocado nesta fatia, e `BusinessCase` **não é publicável**: não recebe
`published_at`/`published_by` nem entra em `publication.py`.

### Por que ele não pende de projeto

Como os quatro da Fase 4 (FDD 048), e não como os cinco da Fase 5: a oportunidade de melhoria nasce
do levantamento, que é da **conta** e sobrevive à venda que o descobriu. Por isso `BusinessCase`
fica **fora de `PROJECT_OF`**, e a permissão de objeto resolve `obj.improvement_opportunity.account`
— um hop, o mesmo de `PriorityAssessment` e `SolutionHypothesis`. Não se confunde com o `Case`, que
está em `PROJECT_OF` porque nasce de um projeto e herda a fronteira dele.

## Testes

- `backend/apps/core/tests/test_business_case.py` — o congelamento com processo sustentado, o
  `null` com a proveniência preenchida (e a linha do processo que ficou de fora, com o
  `nao_apurado` dele), a oportunidade sem dor nenhuma, a deduplicação do processo alcançado por duas
  dores, as três formas de um processo não chegar à conta com o controle positivo ao lado, a soma de
  dois sustentados com um terceiro de hipótese fora, o corpo que não escreve os campos congelados,
  as quatro recusas da `decide` com os controles simétricos, o 409 da edição do decidido com o
  controle do rascunho, o `status` que não muda por `PATCH`, a unicidade do aprovado nas três
  condições mais o `IntegrityError` que prova que a garantia é a constraint, as duas pontas da
  invariante das FKs no serializer **e** no `clean()`, o dinheiro como texto no JSON renderizado, os
  três filtros, o arquivar/restaurar e o recorte da Entrega com controle positivo.
- `backend/tests/regression/test_o_custo_congelado_do_business_case_nao_muda.py` — o gêmeo de
  `test_case_congelado_nao_muda.py`: mexe no processo pelos caminhos que alterariam o cálculo (os
  quatro fatores, um aditivo, a sustentação arquivada e uma dor nova trazendo outro processo), tenta
  reescrever pela API, e o controle que impede o teste de passar por o cálculo estar quebrado — um
  business case criado **depois** da correção vê o número novo.

## Fora deste recorte

- **Tela.** Nenhuma. O aceite é a API, no precedente da FDD 040 (`NO_INTERFACE_CHANGE`): browser não
  é exigido enquanto nenhuma tela consumir. A superfície entra por **DAP aprovado**, porque é
  superfície nova — e o lugar natural dela é a vizinhança de `/contas/:id/priorizacao`, simétrica a
  `/contas/:id/valor`. Nada em `frontend/` foi tocado, nem os tipos: eles entram com o consumidor,
  na fatia da tela.
- **Publicação.** `BusinessCase` não é publicável, e `publication.py` não é tocado — ver a decisão
  acima. São **cinco** modelos marcados (ADR 0060) e continuam cinco.
- **O portal do cliente.** `portal.build_snapshot` não leva nada desta fatia.
- **O Next Best Opportunity.** É a fatia seguinte da ADR 0069: `recommendations.py` e a promoção do
  `prioritization` a recomendação de primeira classe.
- **O cockpit de reunião de Discovery.** A terceira peça da ADR 0069, atrás de DAP próprio.
- **Recorrência e cenários.** Um business case por decisão, sem versões concorrentes de cenário
  (otimista/pessimista) e sem valor recorrente. A ADR 0069 declara que os campos podem mudar depois
  dos primeiros Discoveries reais, e essa possibilidade é consequência aceita, não risco descoberto:
  o que muda é campo, e nenhuma peça reescreve número de outra.
- **Renomear tabela.** Não se aplica: o modelo nasce com o nome canônico, e por isso não leva
  `Meta.db_table` — esse é o instrumento de quem renomeia modelo existente (ADR 0052).
