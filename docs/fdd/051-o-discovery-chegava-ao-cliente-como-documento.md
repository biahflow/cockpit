# FDD 051 — O Discovery chegava ao cliente como documento

> **`Process`, `Finding`, `PainPoint` e `ImprovementOpportunity` passam a atravessar para o One,
> atrás de uma marca de publicável.** Entram `processes[]`, `findings[]`, `pain_points[]` e
> `improvement_opportunities[]` na raiz do snapshot. **Cinco** modelos ganham
> `published_at`/`published_by` (migração `0075`, sem backfill), dez actions `publish/`
> `unpublish/`, uma invariante de cadeia com cinco portas e oito emissores novos. **Nada
> atravessa sem a marca, o AS-IS inclusive.** Contrato `/api/v1/` preservado: tudo aditivo.

## Jornada

A Fase 3 da ontologia (ADR 0049, FDD 045) desfez a `Evidencia` fundida no par `Evidence`/`Finding`;
a Fase 4 (ADR 0054, FDD 048) deu ao PRIORITIZE a cadeia `PainPoint` → `ImprovementOpportunity` →
`PriorityAssessment` → `SolutionHypothesis`. Onze modelos, nome canônico, invariantes cobradas.

**Nenhum atravessava.** `portal.build_snapshot` não tinha uma chave sequer do levantamento, e
`signals.py` não tinha um receiver para nenhum dos onze. O Discovery chegava ao cliente do jeito que
sempre chegou: um documento — o `Artifact` de `kind=discovery`, a narrativa entregue no readout.

A §3 do `docs/ontology/language-map.md`, por outro lado, já dizia o contrário desde antes:

| No One | Nunca no One |
| --- | --- |
| Process · ProcessStep (o AS-IS validado) | … |
| Finding · PainPoint (revisados) | Evidence não revisada, transcrição bruta |
| ImprovementOpportunity + Opportunity Score | `PriorityAssessment.rationale` interno |

O documento estava certo e o schema atrás dele. E o que se perdia não é conveniência: **é o que
separa o One de um Drive compartilhado**. Um PDF de Discovery é lido uma vez; um mapa navegável é
onde o cliente volta para conferir de onde veio a afirmação, ver a lacuna declarada e acompanhar o
backlog priorizado mudar. O outro lado (`biahflow/one#90`) pediu exatamente isso.

Duas coisas travavam a fatia, e as duas eram decisões, não trabalho.

## As duas decisões

### (a) O Discovery é da conta; o snapshot é do projeto

`Process`, `Evidence`, `Finding`, `PainPoint` e `ImprovementOpportunity` pendem da `Account` — e
pendem de propósito, desde a FDD 039: *o que se levantou sobre a operação de uma empresa sobrevive à
venda que o descobriu*. O snapshot, por outro lado, é por projeto.

**Decisão: o Discovery da conta vai em todo snapshot de projeto dela.** O mesmo payload sai
duplicado por projeto e o One deduplica por id, que ele já sabe fazer. As duas alternativas foram
recusadas com motivo:

- **uma rota de escopo Account** seria um segundo canal de ingestão do lado de lá — a única coisa
  desta fatia que não seria aditiva, e a que obrigaria o One a mudar antes de poder ler;
- **recortar pelo projeto que descobriu** perderia exatamente a propriedade que motivou a FK de
  conta, e reintroduziria o defeito que o `DigitalEmployee` tinha antes da FDD 026 — o que vale
  morando só na instância.

A consequência é o fan-out dos emissores, no molde literal do `_emit_engagement`.

### (b) A marca de publicável não existia — e a §3 promete que existe

Levantamento confirmado no schema: `Evidence` **não tinha** nenhum campo de revisão ou
publicabilidade; `Process`/`ProcessStep` **também não tinham nada que dissesse "validado"**;
`Finding` tem `reviewed_by`/`reviewed_at`, mas eles só são obrigatórios para
`fact` — e `hypothesis`, que é o default e o que a extração por IA produz, nasce sem revisor nenhum.
A regra 1 da §3 ("nada aparece no One antes de ser revisado por humano") não tinha onde se apoiar,
e os **dois** qualificadores da tabela ao lado dela pressupunham estados que o banco não sabia
afirmar.

