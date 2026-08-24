# Pulse Design System — contrato de consumo

**ADR:** [0041](../adr/0041-pulse-design-system-e-validacao-visual.md)
**DAP:** [r2](dap-gh19-r2/README.md), aprovado 2026-08-24
**Fonte dos tokens:** `frontend/src/index.css` (`@theme` / `@theme inline` / `@layer components`)

Este é o contrato para telas novas e alterações visuais no Pulse. A forma já existente (ADR 0024–0026) continua; r2 explicita a hierarquia compacta para operação e os tokens semânticos aprovados.

## Identidade

- O nome é **Pulse Design System**. `Nexus` não é produto, namespace, token nem identidade.
- Pulse não clona o One. Princípios compartilhados não implicam a mesma pele.
- O que identifica este portal é o matiz **clay** (`#bd4a30`). O portal do cliente é o roxo. Nunca use um no outro.

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
| `brand-500` | `#bd4a30` | acento clay |
| `brand-600` | `#a8412a` | hover da marca |
| `brand-700` | `#9c3c26` | texto sobre `brand-50` |
| `brand-900` | `#5c2317` | clay profundo (login) |
| `danger` / `danger-50` | `#b91c1c` / `#fef2f2` | erro e ação destrutiva — **não é marca** |
| `success` / `success-50` | `#047857` / `#ecfdf5` | semântico; hexes emerald-700/50 |
| `warning` / `warning-50` | `#b45309` / `#fffbeb` | semântico; hexes amber-700/50 |
| `info` / `info-50` | `#1d4ed8` / `#eff6ff` | informativo, separado da marca |

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
| `.state--0` | informativo (`info`) |
| `.state--1` | sucesso |
| `.state--2` | aviso |
| `.state--3` | perigo (`danger-50` + `danger`) |
| `.state--off` | neutro (arquivado, desligado) |
| `.alert--error` / `.alert--ok` | alerta de tela, não selo |
| `.empty-state` | vazio |
| `.form-label` + `field` | rótulo e campo |

Mapa de estado devolve **variante** (`"state--1"`), nunca a cor (`"bg-emerald-50 …"`).

## Contraste

Quando o axe e o tom discordam, cede o tom. Gate: `frontend/e2e/a11y.spec.ts` (WCAG 2.0/2.1 A e AA).

Medições aprovadas em r2: `ink`/`canvas` 18,07:1; `muted`/`canvas` 7,30:1; `brand-500`/branco 5,02:1; `brand-700`/`brand-50` 6,14:1; `brand-200`/`ink` 7,14:1; sucesso 5,21:1; aviso 4,84:1; perigo 5,91:1; informação 6,16:1.

## Página de prova

`/design-system` é a galeria viva, só admin, fora do menu lateral. O caminho de chegada é Configurações. Não-admin vê `.empty-state` sem botão primário.

## Fora deste contrato

Tema escuro (exige novo DAP), redesign amplo das telas/shell, clone do One, identidade Nexus, copy dos mocks do DAP.
