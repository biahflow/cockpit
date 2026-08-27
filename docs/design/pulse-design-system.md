# Pulse Design System — contrato de consumo

**ADR:** [0041](../adr/0041-pulse-design-system-e-validacao-visual.md) · [0043](../adr/0043-a-marca-pulse-no-shell-e-as-fundacoes-r2-consumidas.md) · [0047](../adr/0047-a-escada-fde-e-eixo-da-conta-e-a-jornada-da-entrega-fica-onde-esta.md)
**DAP:** [r2](dap-gh19-r2/README.md), aprovado 2026-08-24 (fundações normativas) · [GH-26 r1](dap-gh26-r1/README.md), aprovado 2026-08-25 (marca e shell) · [GH-41 r1](dap-gh41-r1/README.md), aprovado 2026-08-27 (papel de código) · [GH-42 r1](dap-gh42-r1/README.md), aprovado 2026-08-27 (linha do tempo, `.state--gate` e `.eng-ref`)
**Fonte dos tokens:** `frontend/src/index.css` (`@theme` / `@theme inline` / `@layer components`)

Este é o contrato para telas novas e alterações visuais no Pulse. A forma já existente (ADR 0024–0026) continua; r2 explicita a hierarquia compacta para operação e os tokens semânticos aprovados.

**O shell consome o contrato desde a ADR 0043.** Até ali r2 era declaração: os papéis tipográficos e o contrato de raio existiam em `@theme` e o shell escrevia `text-[13px]` e `rounded-xl` à mão. Sidebar, gaveta, topbar, popovers, campos e a visão geral passaram a consumir os papéis e os raios. As duas exceções ao contrato de raio estão declaradas: `.icon-button` mantém `size-10` por WCAG 2.5.8 (muda o raio, não o alvo) e `.filter-chip` segue `rounded-full`, reservado no DAP GH-26 r1 para quando Leads e Clientes entrarem em escopo.

## Identidade

- O nome é **Pulse Design System**. `Nexus` não é produto, namespace, token nem identidade.
- Pulse não clona o One. Princípios compartilhados não implicam a mesma pele.
- O que identifica este portal é o matiz **clay** (`#bd4a30`). O portal do cliente é o roxo. Nunca use um no outro.
- **O produto se apresenta como Pulse; Biahflow é a casa** (ADR 0043). Marca no shell é o asset canônico consumido pelo `PulseBrand` — `frontend/src/assets/brand/`, nunca SVG colado inline. Superfície escura usa `pulse-mark-inverse.svg` (`tone="dark"`): o clay sobre `brand-900` dá 2,45:1 e o mark some. O mark é decorativo, então **o axe não pega isto** — a regra `color-contrast` mede texto.

## Tokens

Valores novos só entram com DAP aprovado. Não inventar matiz. Não acrescentar `brand-300`.

| Token | Hex / origem | Papel |
| --- | --- | --- |
| `ink` | `#12110f` | texto, títulos, **botão primário** |
| `muted` | `#57534e` | texto secundário |
| `line` | `#e7e5e4` | borda |
| `line-strong` | `#d6d3d1` | borda enfatizada |
| `canvas` | `#fafaf9` | fundo da página |
| `surface` / `surface-subtle` | `#ffffff` / `#f5f5f4` | superfícies |
| `brand-50` | `#fdf1ec` | tinte da marca |
| `brand-100` | `#fadfd4` | tinte mais carregado |
| `brand-200` | `#dd8b62` | único acento que sobrevive a fundo escuro |
| `brand-500` | `#bd4a30` | acento clay; **chapado só no `.state--gate` e no anel de foco** |
| `brand-600` | `#a8412a` | hover da marca |
| `brand-700` | `#9c3c26` | texto sobre `brand-50` |
| `brand-900` | `#5c2317` | clay profundo (login) |
| `danger` / `danger-50` | `#b91c1c` / `#fef2f2` | erro e ação destrutiva — **não é marca** |
| `success` / `success-50` | `#047857` / `#ecfdf5` | semântico; hexes emerald-700/50 |
| `warning` / `warning-50` | `#b45309` / `#fffbeb` | semântico; hexes amber-700/50 |
| `info` / `info-50` | `#1d4ed8` / `#eff6ff` | informativo, separado da marca |
| `--font-mono` | pilha do sistema (`ui-monospace`…) | **o papel de código** (DAP GH-41 r1). Sem webfont: a mono aparece em sete caracteres de SHA, e a Inter já custa um download |

`accent` e `accent-50` são apelidos de migração para `brand-500` / `brand-50`. Em código novo escreva `brand-*`.

## Primitivas

Use a classe. Não reescreva o literal. A guarda é `frontend/src/test/primitivas.test.ts` (ADR 0026); a allowlist nasce vazia.

