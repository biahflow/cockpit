# FDD 033 — Os gates da jornada

## Jornada

A metodologia FDE trazida pela ADR 0030 (`docs/metodologia-fde.md`) tem duas regras que travam a
passagem de fase, e nenhuma das duas existia como comportamento aqui:

> **Decision gate (obrigatório ao fim de Feasibility e de PROVE)** — exatamente uma saída,
> decidida por humano. *(Assim estava escrito quando esta FDD nasceu; a ADR 0053 separou os dois
> vocabulários — ver a emenda de 28/08/2026 no fim.)*

> **Quality gates (antes de entregar qualquer coisa ao cliente)** — Discovery: AS-IS validado?
> Números sustentados por evidência? … Feasibility: baseline definido? amostra adequada? …

A Jornada de Transformação (FDD 011) já tinha a escada de fases, o template configurável e os
entregáveis. O que ela não tinha era **como uma fase se recusa a fechar**: `advance_phase`
concluía a ativa e ativava a próxima, com o comentário explícito de que "não bloqueia por
entregáveis pendentes — o avanço é uma decisão da equipe". Enquanto o gate morava numa página do
Notion, isso era coerente: o sistema não podia cobrar uma regra que não conhecia.

O princípio da ADR 0030 é justamente esse: **contexto vira comportamento do sistema, não página
para ler.** Um checklist que só existe em documento é lido na primeira semana e esquecido na
terceira; um decision gate que não trava nada é uma convenção que sobrevive à custa da memória de
quem estava na reunião. E o pior caso não é a fase que avança cedo — é a que avança sem que reste
registro de *por que* se decidiu avançar.

## O que esta fatia entrega

Os dois gates, materializados na jornada que já existe:

- **Decision gate.** O template `JourneyPhase` ganha `requires_gate`; a instância
  `ProjectPhase` ganha `gate_decision` e `gate_notes`. A decisão entra por uma action nova,
  `POST /api/v1/projects/{id}/apply-gate/`, e cada saída faz uma coisa diferente com a jornada —
  GO/CONDITIONAL GO concluem e avançam, REDESIGN reabre a fase anterior e tranca a corrente,
  NO-GO registra e para ali. Desde a ADR 0053 a fase de PROVE fala SCALE / ITERATE / STOP, e as
  três caem nos **mesmos três efeitos**.
- **Quality gate (checklist).** `PhaseChecklistItem` no template e `ProjectChecklistItem` na
  instância, espelhos exatos de `PhaseDeliverable`/`ProjectDeliverable`. Concluir a fase ativa
  exige checklist completa **ou** `checklist_waiver` preenchida.

Na tela: o checklist e o painel do gate na fase ativa do detalhe do projeto, o selo da decisão
acompanhando a fase que já decidiu, e a configuração dos dois na tela de Jornada.

## Critérios de aceite

1. **Fase de gate não fecha sem decisão.** `advance_phase` recusa com 409 quando a fase ativa tem
   `requires_gate` e `gate_decision` vazio, e recusa de novo quando a decisão gravada é REDESIGN ou
   NO-GO — o gate decidiu não seguir, e "avançar mesmo assim" não é uma quinta saída.
2. **As saídas não são nomes diferentes para avançar.** REDESIGN/ITERATE reabrem a fase
   anterior e trancam a corrente; NO-GO/STOP deixam a fase ativa e não avançam nada. Mudar o
   status do projeto continua sendo ato humano, fora deste recorte.
3. **REDESIGN limpa o que deixou de ser verdade, e só isso.** A fase reaberta perde
   `completed_at` e o próprio gate; a fase trancada **mantém** `started_at` e o
   `gate_decision=redesign`, que é o registro de por que se voltou. Vale igual para o ITERATE.
4. **A checklist trava a conclusão por qualquer caminho.** Vale no `advance-phase` e na conclusão
   embutida no `apply-gate` — a guarda mora em `journey.py`, não na view. Zero itens passa: as
   fases semeadas antes desta FDD não têm checklist, e travá-las quebraria a jornada de todo
   projeto existente.
5. **Pular o quality gate é legítimo; fazê-lo em silêncio não é.** `checklist_waiver` preenchida
   destrava a conclusão e fica como registro. É o mesmo desenho da recusa de exclusão de fase
   (FDD 011/025): a saída existe, e ela é explícita.
6. **Projeto novo herda a checklist; projeto existente não é reescrito.**
   `materialize_journey` copia os itens junto dos entregáveis, e continua idempotente.
7. **Vendas lê, Entrega escreve no que é dela.** `project_checklist_item` entra em
   `RolePermission` e em `PROJECT_OF`: Vendas só-leitura, Entrega escreve dentro dos projetos de
   que participa, e `apply-gate` herda a política do `advance-phase` (o corte da Entrega é por
   ação, não por método).