**Decisão: marca própria em cinco modelos — `Process`, `Evidence`, `Finding`, `PainPoint` e
`ImprovementOpportunity` — mais uma invariante de cadeia.** As perguntas são diferentes:
`epistemic_status` responde *"quão certos estamos disso"*, a marca responde *"o cliente pode ver
isso"*. Elas se cruzam nos quatro sentidos: um achado pode ser `hypothesis` e perfeitamente
publicável — é o que se leva à reunião —, e pode ser `fact` e interno.

Por que os **cinco** e não os dois que a issue propôs: `PainPoint.status=confirmed` e
`ImprovementOpportunity.status=prioritized` são estados de **fluxo**, não de visibilidade. Reusar
qualquer um dos dois esconderia a decisão de mostrar dentro de um campo que significa outra coisa —
o mesmo defeito de reusar o `reviewed_at` do fato.

**O ato de publicar É a revisão humana que a regra 1 exige**, e é por isso que `published_by` é
obrigatório: é a pessoa que leu. É isso que torna aceitável um `Finding` em `hypothesis` atravessar
rotulado como hipótese — ele atravessa porque alguém o leu e o publicou, não porque a IA o extraiu.

**O AS-IS entra na mesma regra, e não é exceção.** A primeira redação desta fatia o deixou
atravessar sem marca, apoiada em a tabela da §3 qualificar com "(revisados)" exatamente
`Finding · PainPoint` e chamar o mapa de `Process · ProcessStep (o AS-IS validado)` — o entregável
desenhado *com* o cliente, que ele conferiu em vez de descobrir num painel.

O argumento não se sustenta, e a revisão o derrubou: **"validado" é um qualificador tão sem lastro
no schema quanto "revisada e publicável"**. Nenhum campo dizia que aquele mapa tinha sido conferido
com alguém; "desenhado com o cliente" é a intenção do artefato, não um fato consultável, e um mapa
levantado numa entrevista e nunca apresentado é indistinguível de um conferido linha a linha. A §3
pressupunha dois estados que o schema não tinha, e esta fatia move o schema para os **dois**.

E o que atravessaria não é neutro: `ProcessStep.erro` e `.retrabalho` são a caracterização da casa
sobre onde o time do cliente erra e o que acontece quando erra — *"Pedido faturado com preço
desatualizado"*, *"Nota cancelada e reemitida no dia seguinte"*. É o mesmo tipo de material que a
coluna *Nunca no One* protege em `Evidence` não revisada.

**`ProcessStep` não recebe marca própria**: ele anda com o processo pai, porque as seis letras do
P-S-D-T-E-R são um formulário só e "meio mapa publicado" não é estado que alguém queira. O custo
aceito é um ato de publicação a mais — **um por processo**, não um por etapa.

## O que esta fatia entrega

### 1. A marca (migração `0075`)

```python
published_at = models.DateTimeField(null=True, blank=True)
published_by = models.ForeignKey(User, on_delete=SET_NULL, null=True, blank=True, ...)
```

Nos cinco, com `related_name` distinto. **Os dois ou nenhum**, cobrado em
`models.valida_marca_de_publicavel` — um lugar só, chamado pelos cinco `clean()`, e o do `Process`
nasceu para isto. É a forma do par
`gap_waiver`/`gap_waiver_by` do `ProveExperiment` e do `status=approved`/`approved_by` do
`ValueLedgerEntry`: publicar é ato com autor, e sem nome "alguém revisou" é alegação de ninguém.

Nos serializers os dois campos são **só de leitura**. Quem escreve é a action, pela razão de
`journey.apply_gate` e de `POST /prove-experiments/{id}/start/`: o que vale depende do estado
corrente, e um `PATCH` publicaria sem passar pela pergunta.

**Sem backfill, e a ausência é a decisão.** Nada nasce publicado. O schema não pode decidir
retroativamente que uma afirmação sobre a operação de um cliente pode ser mostrada a ele — marcar o
que já existe por `epistemic_status=fact` ou por `status=confirmed` fabricaria a revisão humana que
a marca existe para registrar.

### 2. As dez actions e a invariante de cadeia

`POST publish/` e `POST unpublish/` nos cinco viewsets, vindas de um `PublicationMixin` só.
**Nenhuma regra nova de papel**: os cinco `resource` já estão nos conjuntos de Vendas e de Entrega
em `permissions.py`, e o corte por objeto (a conta no escopo) já existe nos viewsets.

