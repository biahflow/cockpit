# ADR 0055 — A medição sai do ativo de solução, e o ativo passa a referenciá-la

**Status:** aceita
**Data:** 2026-08-29
**Depende de:** ADR 0049 (a ontologia entra pela linguagem) · ADR 0052 (o renome de classe vem
antes da Fase 6) · ADR 0053 (cada gate tem seu vocabulário) · `docs/ontology/language-map.md` §2,
§6.11, §6.12 · DAP `docs/design/dap-prove-e-valor-r1/` (decisão **C1**, aprovada em 28/08/2026)
**Implementada por:** FDD 049 · issue #69 (Fase 5 da ontologia)

## Contexto

A FDD 027 tipou o KPI para que centenas de cases fossem comparáveis entre si em vez de uma coleção
de frases. Ela acertou o problema e escolheu o lugar mais barato para a solução: cinco colunas em
`DigitalEmployee` — `kpi_label`, `kpi_unit`, `kpi_direction`, `kpi_baseline`, `kpi_current`. Na
época o ativo de solução era a única entidade que tinha um número associado, e a alternativa teria
sido inventar uma tabela sem consumidor.

Três anos de produto depois, o lugar cobra o preço. Ele é o mesmo em três formas:

1. **O KPI não sobrevive ao ativo.** Trocar o funcionário digital que atende à mesma métrica joga
   fora o "antes" — e o "antes" é a única coisa da medição que não pode ser refeita.
2. **Um PROVE mede um número só.** Um experimento honesto mede tempo *e* retrabalho, porque a
   melhora de um às custas do outro é o resultado que ninguém quer descobrir depois.
3. **"Antes" e "depois" são duas colunas.** A forma afirma que são dois fatos de naturezas
   distintas. São o mesmo fato lido em duas janelas, e a diferença não é filosófica: ela decide se
   a comparação é legítima. Duas colunas não têm como carregar a janela, a hora da leitura, a
   evidência nem a confiança — e podem ser preenchidas com métodos diferentes sem que nada denuncie.

Há uma quarta pressão, e ela vem de fora do schema. `Case` congela `metrics`/`health_snapshot`/
`roi_snapshot` na conclusão do projeto (ADR 0020) e, na prática, virou a fonte de verdade do
resultado. Não é: um case é **material comercial derivado** de dado aprovado. O dado aprovado não
existia.

## Decisão

### O KPI é entidade, e o ativo de solução passa a referenciá-lo

`KPI` e `Measurement` nascem como modelos próprios. `DigitalEmployee` ganha `kpi`
(`SET_NULL`, opcional) e **perde** `kpi_baseline` e `kpi_current`. O que ele guarda deixa de ser a
medição e passa a ser o ponteiro para qual indicador ele move.

`kpi_label`, `kpi_unit`, `kpi_direction`, `kpi_value`, `hours_saved_month` e `roi_month` **ficam**.
Os quatro primeiros alimentam o painel "Seu Time Digital" que `portal.build_snapshot` entrega ao
cliente, e mexer neles é mudar a projeção do cliente — outro gate, outro pacote.

### Baseline e outcome são o mesmo KPI em momentos diferentes

`Measurement.kind` ∈ `baseline`/`outcome`/`monitoring`, com valor, janela (`period_start`,
`period_end`), hora da leitura (`measured_at`), evidências e confiança. **No máximo uma `baseline`
viva por KPI**, por `UniqueConstraint` parcial: duas fariam a comparação com a semana passada
depender de qual delas alguém abriu — é a decisão que a ADR 0054 já tomou para a versão da
avaliação, aqui na forma condicional ao arquivamento.

**`Measurement` não tem `unit`, e a ausência é a garantia.** O que torna um baseline comparável a um
outcome é serem leituras do *mesmo* KPI, com a *mesma* unidade e o *mesmo* método (`KPI.unit`,
`KPI.definition`, `KPI.formula`) — invariante §6.11 do `language-map`. Acrescentar a unidade à
medição pareceria conveniente e destruiria exatamente isso: duas leituras poderiam divergir de
unidade e continuar sendo comparadas na tela. Se um dia a unidade mudar, o que nasce é **outro
KPI**.

