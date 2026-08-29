# FDD 049 — A medição morava dentro do ativo de solução

> **Feasibility, PROVE, KPI/Measurement e Value Ledger.** É a quinta fatia da ontologia (ADR 0049,
> issue #69). O KPI sai de `DigitalEmployee` e vira entidade (ADR 0055); baseline e outcome passam
> a ser **duas leituras do mesmo indicador**; o PROVE não começa sem KPI, critério e baseline — ou
> lacuna aprovada, assinada; e a entrada de valor aponta para um `Outcome` e registra o método de
> atribuição, que é o que as invariantes §6.11 e §6.12 do `language-map` sempre disseram e nada
> cobrava.

## Jornada

A escada FDE tem duas perguntas depois de *"onde atuar?"*: **"a tecnologia consegue fazer a
tarefa?"** (Feasibility) e **"funcionou em produção controlada?"** (PROVE). As duas já tinham fase
(`JourneyPhase.canonical_stage`) e já tinham decisão (`ProjectPhase.gate_decision`, com os dois
vocabulários da ADR 0053). O que não tinham era **o conteúdo da decisão** — e um `GO` gravado sem
amostra, sem classes de erro e sem os três vereditos é uma decisão sem laudo: seis meses depois
ninguém diz o que foi testado nem o que ficou de ressalva.

O defeito maior estava um passo à frente, e era estrutural.

**O ativo de solução era dono da verdade da medição.** `kpi_label`, `kpi_unit`, `kpi_direction`,
`kpi_baseline` e `kpi_current` eram colunas de `DigitalEmployee` (FDD 027). Três consequências
saíam daí:

- **um KPI não sobrevivia à troca do ativo que o mede.** Trocar o funcionário digital que atende à
  mesma métrica jogava fora o "antes";
- **um PROVE não podia ter mais de um KPI.** Um experimento mede tempo *e* retrabalho, e o modelo
  cabia um número;
- **"antes" e "depois" eram duas colunas**, afirmando serem dois fatos de naturezas distintas. São
  o mesmo fato lido em duas janelas — e é essa a frase central desta fatia.

**E valor gerado não tinha onde morar.** O `Case` congela `metrics`/`health_snapshot`/`roi_snapshot`
na conclusão do projeto (FDD 027, ADR 0020) e, na prática, virava a fonte de verdade do resultado.
Não é: um case é **material comercial derivado** de dado aprovado. O que faltava era o dado
aprovado — uma entrada que aponte para uma medição de resultado, diga o método pelo qual aquele
número foi atribuído ao trabalho, e passe por aprovação com autor.

## O que esta fatia entrega

**Cinco entidades, e a divisão de trabalho entre elas é a fatia inteira.**

- **`FeasibilityAssessment`** — o laudo: três eixos (`technical`, `operational`, `economic`), cada
  um com veredito (`favorable`/`caveat`/`unfavorable`) e nota; a amostra; as classes de erro; as
  `Evidence` que o sustentam; e a decisão de gate no vocabulário da Feasibility.
- **`ProveExperiment`** — o experimento: escopo controlado, datas, critério de sucesso **prévio**,
  estado, a decisão de gate no vocabulário do PROVE, e o trio da lacuna aprovada.
- **`KPI`** — o indicador, com nome, definição, fórmula, unidade, direção, fonte, cadência, dono e
  meta. Pende do **projeto**; o experimento é opcional.
- **`Measurement`** — a leitura: `kind` ∈ `baseline`/`outcome`/`monitoring`, valor, janela, hora da
  medição, evidências e confiança.
- **`ValueLedgerEntry`** — o valor atribuído: aponta para uma medição de resultado, tem tipo,
  montante, janela, **método de atribuição** e um estado que termina em aprovado com autor.

**Quatro invariantes com dente:**

1. **O PROVE não começa sem KPI, critério de sucesso e baseline** — ou com lacuna aprovada
   explicitamente. Mora na action `POST /prove-experiments/{id}/start/`, e a lógica de "o que
   falta" mora numa função pura, `prove.o_que_falta_para_iniciar`.
2. **No máximo uma `baseline` viva por KPI.** `UniqueConstraint` parcial sobre
   `kind="baseline"` e `archived_at IS NULL`, no molde de `unique_chosen_solution_hypothesis`.
3. **A entrada de valor aponta para um `Outcome`, e registra método de atribuição.** As duas metades
   da §6.12, no `clean()` do modelo e no serializer.
4. **`approved` exige `approved_by`**, e `approved_at` é carimbado no `save()` na primeira vez que
   a entrada chega lá — a forma do `published_at` do `Case`.

**E `value` nulo é "não medido", nunca zero.** É a mesma distinção de `PainPoint.impact_estimate`,
do `nao_apurado` de `process.custo_do_estado_atual` e do próprio `kpi_baseline` que esta fatia
substitui. Zero afirma que o processo não custava nada antes; a lacuna admitida é sempre melhor que
a lacuna disfarçada de medição.

## Critérios de aceite

- Iniciar um PROVE sem KPI, sem critério ou sem baseline é **400 dizendo qual dos três falta** — e
  não só que falta algo.
- Um KPI sem baseline **entre vários** já impede o início: a comparação é por KPI.
- Baseline **arquivada** não conta como baseline.
- `gap_waiver` preenchido sem `gap_waiver_by` é 400; com autor, o início passa e `gap_waiver_at` é
  carimbado.
- Iniciar duas vezes é **409**; `PATCH` com `status=running` é **400** apontando a action.
- Duas `baseline` vivas no mesmo KPI são recusadas; arquivar a primeira libera a segunda. Vários
  `outcome` no mesmo KPI são o estado normal.
- `Measurement.value` ausente fica **nulo** e nunca vira zero; zero informado é preservado.
- `ValueLedgerEntry` apontando para `kind=baseline` é recusada; sem `attribution_method` também;
  `approved` sem `approved_by` também.
- Apagar a medição que sustenta uma entrada levanta `ProtectedError` — traduzido em 409 pela rede
  do `api_exception_handler`. **Arquivá-la** também é 409, e é esse o caminho que a API percorre.
- Arquivar um KPI leva as medições dele junto, na mesma transação; e é 409 quando alguma delas
  sustenta uma entrada de valor viva.
- O `gate_decision` do PROVE aceita `SCALE`/`ITERATE`/`STOP` e recusa `GO`; o da Feasibility, o
  contrário.
- `kpi_baseline` e `kpi_current` **continuam saindo** no `GET` de `/digital-employees/`, com o valor
  da medição correspondente, e `null` quando não há.
- Entrega não lê nem escreve os cinco fora dos projetos dela, e a entrada de valor **sem projeto** é
  visível para quem alcança algum projeto daquele mandato.
- A migração `0067` atravessa três estados de ativo (com os dois números, só com baseline, sem
  nenhum) preservando exatamente o que havia — e o terceiro **não ganha medição nenhuma**.

## Contrato

Rotas novas em `/api/v1/`, todas com `?archived=1` e `POST /unarchive/`:

| Rota | Âncora do recorte | Filtros |
| --- | --- | --- |
| `/feasibility-assessments/` | projeto | `?project=`, `?solution_hypothesis=`, `?gate_decision=` |
| `/prove-experiments/` (+ `POST /{id}/start/`) | projeto | `?project=`, `?solution_hypothesis=`, `?status=`, `?gate_decision=` |
| `/kpis/` | projeto | `?project=`, `?prove_experiment=`, `?unit=`, `?direction=` |
| `/measurements/` | projeto do KPI | `?kpi=`, `?kind=` |
| `/value-ledger-entries/` | projeto, ou mandato quando não houver | `?engagement=`, `?project=`, `?outcome_measurement=`, `?status=`, `?value_type=` |

**Nomes canônicos e nenhum alias** — alias existe para não quebrar chave que a `/api/v1/` já
prometeu, e aqui não há chave antiga nenhuma.

`ProveExperimentSerializer` publica `missing_to_start`, derivado e só de leitura: é a mesma lista
que a action usa para recusar, e é dela que a tela desenha as três pastilhas `Pronto`/`Falta`.

**Vendas lê os cinco e não escreve nenhum**, ao lado de `digital_employee` e `case` e pelo mesmo
argumento: o laudo, o experimento, o KPI, a medição e a entrada de valor são produzidos por quem
executa o trabalho; o comercial lê o que a casa provou e não escreve a medição que sustenta a
afirmação. **Entrega escreve os cinco**, dentro do recorte dela.

### A quebra deliberada da `/api/v1/`

A decisão **C1** do DAP `docs/design/dap-prove-e-valor-r1/` (aprovada em 28/08/2026) tira os campos
"Antes (base)" e "Depois (atual)" do formulário do Time Digital. No backend isso significa que
**dois verbos pararam de funcionar**, e os dois estão registrados em
[`docs/ontology/aliases.md`](../ontology/aliases.md):

- **`PATCH /digital-employees/{id}/` com `kpi_baseline` ou `kpi_current`** — as duas chaves passaram
  a ser campos derivados e só de leitura. O corpo é aceito com 200 e ignorado, na forma dos três
  snapshots congelados do `Case`.

  **Ignorar e não recusar com 400 foi decisão, e o precedente do `Case` é a razão fraca dela.** A
  razão forte é que as duas chaves **continuam sendo lidas**: ler-modificar-escrever é o padrão
  normal de quem consome a `/api/v1/`, e um cliente que faz `GET`, muda o `name` e devolve o corpo
  inteiro está apenas ecoando o que acabou de receber. Um 400 puniria o cliente bem-comportado
  justamente pelo contrato que o serializer mantém de pé — e só seria honesto se a leitura também
  tivesse morrido, o que acontece na `/api/v2/`, junto com a chave.

  O preço fica declarado: quem hoje **escreve** medição por aqui deixa de escrever e recebe 200, o
  que é perda silenciosa. É por isso que a fatia da tela sai no mesmo PR — a SPA é o único escritor
  conhecido, e ela para de mandar os campos no mesmo commit em que eles param de ser aceitos. Um
  escritor externo desconhecido é risco residual, e está aqui escrito em vez de descoberto depois.
- **`POST /projects/{id}/digital-employees/from-blueprint/` com `kpi_baseline`** — a chave saiu do
  corpo aceito e do esquema. `blueprints.instantiate` perdeu o parâmetro.

**As chaves continuam saindo no `GET`**, agora derivadas das `Measurement` do KPI referenciado: a
baseline viva e o `Outcome` mais recente. Remover a leitura seria quebra de contrato, e a ADR 0052
já fixou que chave de payload morre na `/api/v2/`, não antes. Há regressão afirmando isso
(`tests/regression/test_a_medicao_do_ativo_sobrevive_na_v1.py`) pelo motivo que a `aliases.md` §2c
dá para os aliases de escrita: sem ela, as duas linhas do serializer não têm chamador **dentro** do
repositório, e a próxima varredura atrás de campo morto as remove achando que paga dívida.

## Decisões

### `KPI.prove_experiment` é opcional — desvio deliberado da issue

A issue #69 lista `KPI.prove_experiment` entre os campos mínimos como se fosse obrigatório. **Ele
nasce nulável, com `project` como âncora obrigatória**, e a razão é a migração: os `kpi_baseline`
que existem hoje pendem de `DigitalEmployee`, e não houve PROVE nenhum. Torná-lo obrigatório
forçaria a `0067` a **inventar um `ProveExperiment` que nunca aconteceu** — dado fabricado com
aparência de histórico, que é pior que a lacuna. Com o campo nulável, o KPI migrado diz a verdade:
existe, pende do projeto, e não nasceu de um experimento.

"Suportar vários KPIs por PROVE", que é o critério de aceite da issue, continua valendo: é 1-N pelo
`prove_experiment`.

### A invariante de início mora numa action, não num `PATCH`

Pela razão exata de `journey.apply_gate` (ADR 0053): a validação depende do **estado corrente** —
quais KPIs pendem deste experimento e quais deles já têm baseline viva —, e só o ponto que conhece
esse estado pode fazer a pergunta. Um `PATCH` de `status` gravaria `running` sem ela, e a invariante
viraria sugestão. É por isso que `ProveExperimentSerializer.validate_status` **recusa** `running`
apontando a action: sem essa recusa, a invariante vaza pela porta do formulário, que é a mesma
porta pela qual a decisão C1 tira a medição do ativo.

A recusa por falta de requisito é **400** (`InvalidInput`) e a de "já iniciado" é **409**
(`StateConflict`), pela distinção que os dois nomes carregam: lá o estado é que muda para o pedido
passar, aqui é o pedido de iniciar *agora* que não cabe.

**Lacuna aprovada é ato assinado.** `gap_waiver` sem `gap_waiver_by` é 400, e a regra vale mesmo
quando não falta nada: um waiver gravado sem autor é uma afirmação de ninguém. `gap_waiver_by` vem
do corpo e não da sessão, pelo motivo do `reviewed_by` do `Finding` — ele responde "quem aprovou",
que pode não ser quem digita.

### `o_que_falta_para_iniciar` devolve chaves, não frases

Rótulo é da superfície. Um servidor que devolvesse "Baseline" em português congelaria a copy do
board dentro do backend, que é o mesmo defeito que o `CLAUDE.md` proíbe em mapa de estado ("devolve
variante, nunca a cor"). Os rótulos ficam em `prove.ROTULOS`, para a mensagem de erro da API ter
texto legível sem a tela depender dele.

A função é a **única** expressão da regra, e é ela que o serializer publica em `missing_to_start`.
Duas expressões divergiriam, e a tela habilitaria o botão que o servidor nega.

### `Measurement` não tem `unit`, e a ausência é a garantia

O que torna um baseline comparável a um outcome é serem leituras do *mesmo* KPI, com a *mesma*
unidade e o *mesmo* método (`KPI.unit`, `KPI.definition`, `KPI.formula`) — invariante §6.11.
Acrescentar `unit` à medição pareceria conveniente e destruiria exatamente isso: duas leituras
poderiam divergir de unidade e continuar sendo comparadas na tela, sem nada ficar vermelho. Se um
dia a unidade mudar, o que nasce é **outro KPI**, não outra medição. Há teste sobre o `_meta` do
modelo, porque um campo acrescentado por distração não seria pego por mais nada.

### O arquivamento não deixa órfão, e as duas saídas da regra aparecem lado a lado

`Measurement` e `ValueLedgerEntry` são listadas por conta própria, então arquivar o pai sem olhar
deixaria linhas visíveis apontando para uma linha que a interface esconde — o defeito que a FDD 025
chama de órfão visível. O `CLAUDE.md` dá duas saídas legítimas, e cada uma cabe num lugar:

- **`MeasurementViewSet.perform_destroy` recusa com 409** quando uma entrada de valor viva aponta
  para ela. O `PROTECT` do modelo impede o apagamento **real** e o `api_exception_handler` o traduz,
  mas a API não apaga — ela arquiva —, e sem esta guarda o `PROTECT` nunca seria alcançado. É o
  argumento do último achado de uma dor confirmada (FDD 048), com dinheiro em cima: a entrada
  continuaria de pé sustentando um número que a casa afirma ao cliente.
- **`KPIViewSet.perform_destroy` arquiva as medições junto**, na mesma transação, no caso normal —
  uma leitura não tem vida fora do indicador que a define —, e **recusa com 409** quando alguma
  delas sustenta uma entrada viva.

`ProveExperiment` **não** ganha guarda: os KPIs dele continuam listáveis pelo `project`, que é a
âncora obrigatória, e por isso não ficam órfãos quando o experimento é arquivado.

### `ValueLedgerEntry` fica fora de `PROJECT_OF`

Os outros quatro entram: laudo, experimento e KPI pendem de projeto, e a medição chega pelo KPI —
um hop, como a etapa chega pelo processo. A entrada de valor **não**, e não por esquecimento: ela
pende de `Engagement` e o `project` dela é opcional. Um mapa que resolvesse `obj.project`
devolveria `None` para a entrada de mandato sem projeto, e a Entrega tomaria 403 no detalhe de uma
linha que a listagem dela mostra — o defeito que a `Satisfacao` já previu.

O recorte é o inverso, e é o mesmo de `EngagementViewSet`: a pessoa vê a entrada do projeto que ela
alcança; e a entrada **sem** projeto, quando alcança algum projeto daquele mandato. **O engajamento
continua não sendo fronteira de acesso** (ADR 0050): a visibilidade *deriva* de
`Project.objects.visible_to`, nunca o contrário.

### A ordem da migração, e por que as duas metades ficam no mesmo arquivo

`0066` cria os cinco modelos e o `DigitalEmployee.kpi`, **mantendo** as colunas de pé — é delas que
o backfill lê. `0067` faz o `RunPython` e **então** remove as duas colunas, no mesmo arquivo.

A ordem seria respeitada também com uma `0068` separada. O que a separação abriria é uma **janela
de deploy** em que a `0067` rodou e a `0068` não: o mesmo fato gravado em dois lugares, com a última
escrita vencendo — precisamente a duplicação que a decisão C1 existe para remover. Juntos, o par não
tem esse estado intermediário.

A reversa se compõe sozinha e na ordem certa: o Django desfaz as operações de trás para a frente,
então os dois `RemoveField` voltam a criar as colunas **antes** de `desfaz_backfill` ter de escrever
nelas.

**Três aproximações declaradas**, porque nenhuma está no dado de origem: nulo não vira zero nem
medição; a janela e a hora da leitura são aproximadas por `created_at` (o baseline, pedido na
instanciação) e `updated_at` (o atual, editado depois); e arquivados vêm junto com o carimbo. A
marca de que a data veio da migração é o KPI **sem** `prove_experiment`.

O recorte da reversa é pelo ponteiro, como a `0054` faz com `legacy_evidencia`: um KPI apontado por
um ativo **e sem experimento** é a assinatura desta migração. A imprecisão residual está declarada —
um KPI escrito à mão depois, sem experimento e ligado a um ativo, é indistinguível —, e é o preço de
não criar uma coluna `legacy_` só para a reversa. A reversa **recusa** quando uma `ValueLedgerEntry`
já pende da medição, e recusar é o certo: desfazer schema não pode apagar valor atribuído.

### Os dois vocabulários são reusados, nunca redefinidos

`FeasibilityAssessment.gate_decision` usa `ProjectPhase.GateDecision.choices` e
`ProveExperiment.gate_decision` usa `ProjectPhase.ProveDecision.choices`. Duas definições do mesmo
vocabulário divergem em silêncio, e a ADR 0053 já pagou esse preço uma vez — quando
`kickoff.KICKOFF_TEMPLATES["prove"]` mandava registrar `SCALE` numa fase que só aceitava `GO`.

Aqui, ao contrário de `journey.apply_gate`, **não há validação à mão**: em cada modelo não existe
ambiguidade sobre de que gate se trata, então a `ChoiceField` derivada do campo já recusa o valor
do outro vocabulário com 400. É lá que a validação precisa ser escrita, porque lá o vocabulário
depende da fase ativa.

### `cases._metric` muda de origem, e não de forma

O formato de `Case.metrics` é o mesmo — `CasesPage` e `ai._case_lines` leem aquele JSON e não foram
tocados —, e `has_baseline` continua significando o que significava. O que mudou é de onde os dois
números saem: `prove.baseline_de` e `prove.outcome_mais_recente_de`, um lugar só, consumido também
pelo `DigitalEmployeeSerializer`. Duas expressões de "qual é o antes deste ativo" divergiriam na
primeira correção.

As duas funções leem com `.all()` e filtram em Python, no molde de
`ImprovementOpportunity.current_assessment`: um `.filter()` emitiria consulta nova e **ignoraria** o
`prefetch_related("kpi__measurements")` de quem chamou — custo de N+1 com aparência de custo
resolvido.

## Testes

- `apps/core/tests/test_prove_e_valor.py` — a invariante de início nas cinco recusas e nos dois
  controles positivos (incluindo o KPI sem baseline **entre vários** e a baseline arquivada), a
  lacuna com e sem autor, o 409 do segundo início, o 400 do `PATCH` de status, `missing_to_start`
  nos dois extremos, os dois vocabulários de gate aceitando e recusando um ao outro, a fronteira de
  conta do laudo na rota **e** no modelo, o KPI sem experimento e o 1-N, o nulo≠zero da medição nas
  duas direções, a unicidade da baseline com o controle do arquivamento, a ausência de `unit` no
  `_meta`, as três recusas do ledger, o carimbo de aprovação que não se reescreve, o `PROTECT` e as
  três guardas de órfão do arquivamento, o par derivado que a `/api/v1/` publica, e o recorte da
  Entrega nos cinco recursos com controle positivo em cada um.
- `tests/regression/test_backfill_do_kpi_preserva_a_medicao.py` — o esquema volta para a `0066` e os
  dados nascem pelos modelos daquele estado, no molde de `test_engagement_backfill.py`: os três
  estados de ativo, o zero que atravessa como zero, o nome derivado, a aproximação da janela, o
  arquivado, a idempotência, o `updated_at` que não é reescrito, e as três metades da reversa.
- `tests/regression/test_a_medicao_do_ativo_sobrevive_na_v1.py` — as duas chaves continuam saindo,
  com o valor da medição, com `null` na lacuna, sem a medição arquivada, e acompanhando o KPI e não
  o ativo.

## Fora deste recorte

- **Tela.** Nenhuma nesta fatia. A superfície tem DAP aprovado
  (`docs/design/dap-prove-e-valor-r1/`, decisões **A1 · B1 · C1 · D1 · E1**) e vem na seguinte; no
  recorte do backend entraram só os tipos em `frontend/src/types.ts`, sem consumidor, como a Fase 3
  e a Fase 4 fizeram.
- **A remoção dos dois campos do formulário do Time Digital.** A decisão C1 está paga no
  **servidor** — a escrita deixou de ter efeito —, e a remoção dos `<input>` de
  `ProjectDetailPage.tsx` é da fatia da tela. Enquanto isso, o formulário envia dois campos que o
  servidor ignora: é um estado transitório e escrito, não um esquecimento.
- **`Case` derivado de Outcomes aprovados.** O DAP o marcou como **reservado**: `cases.freeze`
  continua congelando como hoje, só lendo de outro lugar.
- **O One.** `portal.build_snapshot` não muda, e `kpi_value`, `kpi_label`, `kpi_unit`,
  `kpi_direction`, `hours_saved_month` e `roi_month` ficam onde estão. Mexer ali é mudar a projeção
  do cliente — outro gate, outro pacote.
- **Gráfico de série do KPI** e **Value Ledger consolidado entre contas** — reservados no DAP.
- **Aprovar valor como ato de admin.** Hoje a Entrega escreve `status=approved` informando
  `approved_by`, dentro do recorte dela. A assimetria que `case.record-consent` e `invoice.settle`
  usam — o ato de afirmar dinheiro é de admin, e passa por uma action com autor de sessão — é o
  passo seguinte natural, e não está nesta fatia.
- Nada de Fase 6: nem `Evidencia`, nem dual-write, nem `db_table`, nem `Project.client`.
- **Renomear tabela.** Não se aplica: os cinco nascem com o nome canônico, e por isso nenhum leva
  `Meta.db_table` — esse é o instrumento de quem renomeia modelo existente (ADR 0052).
