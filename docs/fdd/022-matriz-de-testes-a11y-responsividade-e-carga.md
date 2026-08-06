# FDD 022 — Matriz de testes: acessibilidade, responsividade e carga

## Jornada

Último item aberto do bloco "Prontidão para produção" do `roadmap.md`, e o único que sobrou depois
que a FDD 019 fechou transporte, a 020 observabilidade e a 021 backup: *ampliar a matriz de testes —
acessibilidade, responsividade e carga*.

O que existia era desigual. Havia 89 testes de unidade cobrindo comportamento e 5 e2e cobrindo
fluxo, mas:

- **Acessibilidade: nenhum ferramental.** Nenhuma ocorrência de `axe`, `jest-axe` ou
  `eslint-plugin-jsx-a11y` no repositório. O que havia era a11y escrita à mão e sem rede — `aria-label`
  denso em `ProjectDetailPage`, nenhum em `TeamPage`.
- **Responsividade: nenhum teste.** O `playwright.config.ts` tinha um projeto implícito
  (`Desktop Chrome`), sem `projects` e sem `viewport`. Nenhum `setViewportSize` em lugar algum. A UI
  usa três breakpoints e o corte estrutural — sidebar ↔ menu hambúrguer — nunca foi exercitado.
- **Carga: um script que não podia passar.** `loadtests/dashboard.js` mandava um `SESSION_COOKIE`
  para 20 VUs; com `USER_RATE` a ≈0,55 req/s por usuário, ele colheria 429 e reprovaria no próprio
  `http_req_failed`. Não era "um endpoint só" — era um script que ninguém tinha rodado.

A pergunta que este recorte responde: **o portal continua utilizável por quem navega de teclado, no
celular e com a base grande — e como eu descubro isso antes do cliente?**

## Regras

- **A matriz é dirigida por tabela.** `frontend/e2e/matrix.ts` tem uma lista `ROUTES` de rota ×
  papel, e as duas specs iteram sobre ela. Tela nova entra por **uma linha**, não por um arquivo de
  teste novo — é o que impede a matriz de envelhecer, porque o custo de cobrir a próxima página é
  uma linha.
- **As fixtures têm volume e nomes longos.** Lista vazia nunca estoura na horizontal. Uma matriz de
  responsividade alimentada com "Cliente 1" e tabelas vazias passaria inteira sem provar nada, e o
  estado vazio de `ProjectsPage`/`ClientsPage` é justamente o caminho mais fácil de acertar. As
  fixtures trazem 8 linhas por lista e razões sociais de ~60 caracteres.
- **O axe roda no browser, não em jsdom.** As duas falhas que mais doíam aqui — contraste e foco —
  dependem de layout e de CSS aplicado, e jsdom não calcula nem um nem outro. Um `jest-axe` no
  Vitest daria sensação de cobertura sem ver o que estava quebrado.
- **Três larguras, um browser.** 390 (celular), 768 e 1280. 768 não é enfeite: é a fronteira `md` e,
  como o corte do `Layout` é `lg` (1024), é **a largura em que o tablet cai no menu hambúrguer** — a
  faixa que ninguém testava. Continua só Chromium: viewport não pede browser novo, e o CI já
  instala esse.
- **Os e2e de fluxo continuam só no desktop.** Multiplicá-los por três larguras triplicaria o tempo
  sem cobrir nada que a matriz não cubra.
- **O gate de carga é contagem de query, não cronômetro** (ADR 0014). Mede-se a mesma rota com 3 e
  com 12 clientes e cobra-se que a contagem **não mude**. Auto-calibrado: sobrevive a refatoração
  que troque o número absoluto e reprova exatamente a inclinação.
- **A avaliação em lote é comparada com a individual.** O risco de carregar em lote não é a query, é
  divergir: um agrupamento errado por `project_id` mostraria a saúde do projeto vizinho, e nenhum
  orçamento de query perceberia.

## Defeitos corrigidos

**O portal apagava o próprio indicador de foco.** `index.css` trazia
`button, input, select { @apply focus:outline-none }`. Alguns campos recompunham com `focus:ring`;
**nenhum botão recompunha**. Navegar de teclado era navegar às cegas (WCAG 2.4.7). A supressão saiu
inteira, por dois motivos: browser moderno já só desenha o anel padrão em `:focus-visible`, então
suprimir `:focus` resolvia um problema que deixou de existir; e ela **impedia a correção** —
`outline-none` do Tailwind v4 grava `--tw-outline-style: none` no elemento, e como `outline-2`
desenha com `outline-style: var(--tw-outline-style)`, toda regra de `:focus-visible` escrita depois
resolvia para `none` e não aparecia. Em silêncio. A primeira tentativa de correção **não funcionou
por isso**, e só o teste explícito mostrou.