**`value` nulo é "não medido", nunca zero.** É a mesma distinção que `kpi_baseline` guardava sendo
nulável, que `Process.custo_do_estado_atual` guarda com `nao_apurado` e que `PainPoint.impact_estimate`
guarda pelo mesmo motivo. Zero afirma que o processo não custava nada antes; a lacuna admitida é
sempre melhor que a lacuna disfarçada de medição.

### O valor atribuído é entidade, e ele aponta para um `Outcome`

`ValueLedgerEntry` pende do `Engagement`, aponta para uma `Measurement` **de tipo `outcome`** com
`PROTECT`, e exige `attribution_method` não-vazio. As duas exigências são as invariantes §6.11 e
§6.12, testáveis pela primeira vez:

- uma entrada apontando para um baseline afirmaria resultado onde há ponto de partida, e a leitura
  da tela não denunciaria nada — os dois são números do mesmo KPI;
- sem o método de atribuição, o que sobra é uma promessa com casas decimais. É por isso que "ROI"
  como resultado é termo banido (§5).

`PROTECT` pela razão de `Case.project`: a entrada de valor existe para sobreviver ao que acontece em
volta. `approved` exige `approved_by`, e `approved_at` é carimbado no `save()` na primeira vez que a
entrada chega lá — a forma do `published_at` do `Case`.

### `KPI.prove_experiment` é opcional, e `project` é a âncora

Isto é um **desvio deliberado** da lista de campos da issue #69, que trata o experimento como
obrigatório. A razão é a migração: os `kpi_baseline` que existem hoje pendem de `DigitalEmployee`, e
não houve PROVE nenhum. Torná-lo obrigatório forçaria o backfill a **inventar um `ProveExperiment`
que nunca aconteceu** — dado fabricado com aparência de histórico, que é pior que a lacuna. Com o
campo nulável, o KPI migrado diz a verdade: existe, pende do projeto, e não nasceu de um
experimento. "Vários KPIs por PROVE" continua valendo: é 1-N pelo `prove_experiment`.

### A escrita pelo ativo de solução acaba — e é quebra deliberada da `/api/v1/`

Se o KPI sai do `DigitalEmployee` e o formulário fica, passam a existir **dois lugares que escrevem
a mesma medição**, e a que vale é a última salva: o defeito volta pela porta da tela. É a decisão
C1 do DAP, e ela é a mais cara do pacote porque é a única que remove algo em uso.

No servidor, dois verbos param de funcionar:

- `PATCH /digital-employees/{id}/` com `kpi_baseline`/`kpi_current` — as duas chaves passam a ser
  campos derivados e só de leitura, e o corpo é aceito com 200 e ignorado. É a forma dos três
  snapshots congelados do `Case` (ADR 0020): "não há caminho de escrita, em vez de haver um caminho
  que se combina não usar";
- `POST /projects/{id}/digital-employees/from-blueprint/` com `kpi_baseline` — a chave sai do corpo
  aceito e do esquema, e `blueprints.instantiate` perde o parâmetro.

**As duas chaves continuam saindo no `GET`**, derivadas da baseline viva e do `Outcome` mais recente
do KPI referenciado. Remover a leitura seria quebra de contrato sem necessidade: a ADR 0052 já fixou
que chave de payload morre na `/api/v2/`, não antes. A quebra e o prazo estão registrados em
`docs/ontology/aliases.md`, e há regressão afirmando que a leitura sobrevive — pelo motivo que a
§2c dá para os aliases de escrita: um campo derivado sem chamador dentro do repositório é o que a
próxima varredura remove achando que paga dívida.

### O PROVE não começa sem KPI, critério e baseline