A escada, mais a âncora lateral:

```
Evidence  →  Finding (fact)  →  PainPoint  →  ImprovementOpportunity
                  ↑                  ↑
                  └──── Process ─────┘
```

| Publicar | Exige |
| --- | --- |
| `Process` | nada — é a raiz do próprio ramo, e as etapas andam com ele |
| `Evidence` | nada — é a folha da cadeia |
| `Finding` | se `epistemic_status == fact`, ao menos uma `Evidence` publicada e viva; **e** o `Process` que ele cita publicado e vivo, se citar algum |
| `PainPoint` | ao menos um `Finding` publicado e vivo; **e** o `Process` que ela cita, idem |
| `ImprovementOpportunity` | ao menos um `PainPoint` publicado e vivo |

O que o cliente vê tem que ter sustentação publicada embaixo; senão a lista de ids do payload aponta
para o que não atravessou, e ele lê afirmação sem nada atrás. Falta de sustentação é **400** via
`InvalidInput`, listando o que falta; já publicado é **409** via `StateConflict`.

**A âncora não é degrau, e é por isso que ela aparece de lado no desenho.** O processo não
*sustenta* o achado — ele o localiza. Mas `findings[].process_id` e `pain_points[].process_id`
atravessam, e um achado publicado que cite um mapa fora de `processes[]` é referência pendurada:
o mesmo defeito que `finding_ids`/`pain_point_ids` filtrados evitam do outro lado. A citação conta
por `process` **e** por `step` — os dois FKs atravessam, os dois são `SET_NULL` e independentes, e
olhar só um deixaria a referência pendurada pelo outro. Diferente dos degraus, ela não pergunta
pela *última*: um achado cita **um** mapa, e não há segunda âncora que o salve.

Quem responde "o que falta" é `apps/core/publication.py`, função pura no molde de
`prove.o_que_falta_para_iniciar` e de `priority.py`, devolvendo **chaves e nunca frases** — rótulo é
da superfície, e este repositório já tomou essa decisão duas vezes.

### 3. As cinco portas por onde a cadeia vazaria

A invariante é fácil de afirmar e tem cinco portas. Quatro não existiam como código, e **nenhuma
delas deixaria nada vermelho**:

1. **`publish/`** — a porta óbvia, e a única que a issue pediu.
2. **`unpublish/`** — a metade que sempre vaza. Publicar confere a cadeia no instante em que o item
   sobe; despublicar a desfaz depois, item a item. **409** quando o objeto é a última sustentação
   publicada e viva de algo publicado — ou, no caso do `Process`, quando qualquer achado ou dor
   publicado o cita —, com a mensagem dizendo qual estado impede e como sair dele: despublique o de
   cima primeiro. Recusar, e nunca despublicar o de cima em silêncio: é o argumento das duas
   guardas de arquivamento que já existiam (FDD 045, FDD 048).
3. **`DELETE` (arquivar)** — arquivar some da projeção exatamente como despublicar. A dimensão da
   publicação entra **em cima** das guardas de `Evidence` e `Finding`, sem removê-las (uma pergunta
   se sobra evidência viva para o fato, a outra se sobra evidência publicada para o fato
   publicado), e as guardas de `PainPoint` e `Process` nasceram aqui — nada dependia delas dentro
   de casa. No `Process` a **ordem** é o cuidado: `archive()` cascateia para as etapas no mesmo
   instante (FDD 039), então a guarda vem antes dele.
4. **`PATCH` promovendo a `fact`** — um achado publicado como hipótese não exige nada; promovido
   depois, passaria a dizer "fato" com evidência interna embaixo. `FindingSerializer.validate`
   ganhou a terceira metade da invariante §6.9.
5. **`PATCH` movendo a âncora por baixo de um registro publicado** — trocar `process`/`step` num
   `Finding` ou `PainPoint` **já publicado** para um mapa não publicado. **400**, nomeando o campo.
   É a porta que menos parece porta, e é por isso que ela é uma: as quatro anteriores olham a
   **marca** — publicam, despublicam, arquivam ou mudam o que a marca exige —, e esta não toca em
   `published_at` nenhum. O efeito, porém, é idêntico: `findings[].process_id` (ou `step_id`) passa
   a apontar para fora de `processes[]`, que é a referência pendurada que a âncora existe para
   impedir. Vale só para o registro publicado — mover a âncora de um achado interno é edição normal
   do levantamento —, e a pergunta é feita por `publication.falta_a_ancora` sobre o valor
   **resolvido** que chegou no corpo, e não reexpressa nos serializers.