**Contraste reprovando em toda parte.** `text-slate-400` (2,5:1 sobre branco) em 64 lugares;
`text-slate-500` (4,47:1 sobre o `sand` do próprio portal) em 103; e `--color-signal` `#d05d45` a
3,9:1 — a cor da marca, usada como **texto** em prazo vencido e mensagem de erro. Slate-400 e
slate-500 estão aposentados como cor de texto (o tom mais claro passa a ser slate-600, que dá 7,6:1)
e `--color-signal` foi para `#bd4a30`. O mesmo ajuste conserta o contador de notificações, que é
branco sobre `bg-signal` e também reprovava.

**Controles sem nome acessível.** Três `<input type="date">` e um `<select>` no detalhe do projeto
(`placeholder` não nomeia um campo de data). Rendiam `label` e `select-name`, ambos **críticos**.

**Faixas roláveis inalcançáveis por teclado.** O kanban do comercial e a tabela de projetos rolam na
horizontal mas não recebiam foco — quem navega por teclado não chegava às colunas fora da tela.

**Linha de tabela clicável só com mouse.** `ProjectsPage` tinha `<tr onClick>` navegando para o
projeto, sem ser focável nem acionável por teclado. O `onClick` saiu; a linha já contém um `<a>`
real. **Mudança de comportamento deliberada:** a área clicável encolhe da linha inteira para o nome
do projeto. O *stretched link* preservaria a área, mas depende de `position: relative` em `<tr>`,
que é historicamente instável entre browsers — e só testamos Chromium.

**A página de login não tinha `<h1>` no celular.** O `<h1>` era a chamada de marketing do painel
lateral, que é `hidden lg:flex`: abaixo de 1024 a página ficava só com um `<h2>`. A chamada virou
`<p>` (é decorativa e some no celular) e "Entre na sua operação" virou o `<h1>` — que é o que a
página é.

**Estouro horizontal no detalhe do projeto, no celular.** Duas causas, a mesma raiz: item de grade
nasce com `min-width: auto` e se recusa a encolher abaixo do próprio conteúdo. No `WorkColumn`, uma
linha com campo `w-full` ao lado de um botão de largura fixa; no `ArtifactsPanel`, o `cols` padrão do
`<textarea>` dando ao cartão um min-content de ~525px dentro de uma coluna de 350.

**E um defeito no próprio teste, de carona.** A primeira versão do helper esperava só pelo `<h1>` e
media em seguida. O painel de artefatos carrega **depois** do título, então a medição pegava a
página pela metade e o resultado dependia da máquina do dia — foi assim que o estouro do painel
quase passou. O helper agora espera `networkidle`, que com a API toda mockada significa "o React já
renderizou tudo o que ia buscar".

**N+1 nos três agregadores.** `/clients/overview/` consultava os projetos visíveis **por cliente** e
avaliava saúde, risco, fase e próxima reunião dentro do laço: 43 queries com 3 clientes, 169 com 12.
`/risk/` e `/health/` avaliavam **por projeto**, 2 e 4 queries cada. Agora `risk.assess_projects` e
`health.assess_projects_health` carregam tudo em lote, e `build_overview_context` monta uma vez o que
`build_client_overview` consumia por cliente. Custo constante nos três.


## Fechado depois: foco preso e `Escape`

O que esta FDD adiou por não ser alcançável pelo axe entrou depois, com teste próprio em
`e2e/teclado.spec.ts`:

- **O diálogo prende o `Tab` e fecha no `Escape`.** `aria-modal="true"` promete ao leitor de tela
  que o resto da página está inerte; sem prender a tabulação, a promessa era falsa.
- **O sino e o menu do usuário fecham no `Escape`** e **devolvem o foco a quem os abriu** — a
  metade esquecida, porque sem ela quem fecha é despejado no início da página.
- **A alternativa de teclado ao kanban ficou provada**: o `select` de etapa no detalhe da
  oportunidade existe e é alcançável. Este é caracterização, não correção — o caminho já existia,
  faltava travá-lo.

Sabotagem: remover os hooks reprova quatro dos cinco testes; o quinto passa de propósito, porque
não testa mudança nenhuma.