A invariante mora numa **action** (`POST /prove-experiments/{id}/start/`), e não num `PATCH` de
`status`, pela razão exata de `journey.apply_gate` (ADR 0053): a validação depende do estado
corrente — quais KPIs pendem deste experimento e quais deles já têm baseline viva —, e só o ponto
que conhece esse estado pode fazer a pergunta.

A saída existe e é **um ato assinado**: `gap_waiver` diz por quê, `gap_waiver_by` diz quem, e
`gap_waiver_at` é carimbado pela action. Sem autor não é aprovação, é um campo de texto.

O que falta sai de `prove.o_que_falta_para_iniciar`, função pura, no molde de `priority.py`. Ela
devolve **chaves, não frases**: rótulo é da superfície, e um servidor que devolvesse "Baseline" em
português congelaria a copy do board dentro do backend — o mesmo defeito que o `CLAUDE.md` proíbe em
mapa de estado. É a única expressão da regra, e o serializer a publica em `missing_to_start`, para a
tela desenhar as pastilhas a partir dela em vez de recalculá-la.

## Consequências

- **Um KPI passa a sobreviver ao ativo que o mede**, e um PROVE passa a ter quantos indicadores
  precisar. As duas coisas que a coluna impedia deixam de ser impedidas.
- **A comparação passa a ser auditável**: janela, hora da leitura, evidência e confiança viajam com
  cada medição, e o método viaja com o KPI.
- **Quem media pelo formulário passa a medir pelo PROVE.** É custo real de adoção, e foi aceito
  explicitamente no gate. Enquanto a tela não muda, o formulário envia dois campos que o servidor
  ignora — estado transitório, escrito, não esquecido.
- **A migração é o passo perigoso, e ela pode mentir de um jeito só**: transformando ausência em
  zero. Nulo não vira zero e nulo não vira medição; o ativo sem baseline sai do backfill com a
  ausência que ele tem. Há regressão que atravessa os três estados.
- **A `0067` remove as colunas no mesmo arquivo em que faz o backfill.** Uma `0068` separada abriria
  uma janela de deploy com o mesmo fato em dois lugares — exatamente a duplicação que a C1 remove.
- **O `Case` continua sendo fotografia**, e `cases._metric` só mudou de origem. O case derivado de
  `Outcome` aprovado é reservado no DAP, e não é esta ADR que o autoriza.
- **`ValueLedgerEntry` fica fora de `PROJECT_OF`**, porque o `project` dela é opcional e o
  engajamento não é fronteira de acesso (ADR 0050). A visibilidade deriva de `visible_to`, como
  tudo o mais.

## Alternativas consideradas

- **Manter as colunas e escrever `Measurement` por baixo (decisão C2 do DAP).** Mais suave para quem
  já usa a tela, e é o caminho que desfaz a fase inteira: dois lugares escrevendo a mesma medição
  fazem a fonte da verdade voltar a ser o ativo de solução, e a última escrita vence em silêncio.
- **`Measurement` com `unit` própria.** Conveniente para renderizar a linha sem carregar o KPI, e é
  a mudança que permite duas leituras divergirem de unidade e continuarem sendo comparadas.
- **`KPI.prove_experiment` obrigatório, com a migração criando um experimento sintético.** Deixa o
  modelo mais limpo e mente sobre o histórico — um PROVE que nunca aconteceu, com data e escopo
  inventados, indistinguível dos verdadeiros na primeira consulta.
- **Remover `kpi_baseline`/`kpi_current` também do `GET`.** Menos superfície e quebra de contrato
  sem necessidade: a chave de payload já tem prazo, e ele é a `/api/v2/`.
- **Duas colunas separadas para a decisão de gate da Feasibility e a do PROVE.** Seriam duas
  definições do mesmo vocabulário; a ADR 0053 já resolveu isso reusando `ProjectPhase.GateDecision`
  e `ProjectPhase.ProveDecision`, e é o que os dois modelos novos fazem.