### 4. As quatro chaves do snapshot

Todas de escopo conta, alcançada por `project.engagement.account_id`, com ordem estável, e as
quatro filtradas a `published_at__isnull=False, archived_at__isnull=True` — **sem exceção**.

```
processes[]                  = {id, name, position, updated_at, steps[{id, position, name,
                                pessoas, sistema, dados, tempo, erro, retrabalho}]}
findings[]                   = {id, statement, epistemic_status, confidence, process_id, step_id,
                                evidences[{id, kind, reference, captured_at}]}
pain_points[]                = {id, title, description, impact_type, impact_estimate,
                                finding_ids[], status}
improvement_opportunities[]  = {id, title, desired_change, impact_hypothesis, pain_point_ids[],
                                status, priority_assessment: {version, score, dimensions{…}} | null,
                                solution_hypotheses[{id, statement, intervention,
                                expected_effect, status}]}
```

**As seis chaves do passo ficam em português, e é deliberado.** Elas *são* as seis letras do
P-S-D-T-E-R, nessa ordem, e o docstring de `ProcessStep` explica que renomear ou juntar faria o
levantamento da reunião deixar de casar com o formulário. A §5 do mapa de linguagem bane português
em nome de **modelo**, não de campo — e o snapshot já leva `pendencias` pelo mesmo tipo de razão.

`improvement_opportunities` e não `opportunities`: a §5 bane `Opportunity` sem qualificador, e o One
tem lint derivado dela do outro lado.

**Metadado, nunca material bruto.** `raw_excerpt` e `content_hash` não atravessam — a §3 proíbe
transcrição e evidência não revisada. `reference` atravessa porque é a **citação**, de onde veio e
não o que foi dito, e é o que torna a fonte conferível pelo cliente; o precedente é o
`has_transcript` que `meetings` já usa.

**`unknown` atravessa e não é omitido.** O One o renderiza como lacuna declarada; sumir com ele é o
que faz o cliente achar que não há pergunta em aberto sobre a operação dele.

**As listas de id vêm filtradas ao que atravessou.** `finding_ids` e `pain_point_ids` crus
apontariam para o que ficou de fora. `impact_estimate` nulo sai `None`, **nunca `0`**: zerar afirma
que a dor não custa nada.

**`priority_assessment` é só a versão vigente**, lida de `ImprovementOpportunity.current_assessment`
— reexpressar "vigente" aqui seria a segunda definição do mesmo fato. `null` sem avaliação, nunca
zero.

**O que não atravessa, e por quê:** os nove insumos do custo do estado atual (conta interna, e um
total parcial lido sem quem o levantou vira "vocês disseram que eu perco tanto por mês");
`rationale` (proibição literal da §3, e o repo `one` tem portão próprio para ela); `weights` e
`formula_key` (critério interno — é justamente a
mudança de critério que a versão existe para não confundir quem lê sem contexto); `assumptions` (a
nota interna do que se está supondo); `captured_by`, `reviewed_by`, `assessed_by` e `published_by`
(pessoa interna); e as `SolutionHypothesis` em `discarded`.

### 5. `rank` não é emitido — desvio consciente do que a issue pediu

Dois motivos, e cada um bastaria:

1. **`priority.ranking_da_conta` ordena todas as oportunidades vivas da conta**, publicadas ou não.
   Emitir esse número entregaria ao cliente `2, 4, 7` e, com ele, a dedução correta de que existem
   itens escondidos que o superam.
2. **Recalcular o rank só entre as publicadas criaria uma segunda definição de rank** — exatamente
   o que este repositório recusou ao não persistir o campo (FDD 048). Duas definições do mesmo fato
   divergem em silêncio.

O que a issue queria com o rank — que o backlog seja ordenável — é entregue por `score`, que é o
fato de onde o rank sai.

### 6. Oito emissores