## Decisões

### Por que `gate_decision` só entra pela action

`gate_decision` e `gate_notes` são **read-only no `ProjectPhaseSerializer`**. Um PATCH direto
gravaria "REDESIGN" sem que nada acontecesse: a fase anterior não reabriria, a corrente não
trancaria, e o campo passaria a mentir sobre o estado da jornada — a pior forma de defeito, porque
a tela mostraria a decisão certa sobre um sistema que não a executou. A action é o único lugar
onde a decisão e a consequência dela são a mesma operação.

`checklist_waiver`, ao contrário, é editável no serializer: ele não decide nada sozinho, apenas
declara uma justificativa que a guarda vai consultar.

### Por que REDESIGN limpa `completed_at` (e o precedente que ele segue)

Há dois precedentes opostos na casa, e o gate segue o primeiro:

- `Pendencia.save()` limpa `resolved_at` quando o status sai de "resolvida" — reabrir apaga o
  carimbo, porque "resolvida em" é **estado corrente**;
- `Decisao.published_at` sobrevive à despublicação (FDD 032) — é **fato histórico**: a data em que
  uma decisão passou a valer aconteceu, e esconder a decisão do cliente não a desfaz.

"Concluída em" é do primeiro tipo. Uma fase reaberta para ser refeita não está concluída, e manter
a data faria a jornada afirmar duas coisas incompatíveis ao mesmo tempo. O mesmo raciocínio limpa
o `gate_decision` da fase que volta: o gate dela ainda vai ser decidido de novo.

Já `started_at` da fase trancada **fica**. Ele não é estado corrente, é fato: passou-se por ali, e
o `gate_decision=redesign` preservado ao lado é o que explica por que se voltou.

### Onde moram as guardas

Em `journey.py`, levantando `StateConflict`. As duas recusas são regra de domínio: quem conclui
uma fase por qualquer caminho tem de passar por elas, e uma guarda escrita na view só valeria para
a rota que a chamou — hoje são duas (`advance-phase` e `apply-gate`) e nada impede uma terceira.

Isso exigiu mover `StateConflict` de `views.py` para `exceptions.py`. `views` importa `journey`;
`journey` importando `views` fecharia o ciclo, e o módulo precisa continuar importável sem
request. `exceptions.py` não importa nada do domínio e já era o lugar conceitual da classe — o
próprio docstring do `api_exception_handler` de lá a cita pelo nome ao explicar o 409.

### Por que o checklist não é uma segunda lista de entregáveis

Os dois modelos são espelhos, e a distinção é a que a metodologia faz: o **entregável** é o que
sai da fase (um dashboard, um manual, um vídeo); o **item de checklist** é a condição de qualidade
para que aquilo possa sair ("baseline definido?", "amostra adequada?", "T.O.E. avaliado?"). Marcar
um entregável como entregue não afirma nada sobre qualidade — é por isso que só o checklist trava
a conclusão, e o entregável continua não travando, como a FDD 011 decidiu.

## Contrato

Rotas novas, todas em `/api/v1/`:

| Rota | Quem |
| --- | --- |
| `POST /projects/{id}/apply-gate/` | delivery no próprio projeto / admin |
| `/phase-checklist-items/` (CRUD) | admin (`resource = "journey"`, como o template de entregáveis) |
| `/project-checklist-items/` (CRUD + `?archived=1` + `unarchive`) | delivery no próprio projeto / admin; Vendas só lê |

Campos novos: `JourneyPhase.requires_gate`; `ProjectPhase.gate_decision`, `gate_notes`,
`checklist_waiver` e o `requires_gate` derivado do template; `checklist_items` aninhado nos dois
serializers de fase. Nada removido — a mudança é aditiva.

`ENUM_NAME_OVERRIDES` ganha `GateDecisionEnum`: as saídas aparecem no esquema em dois conjuntos
diferentes (o campo do modelo, que aceita o branco de "ainda não decidido", e o corpo da action,
onde a escolha é obrigatória), e sem o override os dois disputavam o mesmo nome. Desde a ADR 0053
ele aponta para `ProjectPhase.DECISOES_DO_GATE`, as **sete**.

## Testes

- `apps/core/tests/test_journey.py` — as quatro saídas, a recusa sem decisão, a recusa depois de
  REDESIGN/NO-GO, REDESIGN sem fase anterior, gate em fase que não é de gate (409) e decisão
  inválida (400), os dois vocabulários da ADR 0053 (SCALE aceito no PROVE e GO recusado com 400,
  e vice-versa; a fase sem classificação com as quatro; a mensagem do avanço nomeando o
  vocabulário certo; STOP cancelando e ITERATE replanejando),
  o PATCH direto que não grava o gate, a herança do checklist na materialização, a
  fase que não fecha com item pendente, a justificativa que destrava, o item arquivado que não
  conta, o GO que esbarra no quality gate sem gravar a decisão, e o RBAC dos dois gates (Vendas
  lê e não marca; Entrega só alcança o projeto de que participa; template só de admin).
