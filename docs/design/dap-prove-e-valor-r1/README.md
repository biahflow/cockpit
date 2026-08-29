# Design Approval Package — Feasibility, PROVE, KPI/Measurement e Value Ledger

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **1**
Status: **Approved**
Data: 2026-08-28
Produzido por: harness (Claude Code), sob `workflows/design-approval.md`
Issue: [#69](https://github.com/biahflow/pulse/issues/69) — Fase 5 da migração de ontologia (épico [#62](https://github.com/biahflow/pulse/issues/62))

> Este artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> dentro do código de aplicação. Nenhuma linha de `frontend/src/` ou `backend/` muda nesta entrega.

## Por que existe um gate

Hoje **o ativo de solução é dono da verdade da medição**: `kpi_label`, `kpi_unit`, `kpi_direction`,
`kpi_baseline` e `kpi_current` são colunas de `DigitalEmployee`
(`backend/apps/core/models.py:2654-2669`). Isso tem três consequências que a issue #69 existe para
desfazer: um KPI não sobrevive à troca do ativo que o mede; um PROVE não pode ter mais de um KPI;
e "antes" e "depois" são **duas colunas** e não duas medições do mesmo indicador em momentos
diferentes — que é o que elas são.

Junto disso, `Case` congela `metrics`/`health_snapshot`/`roi_snapshot` no momento em que o projeto
conclui (`backend/apps/core/cases.py:74-91`) e, na prática, vira a fonte de verdade do resultado.
Não é: um case é material comercial derivado de dado aprovado.

Esta fase não é só schema — **ela muda superfície que já existe**. O formulário do "Time Digital"
em `ProjectDetailPage.tsx:310-337` edita hoje "Antes (base)" e "Depois (atual)" direto no ativo. Se
o KPI sair do `DigitalEmployee` e o formulário ficar, passam a existir **dois lugares que escrevem
a mesma medição**, e a que vale é a última salva — o defeito volta pela porta da tela. Alterar esse
formulário é `INTERFACE_CHANGE` por definição, e é a decisão **C** deste pacote.

Nenhuma aprovação vigente cobre estas superfícies. O DAP GH-26 r1 aprovou marca e fundações e
listou "as outras 20 telas de produto" como **não** aprovadas.

O gate fica **antes do planejamento**. Ele é pedido agora, com o mapeamento feito e nenhuma linha
de implementação escrita.

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização auto-contida. Abre sem build, sem toolchain e sem rede. |
| `board-desktop.png` | Captura congelada do board a 1280px, `deviceScaleFactor: 2`. |
| `board-mobile.png` | Captura congelada do board a 390px. |

As capturas são a evidência fixa do que foi renderizado. Elas retratam o **board**, não o produto —
a evidência renderizada da tela implementada é `BROWSER_REQUIRED` e vem depois, contra o código.

## Onde as superfícies moram

Três, e o critério de repartição é **de quem é o dado**:

1. **`ProjectDetailPage` — dois painéis novos**, logo abaixo da Jornada: **"Technical Feasibility"**
   (o laudo) e **"PROVE"** (o experimento, seus KPIs e as medições). Feasibility e PROVE pendem de
   `SolutionHypothesis` **e** de `Project`; a decisão que eles justificam é a decisão de gate da
   fase, que já mora ali.
2. **`ProjectDetailPage` — o painel "Time Digital" muda**: deixa de editar baseline e atual, e
   passa a mostrar o KPI que o ativo **referencia**, com link para o PROVE onde ele é medido.
3. **Uma tela nova por conta**, em `/contas/:id/valor` — o **Value Ledger**. `ValueLedgerEntry`
   pende de `Engagement`, e engagement é da conta; um projeto vê a sua fatia, a conta vê o total.
   É a simétrica de `/contas/:id/priorizacao` (DAP priorização r1).

**Nenhum link novo no menu lateral.** Mesma razão do pacote da priorização: valor é sempre *de uma
conta*, e um item de menu que abre pedindo "qual conta?" é um beco.

## O que está sendo pedido

Cinco decisões, desenhadas **lado a lado no board**. A marcação de recomendação é proposta do
harness — não decisão tomada.

### Decisão A — Feasibility e PROVE são painéis do projeto ou tela própria

- **A1 (recomendada)** — dois painéis em `ProjectDetailPage`, abaixo da Jornada, visíveis só quando
  o projeto tem a fase canônica correspondente (`JourneyPhase.canonical_stage` ∈
  `feasibility`/`prove`).
- **A2** — tela própria por projeto, `/projetos/:id/prove`.

A issue é explícita: *"fase é progresso; o agregado é conteúdo da decisão"*. O laudo de Feasibility
existe para sustentar um `GO`/`CONDITIONAL GO`/`REDESIGN`/`NO-GO`, e o PROVE para sustentar um
`SCALE`/`ITERATE`/`STOP` (ADR 0053). Separar o conteúdo da decisão em outra tela faz a pessoa
decidir num lugar e ler a prova em outro — que é como se decide sem ler.

O contra-argumento honesto de A2: `ProjectDetailPage` já é a tela mais longa do produto. A1
responde com visibilidade condicional — um projeto de Discovery Sprint não mostra painel de PROVE,
e a página só cresce onde a fase existe.

### Decisão B — a linha do KPI mostra Baseline → Outcome, ou só a leitura vigente

- **B1 (recomendada)** — `Tempo de resposta · 4h20 → 1h05 · −74% · h` com o histórico completo de
  `Measurement` num `<details>` colapsado.
- **B2** — só a medição mais recente; o histórico existe na API e não na tela.

Baseline e Outcome **são o mesmo KPI em momentos diferentes** — é a frase central da issue. Mostrar
só a leitura vigente reintroduz, na leitura, a fusão que o modelo desfaz na escrita: sem o par, o
número não diz se melhorou. E a comparação só é legítima com **mesma unidade e mesmo método**
(invariante da issue), então a unidade fica na linha, não no cabeçalho.

**A lacuna é `—`, nunca `0`.** KPI sem baseline mostra `— → 1h05`, e a variação fica vazia. Zerar
afirmaria que o processo não custava nada antes, e é a mesma regra que
`Process.custo_do_estado_atual` já aplica com `nao_apurado`
(`backend/apps/core/process.py:71-74`).

### Decisão C — o formulário do Time Digital perde "Antes (base)" e "Depois (atual)"

- **C1 (recomendada)** — os dois campos saem do formulário
  (`ProjectDetailPage.tsx:310-337`). O painel passa a mostrar, só-leitura, o KPI que o ativo
  referencia e a última medição, com link para o PROVE onde ela foi tomada.
- **C2** — os campos ficam, editáveis, e passam a escrever `Measurement` por baixo.

C2 é mais suave para quem já usa a tela, e é o caminho que desfaz a fase inteira: dois lugares
escrevendo a mesma medição fazem a fonte da verdade voltar a ser o ativo de solução. C1 assume o
custo — quem media pelo formulário passa a medir pelo PROVE — e é a única leitura compatível com
"o DigitalEmployee passa a **referenciar** KPIs, não a possuí-los".

**Esta é a decisão mais cara do pacote**, porque é a única que remove algo que existe hoje e que
alguém pode estar usando. Ela está desenhada no board como *antes* e *depois*, lado a lado.

`kpi_value` (o campo de texto livre marcado "obsoleto desde a FDD 027", `models.py:2655-2658`)
**não** é tocado aqui: ele alimenta o painel "Seu Time Digital" do One
(`backend/apps/core/portal.py:270-283`), e mexer nele é mudar a projeção do cliente — outro gate,
outro pacote.

### Decisão D — o Value Ledger é tela própria ou seção da conta

- **D1 (recomendada)** — tela própria em `/contas/:id/valor`, simétrica a `/contas/:id/priorizacao`.
- **D2** — nona seção do `AccountDetailPage`.

Mesmo raciocínio do pacote da priorização, e uma razão a mais: o ledger é uma **lista financeira
com aprovação** (`status`, `approved_by`, `attribution_method`), e uma lista com fluxo de aprovação
dentro de uma página de cadastro fica pequena demais para ser auditável.

### Decisão E — PROVE sem baseline: bloqueia ou avisa

- **E1 (recomendada)** — o botão "Iniciar PROVE" fica desabilitado, com uma lista do que falta
  (KPI · critério de sucesso · baseline) e **uma saída explícita**: "registrar lacuna aprovada",
  que pede quem aprovou e por quê.
- **E2** — avisa em `.alert--error` e deixa começar.

A invariante da issue diz: *"PROVE não começa sem KPI, critério de sucesso e Baseline definidos —
ou lacuna aprovada explicitamente"*. Uma tela que só avisa transforma invariante em sugestão, e a
"lacuna aprovada" deixa de ser um ato registrado para virar um clique que ninguém assina. E1 mantém
a saída — mas ela custa um nome e uma justificativa.

## Estados desenhados

| Estado | Onde | O que diz |
| --- | --- | --- |
| Carregando | painéis do projeto e tela de valor | "Carregando…", no molde vigente |
| Vazio — sem Feasibility | painel Feasibility | "Nenhum laudo. A Feasibility responde se a tecnologia consegue fazer a tarefa." |
| Vazio — sem PROVE | painel PROVE | "Nenhum experimento. O PROVE responde se funcionou em produção controlada." |
| Vazio — sem KPI | painel PROVE | "Sem KPI definido. O PROVE não começa sem indicador, critério e baseline." |
| Bloqueado — falta baseline | painel PROVE | botão desabilitado + a lista do que falta + "registrar lacuna aprovada" (decisão E) |
| Sem medição | linha do KPI | `— → —`, variação vazia. **Nunca `0`** |
| Vazio — ledger | `/contas/:id/valor` | "Nenhum valor registrado. Uma entrada de valor aponta para um Outcome medido." |
| Pendente de aprovação | linha do ledger | `.state--2` "Pendente" — valor que ainda não vale como valor |
| Erro | todos | `.alert--error` com o texto do backend |
| Não autorizado | painéis do projeto | recorte de Entrega por `ProjectMember`, como o resto de `ProjectDetailPage` |

**A decisão de gate nunca aparece rotulada como resultado.** `GO`, `SCALE` e afins ficam onde já
estão — na Jornada — e o painel do PROVE mostra a decisão como *decisão*, ao lado do Outcome, nunca
no lugar dele. É a invariante §6.3 do `language-map` e um item explícito da issue; está registrado
aqui, não submetido.

## Procedência de cada valor visual

Nenhum valor novo. Tudo vem de `frontend/src/index.css` e das fundações r2 (DAP GH-26 r1):

| Valor | Origem |
| --- | --- |
| Cores `ink`, `canvas`, `line`, `muted`, `brand-*`, `danger` | `index.css` `@theme` — ADR 0024 |
| `.panel`, `.row`, `.panel-heading`, `.eyebrow`, `.metric-card`, `.metric-icon` | `@layer components` |
| `.state--0..3`, `.state--off` | idem. `--off` para "encerrado"/"descartado", que não são aviso |
| `.btn`, `.btn--secondary`, `.btn--secondary-danger`, `.btn--icon` | idem |
| `.field`, `.form-label`, `.form-grid`, `.toolbar`, `.empty-state`, `.alert--error`, `.back-link` | idem |
| Raio 8px / 12px, papéis `--text-title/-body/-label/-meta` | fundações r2 |
| Ícones | `lucide-react` — `FlaskConical` (PROVE), `Microscope` (Feasibility), `Gauge` (KPI), `Coins` (Value) |

Se a implementação precisar de primitiva que não existe, isso é **revisão deste pacote**, não
julgamento de quem implementa (`src/test/primitivas.test.ts`, ADR 0026).

## Fronteira entre entregue e reservado

**Entregue:** os dois painéis do projeto, a mudança do painel Time Digital (decisão C), a tela
`/contas/:id/valor`, e os dez estados acima.

**Reservado (desenhado esmaecido, com a condição escrita ao lado):**

- **`Case` derivado de Outcomes aprovados.** A issue pede; a tela do Case
  (`CasesPage.tsx:140-144`) lê hoje o snapshot congelado e **não muda nesta entrega**. Vira real
  quando houver Outcome aprovado suficiente para derivar — e é revisão deste pacote ou pacote novo.
- **Gráfico de série do KPI.** As medições formam série temporal e o produto não tem nenhum gráfico
  hoje. Fica reservado: um primeiro gráfico é decisão de sistema de design, não de tela.
- **Value Ledger consolidado entre contas.** O ledger é por conta nesta revisão. O total da casa é
  tela de Indicadores, e tem dono diferente.

## O que a aprovação não cobre

- O **backend** da Fase 5 (modelos, migração de `kpi_baseline`/`kpi_current` para `Measurement`,
  rotas, permissões). Aprovar a tela não aprova o schema.
- A **migração de dado**. Mover medição existente é decisão com risco próprio e vai no PR da #69,
  com nota de reversão.
- O **One**. `portal.build_snapshot` não muda aqui, e `kpi_value` continua como está.
- As telas da **Fase 4** (#68), que têm pacote próprio (`docs/design/dap-priorizacao-r1/`).
- **Copy final de microtexto** fora dos dez estados listados.
- Qualquer alteração nas demais seções de `ProjectDetailPage` e nas oito de `AccountDetailPage`.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| Revisão | 1 |
| Decisões submetidas | A · B · C · D · E |
| Escolhas | **A1 · B1 · C1 · D1 · E1** — as cinco recomendações do harness, aprovadas em bloco |
| Aprovado por | Daniel Campos |
| Data | 2026-08-28 |
| Escopo | superfície e estados. Não cobre backend, migração de dado, One, Fase 4, nem copy fora dos dez estados |

A aprovação foi dada sobre `board.html` na sua forma corrigida — a lista "falta para iniciar o
PROVE" passou a mostrar os **três** requisitos da invariante (KPI · critério de sucesso · baseline),
cada um com pastilha `Pronto`/`Falta`, em vez dos dois itens que a primeira renderização trazia. As
capturas foram refeitas depois da correção, e é a elas que esta aprovação se refere.

**O que C1 obriga, e está aprovado junto:** os campos "Antes (base)" e "Depois (atual)" saem do
formulário de edição do `DigitalEmployee` em `ProjectDetailPage`. Quem media pelo formulário passa
a medir pelo PROVE. É a única decisão do pacote que remove algo em uso hoje, e a migração de
`kpi_baseline`/`kpi_current` para `Measurement` precisa preservar o dado existente — o que **não**
está aprovado aqui: migração de dado é decisão do PR da #69, com nota de reversão.