| Classe | Uso |
| --- | --- |
| `.page-head` / `.eyebrow` | cabeçalho de tela |
| `.panel` / `.panel--flush` | cartão |
| `.btn` | primário **ink** |
| `.btn--secondary` | contorno |
| `.btn--danger` | confirmação destrutiva já pedida |
| `.btn--secondary-danger` | arquivar: neutro em repouso, vermelho na intenção |
| `.type-code` | identificador que se lê caractere a caractere — SHA, `owner/repo#numero`, código de ocorrência. Declara a **família** e só ela: o corpo vem do papel ao lado (`.type-body`, `.type-meta`), porque o mesmo identificador aparece em dois tamanhos na mesma linha |
| `.state--0` | informativo (`info`) |
| `.state--1` | sucesso |
| `.state--2` | aviso |
| `.state--3` | perigo (`danger-50` + `danger`) |
| `.state--off` | neutro (arquivado, desligado) |
| `.alert--error` / `.alert--ok` | alerta de tela, não selo |
| `.empty-state` | vazio |
| `.form-label` + `field` | rótulo e campo |
| `.metric-card--dark` | o cartão escuro da visão geral (ADR 0043) |
| `.metric-icon--danger` / `--dark` | tinta do quadrado de ícone; escreva a variante, não `bg-red-50` |
| `.user-button` | o botão de usuário da topbar |
| `.state--gate` | **a única pastilha sólida do produto**: `brand-500` chapado, texto branco. Reservada ao Human Gate — o acento vale por ser raro |
| `.eng-ref` | projeção de engenharia: raio de detalhe, `surface-subtle`, borda `line-strong`, texto `muted` monoespaçado. **Fora da família `.state` de propósito** |
| `.timeline` + `.timeline-step` + `.timeline-marker` + `.timeline-body` | linha do tempo. É `<ol>`, porque a ordem é o significado; o marcador é decorativo (`aria-hidden`) |
| `.timeline-step--done` `--active` `--future` `--skipped` `--blocked` `--gate` `--cancelled` | as sete variantes de degrau. **Mudam forma e continuidade do trilho; a tinta continua vindo de `.state--*`** |
| `.timeline--nested` | a trilha subordinada dentro de um degrau: recuo, trilho de 1px, marcador de 13px, `surface-subtle` |
| `.timeline--compact` | a escada inteira numa linha, para varrer uma lista. Decorativa — o rótulo por extenso vai no texto ao lado |

Mapa de estado devolve **variante** (`"state--1"`), nunca a cor (`"bg-emerald-50 …"`). Vale igual
para as variantes de `.timeline-step`.

**O trilho carrega informação e nunca a carrega sozinho** (ADR 0047, DAP GH-42 r1). Contínuo = a
escada passou por aqui; tracejado = não chegou aqui — é o que separa um degrau *pulado* (houve
decisão) de um *não vendido* (não houve), sem inventar matiz para isso. Mas a regra `color-contrast`
do axe mede **texto**, e um traço de 2px em `line-strong` (1,49:1) passaria pelo portão e ainda
assim seria ilegível para quem enxerga pouco: por isso todo estado leva rótulo escrito por extenso,
e nenhuma informação existe só na forma do marcador.

## Contraste

Quando o axe e o tom discordam, cede o tom. Gate: `frontend/e2e/a11y.spec.ts` (WCAG 2.0/2.1 A e AA).

Medições aprovadas em r2: `ink`/`canvas` 18,07:1; `muted`/`canvas` 7,30:1; `brand-500`/branco 5,02:1; `brand-700`/`brand-50` 6,14:1; `brand-200`/`ink` 7,14:1; sucesso 5,21:1; aviso 4,84:1; perigo 5,91:1; informação 6,16:1.

Acrescentadas no GH-41 r1: `.state--off` (`slate-600` sobre `slate-100`) **6,92:1** — é o par que carrega a regra do obsoleto; `ink` sobre `surface-subtle` 17,30:1 (o SHA dentro do chip de código); `brand-600` sobre `surface` 6,08:1 (o link canônico da referência).

Acrescentadas no GH-42 r1: branco sobre `brand-500` (o `.state--gate`) 5,02:1; `muted` sobre `surface-subtle` (o `.eng-ref` e a trilha aninhada) 6,99:1.

**Estado obsoleto nunca veste a cor do estado observado** (GH-41 r1). Quando o backend diz que a projeção envelheceu, todo selo cai para `.state--off` e o âmbar **troca de lugar** — sai dos selos e vai para a linha de proveniência, que passa a ser o dado principal. Assim o âmbar continua querendo dizer uma coisa só na tela inteira: "atenção neste dado", e não "velho".

## Página de prova

`/design-system` é a galeria viva, só admin, fora do menu lateral. O caminho de chegada é Configurações. Não-admin vê `.empty-state` sem botão primário.

## Fora deste contrato

Tema escuro (exige novo DAP), redesign amplo das telas/shell, clone do One, identidade Nexus, copy dos mocks do DAP.