- `ProjectDetailJourney.test.tsx` — marcar item, registrar justificativa, aplicar GO com notas,
  a confirmação de REDESIGN/NO-GO, o selo da decisão e o 409 do avanço exibido na tela.
- `ProjectDetailJourneyReadonly.test.tsx` — Vendas lê o checklist, não o marca e não vê o painel
  do gate.
- `JourneyConfigPage.test.tsx` — o toggle do gate com o aviso do que ele passa a exigir, e o CRUD
  do checklist do template.

## Fora deste recorte

- **Snapshot do portal do cliente (`portal.py`).** Os campos novos não atravessam. O gate é
  linguagem interna de metodologia, e "NO-GO" numa tela de cliente é uma conversa que se tem
  antes, não um selo que aparece. Decisão para uma fatia própria, com emenda na ADR 0003 se vier.
- **Obrigar `gate_notes` no CONDITIONAL GO/REDESIGN/NO-GO.** A tela pede, o backend aceita vazio.
  Exigir texto por API sem ter visto o uso real produz o campo preenchido com um ponto.
- **Semear `requires_gate` nas fases padrão.** A semente da jornada (migração `0015`) não é
  tocada: as fases de lá são o vocabulário Biahflow (Welcome → Optimize), não a escada FDE
  (Feasibility, PROVE). Quem marca quais fases terminam em gate é o admin, na tela de Jornada.
- **Mudar o status do projeto no NO-GO.** A jornada para; encerrar, pausar ou renegociar o projeto
  é decisão humana com consequências comerciais próprias.

## Emenda (28/08/2026) — `GateOutcome` vira `GateDecision`, e a chave antiga fica na `/api/v1/`

A decisão **D7** do `docs/ontology/language-map.md` renomeia `GateOutcome` para `GateDecision`,
porque "Outcome" já é o **resultado de negócio medido** (`Measurement(kind=outcome)`, na tabela
mestra §2) e a saída de um decision gate não é isso — é uma decisão. Os **quatro valores não
mudam**: `go`, `conditional_go`, `redesign` e `no_go` já eram os canônicos. O texto acima foi
atualizado para o nome novo; o comportamento descrito nele é o mesmo de antes, linha por linha.

**O que mudou de nome.** A classe aninhada `ProjectPhase.GateOutcome` → `GateDecision`; o campo
`ProjectPhase.gate_outcome` e o `PhaseEvent.gate_outcome` → `gate_decision` (migração `0060`, só
`RenameField`: coluna renomeada preserva linha e pk, que é a invariante da `aliases.md` §2b); o
componente `GateOutcomeEnum` do esquema → `GateDecisionEnum`; o tipo TS `GateOutcome` →
`GateDecision`. O parâmetro de `journey.apply_gate` passou de `outcome` a `decision`.

**A propriedade-alias `ProjectPhase.gate_decision` deixou de existir**, e não por remoção: o campo
passou a ter o nome dela. Ela nasceu na Issue #71 para o snapshot do portal emitir canônico
enquanto o modelo não renomeava (`portal.py` lia por ela em vez de tocar o nome antigo). O
snapshot continua emitindo exatamente a mesma chave com o mesmo valor — agora lendo o campo.

**A `/api/v1/` não muda.** `ProjectPhaseSerializer` e `PhaseEventSerializer` passam a expor as
**duas** chaves com o mesmo valor: `gate_decision`, a canônica, e `gate_outcome`, alias de leitura
com data de morte na `/api/v2/`. A action `apply-gate` aceita `decision` no corpo e continua
aceitando `outcome` — a canônica tem precedência quando as duas vêm juntas. Quem integrou com a v1
não precisa fazer nada; quem escrever integração nova escreve o nome certo. A regressão que impede
alguém remover o alias antes da hora é
`backend/tests/regression/test_o_alias_do_gate_sobrevive_na_v1.py`.

**Por que agora, e não na Fase 6.** A **ADR 0052** desfez o termo "renome físico" em três coisas
com prazos distintos: o nome da **classe** é a issue #67 (uma fatia por PR, e esta é a primeira),
o nome da **tabela** é a Fase 6, e a **rota** com a **chave de payload** é a `/api/v2/`. O risco
que a espera protegia é o da pk, e pk é exatamente o que um `RenameField` não toca.

**A UI não muda de idioma.** `gateLabel` continua devolvendo GO / CONDITIONAL GO / REDESIGN /
NO-GO: são os rótulos da metodologia (`docs/metodologia-fde.md`), não identificadores.