`Process`, `ProcessStep`, `Evidence`, `Finding`, `PainPoint`, `ImprovementOpportunity`,
`PriorityAssessment` e `SolutionHypothesis`, todos com **fan-out por projeto** através de um helper
só (`_emit_para_a_conta`) — oito laços copiados garantiriam que o nono esquecesse `engagement__`.
Nenhum leva guarda de `created`: o que importa é o update, e **publicar é o evento inteiro desta
fatia** — um `save()` que muda o que o cliente vê sem criar linha nenhuma.

Quatro dos oito atravessam **aninhados** e não têm chave de topo (`Evidence`, `ProcessStep`,
`PriorityAssessment`, `SolutionHypothesis`), então a guarda derivada da ADR 0027 não os alcança —
`apps/core/tests/test_portal.py` os afirma à mão, na forma que a `Measurement` estreou na FDD 050.

## Aceite

1. `processes[]` traz os processos **publicados** e vivos da conta com os passos vivos e as seis
   chaves em português; processo não publicado, processo arquivado e passo arquivado ficam fora.
2. Nenhum item de `processes[]` leva os nove insumos de custo, `registered_by` ou `source_project`.
3. O Discovery da conta sai no snapshot de **todos** os projetos dela — dois projetos, dois
   engagements — e não no de fora.
4. `findings[]` traz só os publicados e vivos; achado não publicado não atravessa.
5. `fact` publicado sai com `evidences[]` não vazio; `unknown` publicado atravessa e não é omitido.
6. `evidences[]` não traz `raw_excerpt` nem `content_hash`; evidência não publicada não entra na
   lista mesmo estando no M2M de um achado publicado.
7. `pain_points[]`: `finding_ids` filtrado aos publicados; `impact_estimate` nulo sai `None` e não
   `0`.
8. `improvement_opportunities[]`: só a versão vigente do assessment; `rationale`, `assessed_by`,
   `weights`, `formula_key` e `rank` não aparecem; `score` e as cinco `dimensions` aparecem; sem
   avaliação, `priority_assessment` é `None`.
9. `solution_hypotheses[]` sai aninhada, sem as `discarded`, sem as arquivadas e sem `assumptions`.
10. Nenhum bloco leva `reviewed_by`, `captured_by`, `assessed_by`, `published_by`, `rationale`,
    `raw_excerpt` ou `content_hash` — asserção sobre as **chaves**, num cenário cheio.
11. Publicar `Finding` em `fact` sem evidência publicada é 400 e a resposta lista o que falta;
    publicar `PainPoint` sem achado publicado e `ImprovementOpportunity` sem dor publicada, idem.
12. Publicar duas vezes é 409; despublicar o que não está publicado é 409.
13. Despublicar a última sustentação publicada é 409 nos três degraus, e deixa de sê-lo quando
    sobra outra.
14. Arquivar a última sustentação publicada é 409 nos três degraus; a guarda antiga do `fact`
    continua de pé sem publicação nenhuma.
15. `PATCH` promovendo a `fact` um achado publicado sem evidência publicada é 400; o mesmo `PATCH`
    num achado interno passa.
16. Publicar `Process` não exige nada e o segundo `POST` é 409; publicar `Finding` ou `PainPoint`
    que cita mapa não publicado é 400 listando o que falta, inclusive quando a citação é só pelo
    `step`; achado sem mapa nenhum publica.
17. Despublicar e arquivar o mapa que ancora achado ou dor publicados são 409, e a cascata das
    etapas não roda antes da recusa; despublicado o de cima, o mapa desce e arquiva.
18. `published_at` sem `published_by` (e o inverso) é `ValidationError` nos cinco modelos; a marca
    não é escrita por `PATCH`; nada nasce publicado.
19. Os oito modelos emitem, com fan-out para os dois projetos da conta e não para o de fora.
20. As duas guardas do snapshot passam com as quatro chaves declaradas, e os quatro aninhados têm
    emissor afirmado à mão.
21. `PATCH` movendo `process` de um achado publicado para um mapa não publicado é 400 e a âncora
    não se move; idem quando a citação é só pelo `step`; idem para a dor publicada. Mover para um
    mapa **publicado** passa, e mover a âncora de um achado **interno** passa.

Regressão: `backend/tests/regression/test_o_snapshot_leva_o_discovery.py` e
`backend/tests/regression/test_a_cadeia_de_publicacao_nao_vaza.py`.

## A divergência que esta fatia resolveu, e onde ela foi registrada

