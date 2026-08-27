# Design Approval Package — GH-42 · Escada FDE na conta

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **1**
Status: **Awaiting approval**
Data: 2026-08-27
Produzido por: harness (Claude Code), sob `docs/engineering-os/workflows/design-approval.md`

> Este artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> dentro do código de aplicação — `design-approval.md` chama de anti-padrão "a mock that is also
> the implementation".

## Por que existe este gate

A Issue [#42](https://github.com/biahflow/pulse/issues/42) se classifica `INTERFACE_CHANGE` /
`BROWSER_REQUIRED` no próprio corpo, e cria uma superfície que não existe: uma linha do tempo com
degraus, marcadores, trilho e aninhamento. **Nenhum DAP vigente cobre isso.** O GH-19 r2 aprovou
fundações (tokens, tipografia, espaço, raio, elevação); o GH-26 r1 aprovou a marca e a composição
do shell e listou explicitamente as outras telas de produto como "Issue própria por tela ou
família" (`dap-gh26-r1/README.md`, seção "Entregue vs. reservado").

E há um segundo motivo, mais forte: **não existe primitiva de linha do tempo ou de *stepper* no
design system**. Toda composição desta superfície seria valor novo, e o `design-approval.md` diz
que um projeto nessa posição "should expect its first approved package to establish language that
later packages cite". É isso que esta revisão pede que seja decidido.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | — |
| Aprovado por | — |
| Data | — |
| Revisão aprovada | — |
| Explicitamente **não** aprovado | — |

**Nenhum agente aprova design, inclusive um que não produziu** (`design-approval.md`, "Agent
authority"). Os campos ficam em `—` até que uma pessoa decida.

A aprovação precisa ser dada em **duas decisões separadas**, porque aprovar visual não aprova copy:

1. **Visual** — a composição da escada, as sete variantes de degrau, a pele de engenharia, a
   pastilha sólida do Human Gate e o bloco compacto da visão geral.
2. **Copy** — as strings exatas: os cinco rótulos de quem-espera (`Biahflow`, `Cliente`,
   `Engenharia`, `Dependência externa`, `Human Gate`) e os sete rótulos de estado (`Concluído`,
   `Não vendido`, `Pulada`, `Bloqueado`, `Aguardando decisão de gate`, `Replanejado`,
   `Sem acesso`), além do título do painel (`Escada FDE`) e do texto do estado vazio.

Aprovação da revisão 1 não é aprovação de uma revisão posterior.

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização auto-contida. Abre sem build, sem toolchain e sem rede. |
| *(a produzir)* `approved-board.png` | Captura congelada do quadro. **É a isto que a aprovação vai se referir.** |

**O pacote está incompleto até que a captura exista.** O item 2 do `design-approval.md` exige
"fixed evidence of what was rendered … alongside the source", com a razão explícita: *"a rendering
depends on fonts, browser, and platform; the frozen capture is what the approval actually refers
to."*

A captura e o SHA-256 dela **serão produzidos e anexados no ato da aprovação**, por quem tiver
navegador. Este harness não tem um, e a alternativa — inventar um nome de arquivo e um hash —
produziria exatamente a "approval without revision identity" que o mesmo documento lista como
anti-padrão. **Nenhum hash foi inventado aqui.**

Depois da aprovação, o preenchimento é:

```text
SHA-256 de approved-board.png: <a calcular no ato>
```

## Superfícies e estados no pacote

| Superfície | Estado | No pacote |
| --- | --- | --- |
| A · Escada da conta (`/clientes/:id`) | sucesso — degrau concluído | sim |
| A | sucesso — degrau **ativo**, expandido, com a jornada de entrega aninhada | sim |
| A | **não vendido** | sim |
| A | **pulada** (só Feasibility), com motivo, autor e carimbo | sim |
| A | **bloqueado**, com o quê e quem | sim |
| A | **aguardando decisão de gate**, com as quatro saídas | sim |
| A | **cancelado / replanejado**, sem apagar histórico | sim |
| A | **vazio** — conta nova, `.empty-state` | sim |
| A | **carregando** — esqueleto, sem selo colorido | sim |
| A | **sem autorização** — o que o papel `delivery` vê | sim |
| A | **erro / serviço indisponível** — `.alert--error` | sim — **acrescentado** (ver nota abaixo) |
| A | histórico de transições com carimbo e autor | sim |
| B · Bloco compacto (`/`) | sucesso, quatro contas em estados diferentes | sim |
| B | vazio / carregando / erro | **não** — herdam o comportamento da visão geral, já aprovado no GH-26 r1 |
| A e B | tema escuro | **não** — fora do contrato (`pulse-design-system.md`, "Fora deste contrato") |
| A e B | 390 px, foco, teclado, leitor de tela, *reflow* | **não** — é runtime, validado em browser e não neste quadro |

O **erro de carregamento** não está entre os dez estados que a especificação da tarefa lista. Ele
entra porque o item 3 do `design-approval.md` exige o estado de erro em todo pacote, e a tela pode
alcançá-lo (`ClientDetailPage.tsx:152` já trata a falha com `.alert--error`). É acréscimo, não
desvio.

## Os três eixos — e por que confundi-los é o defeito que este pacote evita

| Eixo | Vocabulário | Granularidade | Onde vive hoje |
| --- | --- | --- | --- |
| `PipelineStage` | Prospecção → Qualificação → Proposta → Negociação → Ganho/Perdido | uma **Opportunity** | Comercial |
| `JourneyPhase`/`ProjectPhase` (FDD 011) | Welcome → Launch Session → Prove → Activation → Assisted Evolution → Scale → Optimize | um **Project** | `ProjectDetailPage.tsx:698` (`JourneySection`) |
| **Escada FDE** (esta issue) | Discover → Prioritize → [ Technical Feasibility ] → Prove → Scale → Optimize | uma **conta** (`Client`), atravessando várias Opportunities | **não existe** |

A autoridade é `docs/metodologia-fde.md:50-53`: *"cada degrau é uma **Opportunity separada na mesma
conta** (Account ≠ Opportunity)"*. A escada FDE é, portanto, **eixo novo, no nível da conta**.

`Welcome` **não** é `Discover`: Welcome é o onboarding de um projeto já vendido; Discover é
diagnóstico anterior à existência do projeto, e é uma venda própria ("Discovery Sprint"). A jornada
de entrega da FDD 011 **fica exatamente como está** e não é renomeada, reordenada nem tocada.

**A consequência que o quadro precisa deixar visível:** a escada da conta **contém** as jornadas de
entrega dos projetos que a realizam. Não são concorrentes; são aninhadas. Por isso o degrau ativo é
o único expandido, e por isso a jornada aparece dentro dele — recuada, em superfície sutil, com
tipografia menor e **referenciada, não redesenhada**.

A Issue #42 escreve "each project". A leitura desta revisão é que o degrau **é realizado por** um
projeto e que cada projeto continua expondo a fase canônica de entrega dele (FDD 011, já entregue);
o que muda é o **nível** em que a escada existe. Isso é decisão de modelagem tomada antes deste
pacote e está registrado aqui como decisão, não como pergunta.

## A regra que este pacote existe para decidir

**"Pulada" e "não vendido" não podem parecer a mesma coisa.** As duas deixam o degrau sem projeto,
e a leitura ingênua desenha as duas em cinza. Mas *pulada* é uma decisão registrada — alguém olhou
e disse que a tecnologia era sabida — e *não vendido* é ausência de decisão. Confundi-las apaga
exatamente a informação que a opcionalidade do Feasibility existe para carregar
(`metodologia-fde.md:38-40`).

A decisão é separá-las **por estrutura, não por tinta**:

| Distinção | Pulada | Não vendido |
| --- | --- | --- |
| Marcador | sólido, preenchido, com o traço de desvio | oco, contorno tracejado, vazio |
| Trilho que sai dele | **contínuo** | **tracejado** |
| Corpo | borda cheia, superfície branca | borda tracejada, sem preenchimento |
| Conteúdo | **motivo + autor + carimbo**, obrigatórios | "Nenhuma decisão registrada" |
| Selo | `.state--off` "Pulada" | `.state--off` "Não vendido" |

**O matiz é o mesmo de propósito.** Nenhuma das duas é aviso nem falha, então pintar uma de âmbar
mentiria sobre a gravidade; e distinguir por cor exigiria matiz novo, que `pulse-design-system.md`
proíbe em texto ("Não inventar matiz"). O trilho contínuo através do degrau pulado é a peça central:
a conta **passou** por aquele ponto e alguém decidiu ali, enquanto no degrau não vendido a escada
ainda não chegou. As duas aparecem **lado a lado** na seção 2 do quadro.

## Quem está esperando — e por que dois valores não bastam

Hoje o produto só sabe dizer `provider` ou `client`:

```python
# backend/apps/core/models.py:301-303
class Party(models.TextChoices):
    PROVIDER = "provider", "Fornecedor"
    CLIENT = "client", "Cliente"
```

Esses dois valores são de `WorkItem` (`models.py:315`) e de `Pendencia` (`models.py:502-504`), e
**não servem** para esta superfície: não distinguem *engenharia* de *Biahflow*, não têm lugar para
*dependência externa*, e não nomeiam o **Human Gate** — que é o valor mais importante e o único que
hoje **não tem nome em lugar nenhum do sistema**.

| Valor | Pele | Novo? | Por que esta pele |
| --- | --- | --- | --- |
| **Biahflow** | `.state--0` (informativo) | não | É a bola em casa. Normal, não é aviso. |
| **cliente** | `.state--2` (aviso) | não | Parado esperando quem não trabalha para nós — é o âmbar que faz alguém cobrar. |
| **engenharia** | **`.eng-ref`** | **sim** | Deliberadamente **fora** da família `.state`: quando a bola está com a engenharia, o dono é a projeção do GitHub, e a regra abaixo diz que essa fonte nunca usa a pele do negócio. |
| **dependência externa** | `.state--off` (neutro) | não | Não é aviso nem falha: é *ausência de agência* — nenhum dos dois lados pode destravar. `.state--off` já é o papel de "sem responsável". A gravidade quem diz é o estado do degrau. |
| **Human Gate** | **`.state--gate`** — `brand-500` sólido, texto branco | **sim** | A única pastilha sólida do produto, e o único uso do clay chapado fora do anel de foco. O acento vale por ser raro; o gate humano é o lugar mais caro de perder de vista. |

Os cinco são **legíveis sem abrir nota nenhuma**: rótulo por extenso, ícone próprio e pele própria.
Nenhum depende de `title` ou de hover — `title` não chega ao teclado nem ao toque.

## Estado de negócio ≠ estado de engenharia

**Redondo e tinto = estado de negócio, do qual o Pulse é a fonte. Quadrado, com borda e
monoespaçado = projeção do GitHub, da qual o Pulse é só espelho.** A separação é estrutural e não
de tom, para que uma cópia acidental não produza a pele errada e para que nenhuma tinta nova seja
necessária. A pele de engenharia carrega sempre a proveniência — repositório, número, referência,
momento da observação — e diz "projeção possivelmente velha" em vez de inventar status; é o
contrato da Issue #41 (`[Integration] Project GitHub delivery state into Pulse…`), aqui só se
desenha o lugar onde ele aparece.

A seção 4 do quadro desenha o caso em que os dois discordam: **PR `merged`, CI verde, e o degrau
continua `Ativo`**. Nenhuma regra desta superfície equipara `PR merged` a `DONE` de entrega — um
degrau só fecha por decisão de gate registrada (`metodologia-fde.md:42-48`), e a Issue #42 exclui
explicitamente *"automatic phase transitions driven only by PR merge"*.

## A primitiva que falta — provavelmente a maior contribuição deste pacote

**Não existe primitiva de linha do tempo ou de *stepper* em `frontend/src/index.css`.** Confirmado
por busca:

```console
$ grep -rn "timeline\|stepper" frontend/src/index.css
$ echo $?
1
```

Enquanto isso, a `JourneySection` desenha os degraus dela com literal Tailwind escrito à mão:

| Onde | Literal hoje | O que isso significa |
| --- | --- | --- |
| `ProjectDetailPage.tsx:722` | `rounded-full px-3 py-1.5 text-xs font-semibold` | Um `.state` reescrito à mão, com padding e corpo diferentes do original. |
| `ProjectDetailPage.tsx:722` (a mesma linha) | `bg-ink text-white` para a fase ativa | Um quinto tom de selo fora da família `.state--*`, que ninguém sabe que existe. |
| `ProjectDetailPage.tsx:729` | `rounded-2xl border bg-slate-50/60 p-4` | Um cartão *quase* igual ao `.panel` — 16 px de raio contra 12, cinza frio contra `surface-subtle`. |
| `ProjectDetailPage.tsx:764` | `rounded-2xl border border-dashed p-4` | O tracejado do gate, também sem nome. |
| `ProjectDetailPage.tsx:731` · `ClientDetailPage.tsx:179` | `text-xs font-semibold uppercase tracking-wide text-accent` | O `.eyebrow` reescrito à mão, **nos dois** lugares que já dizem "Você está aqui" — e ainda no apelido `accent` em vez de `brand-*`. |

Isso colide com a ADR 0026 e com `frontend/src/test/primitivas.test.ts`, **cuja allowlist nasce
vazia** (`primitivas.test.ts:19`). Construir a escada FDE com mais literal do mesmo tipo duplicaria
a dívida em vez de pagá-la, e a segunda definição de "concluído" divergiria da primeira em silêncio
— que é exatamente o defeito que a ADR 0026 existe para pegar.

**Proposta deste pacote, como valor NOVO e explicitamente parte do que está sendo aprovado:**

| Classe | Papel |
| --- | --- |
| `.timeline` | A trilha: recuo do trilho, espaçamento entre degraus, `list-style` zerado. É `<ol>`, porque a ordem é o significado. |
| `.timeline-step` | Um degrau: posiciona marcador e corpo e desenha o segmento de trilho que sai dele. |
| `.timeline-marker` | O nó sobre o trilho. |
| `.timeline-body` | O cartão do degrau — raio de cartão (12 px) e `--shadow-card`, iguais aos do `.panel`. |
| `.timeline-step--done` `--active` `--future` `--skipped` `--blocked` `--gate` `--cancelled` | As sete variantes de estado. **Mudam forma e continuidade do trilho**; a tinta continua vindo de `.state--*`. |
| `.timeline--nested` | A trilha subordinada dentro do degrau ativo: recuo, trilho de 1 px, marcador de 13 px, superfície `surface-subtle`. |
| `.timeline--compact` | A escada inteira numa linha, para a superfície B. |

Ela é a primitiva que faltava, e a `JourneySection` existente **passa a ser candidata a
consumi-la** — mas isso é **reserva, não escopo**: refatorar a jornada de entrega não é esta issue,
e fazê-lo de carona misturaria duas fatias que falham por motivos diferentes. A primitiva nasce
**já com consumidor** (a escada da conta), como a invariante do repositório exige.

O nome segue a casa: hífen para o filho (`.panel-heading`, `.row-main`, `.popover-head`) e `--`
para o modificador (`.panel--flush`, `.metric-card--dark`, `.nav-item--active`).

## Proveniência dos valores visuais

| Valor | Origem | Novo? |
| --- | --- | --- |
| Toda a paleta usada (`ink`, `muted`, `line`, `line-strong`, `canvas`, `surface`, `surface-subtle`, `brand-50/200/500/700`, `danger*`, `success*`, `warning*`, `info*`) | `docs/design/pulse-design-system.md` · `index.css` `@theme` | não — **nenhum matiz novo** |
| Papéis tipográficos (`.type-title`/`-body`/`-label`/`-meta`), raio (4 detalhe · 8 controle · 12 cartão) e elevação (`--shadow-card`, `--shadow-raised`) | DAP GH-19 r2 (fundações normativas) · ADR 0043 | não |
| `.panel`, `.panel--flush`, `.panel-heading`, `.panel-heading--icon`, `.panel-rows`, `.row`, `.row-main` | `index.css` `@layer components` | não |
| A copy "Você está aqui" para a fase corrente | `ClientDetailPage.tsx:179` · `ProjectDetailPage.tsx:731` — já é a palavra do produto | não |
| `.eyebrow` como a classe que a desenha | `index.css` — os dois sites acima escrevem hoje o **literal** (`text-xs … text-accent`) em vez da primitiva; aqui usa-se a primitiva | não |
| `.state--0` / `--1` / `--2` / `--3` / `--off` | `index.css` · `pulse-design-system.md` | não |
| `.empty-state`, `.alert--error`, `.metric-icon`, `.back-link` | `index.css` | não |
| Rótulos e variantes do gate (`GO`/`CONDITIONAL GO`/`REDESIGN`/`NO-GO` → `state--1`/`--2`/`--2`/`--3`) | `ProjectDetailPage.tsx:19,23` — **reusar o mapa, não recriá-lo** | não |
| Nomes dos seis degraus, com `[ Technical Feasibility ]` entre colchetes | `docs/metodologia-fde.md:26` | não |
| Esqueleto em `surface-subtle`/`line` com o raio do cartão real | `DashboardPage.tsx:28` | não |
| **`.timeline`, `.timeline-step` (+7 variantes), `.timeline-marker`, `.timeline-body`, `.timeline--nested`, `.timeline--compact`** | — não existe primitiva de *timeline*/*stepper* no `index.css` | **sim — decidido aqui** |
| **Trilho contínuo vs. tracejado como portador de significado** (passou por aqui vs. não chegou aqui) | — | **sim — decidido aqui** |
| **Marcador quadrado (raio de detalhe, 4 px) reservado ao gate** | consome o degrau "4 · detalhe" do contrato r2, que hoje não tem consumidor no shell | **sim — decidido aqui** |
| **`.state--gate`** — `brand-500` sólido com texto branco | tinta existente, **composição nova**: a única pastilha sólida do produto | **sim — decidido aqui** |
| **`.eng-ref`** — raio 4 px, `surface-subtle`, borda `line-strong`, texto `muted` monoespaçado | tintas existentes, **pele nova**: separa projeção de engenharia de estado de negócio | **sim — decidido aqui** |
| **Os cinco rótulos de quem-espera** (`Biahflow`, `Cliente`, `Engenharia`, `Dependência externa`, `Human Gate`) | —; hoje só existem `Fornecedor`/`Cliente` (`models.py:301-303`) | **sim — copy decidida aqui** |
| **Os sete rótulos de estado do degrau** (`Concluído`, `Não vendido`, `Pulada`, `Bloqueado`, `Aguardando decisão de gate`, `Replanejado`, `Sem acesso`) | — | **sim — copy decidida aqui** |
| **Gaveta de histórico por degrau** (`<details>` + `.panel-rows`) | composição de primitivas existentes; a **escolha** por degrau em vez de painel único é proposta | **sim — composição decidida aqui** |
| `.filter-chip` / `.metric-card` | **considerados e não usados**: filtro seria operar numa superfície de varredura, e a escada não é uma métrica | — |

Design system consultado: `docs/design/pulse-design-system.md`, `frontend/src/index.css` e
`docs/design/dap-gh26-r1/README.md`, lidos em 2026-08-27. **Se este pacote e essa fonte divergirem,
a fonte vence e este pacote está velho.**

## Medições de contraste

| Par | Razão | Veredito |
| --- | --- | --- |
| branco sobre `brand-500` — o `.state--gate` | **5,02:1** | Passa AA. Mesmo valor já medido em `pulse-design-system.md`, no sentido inverso. |
| `muted` sobre `surface-subtle` — `.eng-ref` e a trilha aninhada | **6,99:1** | Passa AA com folga. |
| `slate-600` sobre `slate-100` — `.state--off`, que rotula *Pulada*, *Não vendido* e *Sem acesso* | **6,92:1** | Inalterado. Passa AA. |
| `info` sobre `info-50` — dono *Biahflow* | **6,16:1** | Inalterado (r2). |
| `warning` sobre `warning-50` — dono *Cliente* e "parado há 31 dias" | **4,84:1** | Inalterado (r2). Margem fina; **não reduzir o corpo abaixo de 11 px**. |
| `danger` sobre `danger-50` — *Bloqueado* e o alerta de erro | **5,91:1** | Inalterado (r2). |
| `success` sobre `success-50` — *Concluído* e `GO` | **5,21:1** | Inalterado (r2). |
| `line-strong` sobre branco — o trilho e o marcador oco | **1,49:1** | **Reprovaria como texto, e não é texto.** Ver a nota. |
| Marcador ativo `brand-500` sobre branco | **5,02:1** | Passa WCAG 1.4.11 (não-texto, 3:1). |
| Marcador concluído `success` sobre branco | **5,48:1** | Passa 1.4.11. |
| Marcador bloqueado `danger` sobre branco | **6,47:1** | Passa 1.4.11. |

**O trilho é decoração, e por isso não pode ser o único portador de significado.** A regra
`color-contrast` do axe mede texto; um traço de 2 px em `line-strong` passaria despercebido pelo
portão e ainda assim seria ilegível para quem enxerga pouco. Por isso **todo** estado tem rótulo
escrito por extenso e ícone, e nenhuma informação desta superfície existe só na forma do marcador
ou na continuidade do trilho — a distinção visual acelera a leitura, não a substitui. Quando o axe
e o tom discordam, cede o tom.

## Cobertura de a11y — herdada, e é evidência

As duas rotas desta entrega **já estão** na matriz de telas:

```ts
// frontend/e2e/matrix.ts
18:  { path: "/", name: "Visão geral", role: "admin" },
21:  { path: "/clientes/1", name: "Detalhe do cliente", role: "admin" },
```

A matriz alimenta `e2e/a11y.spec.ts` e `e2e/responsive.spec.ts` (FDD 022). **Nenhuma linha nova é
necessária lá**, e o gate de contraste AA — 24 telas × 3 larguras — já cobre estas duas telas no
estado em que a implementação as deixar. É a prova de que a decisão de cor deste pacote será
verificada por portão, e não só por leitura.

O que a matriz **não** cobre e continua sendo obrigação da implementação: a evidência de runtime
desktop/mobile que a classificação `BROWSER_REQUIRED` exige, incluindo a gaveta de histórico com
teclado e o comportamento da trilha aninhada em 390 px.

## Entregue vs. reservado

| Elemento | Esta entrega | Reservado para | Vira real quando |
| --- | --- | --- | --- |
| Escada FDE da conta em `/clientes/:id`, seis degraus | entrega | — | — |
| Os onze estados, cada um rotulado | entrega | — | — |
| Histórico com carimbo e autor | entrega | — | — |
| Os cinco valores de quem-espera, incluindo **Human Gate** | entrega | — | — |
| Bloco compacto por conta na visão geral | entrega | — | — |
| Primitiva `.timeline` e suas variantes | entrega | — | — |
| Chip de projeção de engenharia (`.eng-ref`) | entrega **a pele**; o dado vem da Issue #41 | — | Sem a projeção, o chip **não é desenhado** — não existe versão inerte dele. |
| Projeção da escada para o cliente no **One** | não entrega | One | Existir projeção aprovada voltada ao cliente. A Issue #42 diz que é do One, e que ele não pode virar a fonte operacional interna. |
| `JourneySection` consumindo `.timeline` | não entrega | Issue própria | A primitiva existir e estar em uso na escada da conta. A jornada de entrega **fica intocada** nesta fatia. |
| Transição automática de degrau | não entrega | — | **Nunca por `PR merged`.** A Issue #42 exclui *"automatic phase transitions driven only by PR merge"*, e o gate de quatro saídas é humano por definição. |
| Cobrança/faturamento por degrau | não entrega | Financeiro / Cobrança | Existir decisão de negócio própria. A Issue exclui *"billing/accounting automation"*. |

**Nenhum elemento reservado é desenhado como controle inerte.** O que não entra simplesmente não é
renderizado — não há botão desligado, link morto nem placeholder ligado sem função. Os quatro
rótulos do gate na superfície A são **texto** justamente por isso: o gate se decide na tela do
projeto (`JourneySection`), e desenhar aqui quatro botões inertes seria defeito, não placeholder.

## O que a aprovação NÃO cobre

Aprovação é escopada. O que estiver aqui continua sendo decisão em aberto depois dela:

- **tema escuro** — exige DAP próprio (`pulse-design-system.md`, "Fora deste contrato");
- **a superfície no One** — projeção voltada ao cliente, fora deste repositório e desta issue;
- **a jornada de entrega da FDD 011** — permanece intocada; nada aqui aprova renomear, reordenar
  ou refatorar `JourneyPhase`/`ProjectPhase`;
- **a copy dos mocks** — nomes de conta, pessoas, datas, números de issue/PR e prazos são
  ilustrativos e nunca especificação;
- **o modelo de dados e a migration** — onde mora o degrau, como se liga a
  `Client`/`Opportunity`/`Project`, e como o histórico é persistido são contrato de backend, não
  superfície;
- **as outras telas de produto** — nada aqui autoriza mexer em tela que não seja
  `ClientDetailPage` e `DashboardPage`;
- **qualquer revisão posterior deste pacote** — um pacote materialmente alterado é revisão nova e
  precisa do próprio registro.

## Decisões que este pacote carrega

1. **A escada FDE é da conta, não do projeto** (`metodologia-fde.md:50-53`). A jornada de entrega
   da FDD 011 fica como está e passa a aparecer *aninhada* dentro do degrau ativo.
2. **"Pulada" e "não vendido" separam-se por estrutura, não por tinta.** É a decisão central. A cor
   continua neutra nas duas, porque nenhuma é aviso; distinguir por cor exigiria matiz novo.
3. **Redondo e tinto é negócio; quadrado, bordado e monoespaçado é engenharia.** E nenhuma regra
   equipara `PR merged` a `DONE`.
4. **O Human Gate ganha nome e a pastilha mais forte do produto.** É a decisão mais discutível
   daqui. *Alternativa registrada:* usar `ink` sólido — **rejeitada**, porque colidiria com o
   `bg-ink text-white` que a `JourneySection` já usa para a fase ativa, e as duas coisas diriam a
   mesma forma com sentidos diferentes.
5. **O degrau ativo não leva selo de estado.** Quem diz "ativo" é a expansão e o `.eyebrow`
   "Você está aqui". Um selo azul aqui competiria com o dono *Biahflow*, também azul.
6. **O histórico mora numa gaveta por degrau**, e não num painel único ao pé da tela.
   *Alternativa registrada:* painel único — **rejeitada**, porque separa a transição do degrau a
   que se refere, e a pergunta que se faz olhando um degrau é sempre "o que aconteceu *aqui*".
7. **A primitiva de linha do tempo é proposta deste pacote**, e não linguagem já estabelecida.
   Aprovar esta revisão aprova acrescentá-la ao `index.css`.
8. **Aprovar o visual não aprova a copy.** Os doze rótulos novos estão escritos por extenso no
   quadro exatamente para que sejam decididos em separado.

## Questões em aberto

Nada aqui é resolvido por agente durante a implementação.

- **O limiar de "parado há N dias"** não é decidido aqui. O quadro desenha 31 dias em âmbar e 4 e 9
  em neutro, mas o corte é regra de negócio, não de design.
- **Um degrau pode compartilhar Opportunity com o degrau anterior?** O quadro desenha *Discover* e
  *Prioritize* saindo da mesma venda ("Discovery Sprint · Vale"), que é o caso real mais comum. Se
  o modelo exigir 1:1 entre degrau e Opportunity, a linha "vendido em" muda de forma.
- **O que exatamente o papel `delivery` não pode ver** na escada — se o nome do degrau realizado por
  projeto alheio já é informação demais. O quadro mostra a *forma* da escada e esconde o *conteúdo
  comercial*; a regra de escopo em si é `Project.objects.visible_to` e não se reescreve
  (RFC 0003, ADR 0010, FDD 018).
- **Ordenação e recorte do bloco da visão geral**: quantas contas aparecem, e se a ordem é por
  tempo parado ou por valor.
- **Notificação** quando um Human Gate fica pendente além do limiar.
- **Reconciliação do vocabulário da Issue** ("delivery journey" para o que aqui é a escada da
  conta) no texto da própria Issue e no `roadmap.md`: não é feita nesta fatia.

## Notas para quem implementa

- **Intencional e a preservar:** a ordem dos seis degraus e a grafia `[ Technical Feasibility ]`
  como está em `metodologia-fde.md:26`; a continuidade do trilho como portadora de significado; o
  rótulo por extenso em **todo** estado, nunca só o marcador; o mapa de gate reusado de
  `ProjectDetailPage.tsx:19,23`, nunca um segundo mapa; a jornada da FDD 011 **referenciada e não
  redesenhada**; e `Project.objects.visible_to` como a única fonte do escopo de entrega.
- **Ilustrativo e a não tratar como especificação:** os nomes de conta ("Metalúrgica Vale",
  "Cooperativa Sul", "Rede Aurora", "Transportes Iguaçu"), as pessoas ("Daniel Campos",
  "Ana Ribeiro"), todas as datas, os números de issue e PR, os prazos, os ícones desenhados à mão
  no quadro e o recorte exato dos espaçamentos.
- **Use a primitiva; não reescreva o literal.** O CSS do `board.html` é *mock*: ele reproduz as
  primitivas para que o arquivo abra sozinho. No produto escreve-se `.panel`, `.state--*`,
  `.empty-state` e a `.timeline` nova — a guarda é `src/test/primitivas.test.ts`, e a allowlist
  dela nasce vazia.
- **Mapa de estado devolve variante, nunca cor.** `"state--1"`, jamais `"bg-emerald-50 …"`. Vale
  igual para as variantes de `.timeline-step`.
- **Semântica antes de estilo.** A escada é `<ol>` porque a ordem é o significado; o marcador é
  decorativo (`aria-hidden`) e o estado vem do texto; o alerta de erro leva `role="alert"`; e
  nenhuma informação depende de `title` ou de hover.
- **Constraints que o quadro não consegue mostrar:** ordem de foco, comportamento de teclado na
  gaveta de histórico, leitor de tela, truncamento com nome de conta longo, *reflow* entre 390 e
  1280 px, e movimento. Tudo isso é validado em runtime (`BROWSER_REQUIRED`), não aqui. A trilha
  aninhada é o ponto mais frágil em 390 px: dois recuos somados comem a largura útil, e a decisão
  de como ela colapsa é de runtime.
- **Este pacote não é fonte.** Depois da aprovação, o que vira contrato consultável é
  `docs/design/pulse-design-system.md` — que ganha as linhas da `.timeline`, do `.state--gate` e do
  `.eng-ref`. Enquanto a aprovação não sai, aquele arquivo **não muda**.