## Emenda (28/08/2026) — cada gate com seu vocabulário

Esta FDD declarava as **quatro** saídas como universais, e o repositório se contradizia sozinho: a
migração `0050` semeia o degrau PROVE dizendo *"fecha em decision gate SCALE / ITERATE / STOP"*, e
`kickoff.KICKOFF_TEMPLATES["prove"]` já semeava a tarefa **"Registrar a decisão SCALE / ITERATE /
STOP"** numa fase em que a rota só aceitava as quatro. A equipe lia uma tarefa e encontrava outros
botões. A **FDD 015** era o único lugar do repositório que já estava certo: a tabela de degraus
sempre separou "decision gate GO / CONDITIONAL GO / REDESIGN / NO-GO" (Feasibility) de "decision
gate SCALE / ITERATE / STOP" (PROVE).

A **ADR 0053** decide a favor do código:

| Fase | Pergunta | Saídas |
| --- | --- | --- |
| Feasibility | *a tecnologia consegue fazer a tarefa?* | `GO` · `CONDITIONAL GO` · `REDESIGN` · `NO-GO` |
| PROVE | *funcionou em produção controlada?* | `SCALE` · `ITERATE` · `STOP` |

**Um campo, dois vocabulários.** `ProjectPhase.gate_decision` continua **um** campo e passa a ter
as sete choices (`ProjectPhase.DECISOES_DO_GATE`). Duas colunas seriam duas definições do mesmo
fato — "a decisão registrada no gate desta fase" —, e a segunda divergiria da primeira em
silêncio. Migração `0064`, só `AlterField`: `choices` não toca no banco e nenhum valor sai, então
não há dado a converter.

**Quem decide qual vocabulário vale é `JourneyPhase.canonical_stage`**, pela função
`models.decisoes_do_gate`. Não é campo novo: um `gate_vocabulary` no template seria a segunda
expressão de um fato que `canonical_stage` já carrega — "qual fase FDE é esta". Fase de gate com
`canonical_stage` **em branco** recebe as quatro da Feasibility: é o comportamento de todo gate
anterior a esta ADR (a semente da jornada, migração `0015`, não classifica nada) e são as saídas
de propósito geral — GO/NO-GO respondem a qualquer gate, SCALE/STOP só fazem sentido depois de um
piloto rodando.

**As três saídas novas não inventam efeito.** Cada uma cai num dos três que já existiam, e o
código passa a ramificar por **efeito** e não por valor literal
(`models.CONCLUEM_E_AVANCAM`/`REABREM_A_ANTERIOR`/`REGISTRAM_E_PARAM`):

| Efeito | Feasibility | PROVE |
| --- | --- | --- |
| conclui e avança | `GO`, `CONDITIONAL GO` | `SCALE` |
| reabre a fase anterior | `REDESIGN` | `ITERATE` |
| registra e para | `NO-GO` | `STOP` |

`ProjectPhase.situation` (FDD 042) segue a mesma tabela: `STOP` é `cancelled` como o `NO-GO`, e
`ITERATE` deixa a fase trancada como `replanned`, como o `REDESIGN`.

**A validação da decisão desceu da view para o domínio.** `views.apply_gate` conferia o valor
contra as quatro **antes** de saber qual era a fase ativa — o que deixou de ser possível quando o
vocabulário passou a depender da fase. A conferência mora agora em `journey.apply_gate`, que é
quem resolve a fase ativa, pela mesma razão que `Opportunity.clean()`/`Project.clean()` vivem no
modelo: shell, admin e migração não passam por rota. A rota continua devolvendo **400** com
mensagem legível, e a mensagem diz **qual** vocabulário aquela fase aceita — via
`exceptions.InvalidInput`, e não via `StateConflict`, que é 409 e diria à pessoa para procurar
erro num estado que está bom.

**O contrato é aditivo.** Nenhum valor sai da `/api/v1/`; o `ChoiceField` de `decision` (e o alias
`outcome`) publica as sete, porque o esquema não sabe de qual fase se trata — **quem estreita é o
servidor**, e o `help_text` diz isso.

**A tela mostra o vocabulário da fase ativa.** `frontend/src/journey.ts` ganha
`GATE_DECISION_LABEL`, `GATE_EFFECT` e `gateDecisions(canonical_stage)` — **um mapa só**, lido
pelo detalhe do projeto e pela tela de Jornada, porque uma cópia por tela é a segunda definição
que diverge sem nada ficar vermelho (ADR 0026). A variante do selo e a pele do botão saem do
efeito: `SCALE` pinta como `GO`, `ITERATE` como `REDESIGN`, `STOP` como `NO-GO`, e as saídas que
reabrem ou param continuam passando pela confirmação. Os rótulos **não se traduzem**: são o
vocabulário da metodologia, em maiúsculas.