`backend/tests/regression/test_processo_nao_volta_ao_cliente.py` (FDD 039) afirmava que o Discovery
estruturado **não** atravessa. A §3 do mapa de linguagem afirma que ele atravessa. As duas coisas
eram verdade ao mesmo tempo porque o schema não tinha a marca que a §3 pressupõe; era o schema que
estava atrasado, e é ele que se moveu.

O arquivo ganhou uma emenda datada, não uma revogação — e **não perdeu asserção nenhuma**. O
cenário dele tem um processo que ninguém publicou, então nada dele atravessa: o nome do processo, o
do passo, o `pessoas` da etapa, o achado em `hypothesis` e os nove insumos do custo continuam
cobrados, palavra por palavra. O que mudou foi a **força** da guarda — ela passava por ausência de
código e passa agora por invariante cobrada, com quatro listas vazias afirmando que o bloco existe
e o registro não atravessou. A camada **estrutural** sobre a fonte de `portal.py` não mudou uma
linha, e os comentários novos do módulo foram escritos contornando `PROIBIDOS_NA_FONTE` em vez de
afrouxá-la.

O `docs/ontology/language-map.md` **não foi editado**: é espelho fiel e não se edita aqui.

## Fora deste recorte

- **`ProcessStep` não ganha marca própria.** Ele anda com o processo pai — decisão registrada
  acima, não pendência.
- **`Discovery`, `DiscoverySession` e `ProcessObservation` não atravessam.** Eles dão tempo e
  autoria ao levantamento — quem esteve na sessão, quando, quantas horas —, e isso é organização
  interna do trabalho, não o resultado dele. A §3 não os lista.
- **Transcrição, nunca.** `Evidence.raw_excerpt` e `content_hash` não têm data de entrada; é
  proibição literal da regra 1 da §3, não pendência.
- **Nada de `Lead`, `Qualification`, `CommercialOpportunity` ou `PipelineStage`** — invariante 10
  da §6, e nenhuma linha desta fatia se aproxima deles.
- **Backfill de publicação.** Ver acima: decisão registrada, não pendência.
- **`rank` no payload.** Idem — decisão registrada, com os dois motivos escritos.
- **Superfície de publicação neste produto.** Nenhuma tela muda nesta fatia. Publicar hoje é uma
  chamada de API; a tela que a expõe é pacote próprio, com DAP, porque decidir *o que o cliente vê*
  merece um board revisado e não um botão improvisado ao lado de "Arquivar".
  **Emenda (03/09/2026):** a pendência foi paga. O pacote é
  `docs/design/dap-publicacao-discovery-r1/` (r1, **A1 · B1 · C1 · D1 · E1 · F1 · G1** mais a oitava
  decisão), a tela é `/contas/:id/publicacao`, e o que foi construído está na **FDD 052** — com o
  contrato do campo derivado `publication_state` na **ADR 0063**.
- **Descer as guardas do snapshot um nível.** Agora há quatro listas novas com chaves aninhadas que
  nenhuma das duas guardas fixa. Continua sendo a pendência deliberada da FDD 047: descer um nível
  toca a guarda de todo mundo e merece decisão própria, com ADR.
- **Rota de escopo Account para o One.** Ver a decisão (a): recusada nesta fatia, e o custo dela é
  a duplicação por projeto, que o outro lado já sabe absorver.

## Referências

- ADR 0060 — publicabilidade é campo próprio, e publicar é o ato de revisão humana da §3.
- ADR 0003 (emenda de 01/09/2026, a segunda do dia) — as quatro chaves e a regra da marca.
- ADR 0027 — a guarda derivada de "o que entra no snapshot precisa de emissor".
- ADR 0049 e FDD 045 — o split `Evidence`/`Finding`, e a invariante §6.9.
- ADR 0054 e FDD 048 — a cadeia do PRIORITIZE, e por que `rank` não é campo.
- FDD 039 — o Discovery estruturado, a FK de conta e a regressão que esta fatia emendou.
- FDD 047 e ADR 0051 — o carimbo da projeção e a pendência das guardas aninhadas.
- FDD 050 — a fatia irmã, do mesmo dia: a cadeia de medição atravessa.
- `docs/ontology/language-map.md` §3, §5 e §6.9-10; a issue `biahflow/one#90`, do outro lado.