**E a matriz cobrou o próprio preço de outra entrega.** Ao carregar a fonte Inter de verdade
(ela estava declarada e nunca baixada), as métricas de texto mudaram e o detalhe do projeto passou
a estourar **5 px** na horizontal no celular — uma fileira de quatro botões de IA com `flex` sem
`flex-wrap`. O layout estava, sem que ninguém soubesse, ajustado contra a fonte de fallback. É
exatamente o defeito que esta matriz existe para pegar, e ela pegou.

## Fora deste recorte

**`eslint-plugin-jsx-a11y`.** Estava planejado e ficou de fora por um motivo concreto: a versão
6.10.2 declara peer de `eslint` só até a 9, e o projeto está na 10. Instalar com `--legacy-peer-deps`
seria contornar uma verificação de qualidade para fechar uma tarefa, o que o `AGENTS.md` §6 proíbe.
Entra quando o plugin alcançar o eslint 10. O gate de verdade é o axe, que roda no browser e vê o
que o lint não veria.

**Focus trap e `Escape` nos modais** (`CommercialPage`, `ProjectDetailPage`) e nos overlays
`<button className="fixed inset-0">` que fecham os menus do `Layout`. É reescrita de comportamento
de foco, não ajuste de estilo.

**Alternativa por teclado ao drag & drop do kanban.** O `<select>` de etapa no modal de detalhe já é
o caminho acessível na prática; falta comprová-lo como equivalente.

**Conteúdo recortado por `overflow-hidden`.** Descoberto ao tentar sabotar o gate: alargar a tabela
de `ProjectsPage` **não** reprova, porque o cartão que a contém tem `overflow-hidden` e recorta em
silêncio. O teste cobre "a página não rola na horizontal", não "nada foi escondido". Achar conteúdo
recortado é outro eixo — provavelmente comparação visual, que precisa de baseline versionada.

**Latência com gate automático** e **segundo browser (Firefox/WebKit)**. Justificativas na ADR 0014
e acima.

**A divergência com a skill `biahflow-design`.** O `CLAUDE.md` aponta o design system
(`paper`, escala `pine`/`clay`, componentes compartilhados), mas o `index.css` traz a paleta anterior
(`ocean`/`mint`/`sand`/`signal`), sem componentes compartilhados e sem import da fonte Inter —
`--font-sans` cai no fallback. A correção de contraste encostou nisso ao escurecer `--color-signal`;
reconciliar as duas paletas é outro recorte.

## Aceite

`npm run e2e` roda 116 testes em quatro projetos: `e2e` (fluxo, desktop) e `mobile`/`tablet`/
`desktop` (matriz). Cada uma das 17 telas é varrida pelo axe nas tags WCAG 2.0/2.1 A e AA nas três
larguras, e conferida contra rolagem horizontal; mais navegação alcançável, alvo de toque ≥24 px e
foco de teclado visível. `uv run pytest` inclui o orçamento de query dos cinco agregadores.

O CI **não ganha nenhum job**: o orçamento roda no `pytest` do job `backend`, a matriz no
`npm run e2e` do job `frontend`. O k6 fica fora, com procedimento em
`docs/runbooks/testes-de-carga.md`.

## Regressão crítica

Cada gate foi verificado por sabotagem deliberada — um gate que nunca reprovou não é gate:

1. **Carga.** Trocar `risk.assess_projects(projects)` de volta pelo laço `assess_project` por
   projeto: `/api/v1/risk/` foi de 13 para 49 queries e o teste reprovou com a contagem nas duas
   bases. Restaurado, os cinco agregadores passam.
2. **Responsividade.** Remover o `min-w-0` do cartão do `ArtifactsPanel`: "Detalhe do projeto não
   rola na horizontal" reprovou em `mobile` e continuou passando em `tablet` e `desktop` — que é
   exatamente a assimetria esperada.
3. **Acessibilidade — e a descoberta que mudou a entrega.** Repor o `focus:outline-none` cru: as
   **51 varreduras do axe continuaram passando**. O axe não tem regra automatizada para foco visível
   (WCAG 2.4.7 é verificação manual), então a correção de foco estava sem gate nenhum. Daí o teste
   explícito `o foco de teclado fica visível nos botões`, que tabula com o teclado de verdade
   (foco programático nem sempre casa com `:focus-visible` no Chromium) e lê o `outline` computado.
   Com a sabotagem ele reprova nas três larguras; restaurado, as 54 passam.

Uma sabotagem **não** reprovou, e o motivo está registrado em "Fora deste recorte": alargar a tabela
de `ProjectsPage` para `min-w-[1400px]` passa, porque o `overflow-x-auto` a contém — e, mesmo
removendo a contenção, o `overflow-hidden` do cartão recorta em vez de rolar.
