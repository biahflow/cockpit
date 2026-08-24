# Pulse Design System — contrato de consumo

**ADR:** [0041](../adr/0041-pulse-design-system-e-validacao-visual.md)
**DAP:** [r1](dap-gh19-r1/README.md), aprovado 2026-08-24 (visual + valores da tabela)
**Fonte dos tokens:** `frontend/src/index.css` (`@theme` / `@theme inline` / `@layer components`)

Este é o contrato para telas novas e alterações visuais no Pulse. A forma já existente (ADR 0024–0026) continua; r1 só nomeia o que já estava medido e acrescenta tokens semânticos sem mudar o matiz.

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
| `canvas` | `#fafaf9` | fundo da página |
| `brand-50` | `#fdf1ec` | tinte da marca |
| `brand-100` | `#fadfd4` | tinte mais carregado |
| `brand-200` | `#dd8b62` | único acento que sobrevive a fundo escuro |
| `brand-500` | `#bd4a30` | acento clay |
| `brand-600` | `#a8412a` | hover da marca |
| `brand-700` | `#9c3c26` | texto sobre `brand-50` |
| `brand-900` | `#5c2317` | clay profundo (login) |
| `danger` | `#b91c1c` | erro e ação destrutiva — **não é marca** |
| `success` / `success-50` | `#047857` / `#ecfdf5` | semântico; hexes emerald-700/50 |
| `warning` / `warning-50` | `#b45309` / `#fffbeb` | semântico; hexes amber-700/50 |
| `info` / `info-50` | alias de `brand-700` / `brand-50` | informativo |

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
| `.state--3` | perigo (`red-50` + `text-danger`) |
| `.state--off` | neutro (arquivado, desligado) |
| `.alert--error` / `.alert--ok` | alerta de tela, não selo |
| `.empty-state` | vazio |
| `.form-label` + `field` | rótulo e campo |

Mapa de estado devolve **variante** (`"state--1"`), nunca a cor (`"bg-emerald-50 …"`).

## Contraste

Quando o axe e o tom discordam, cede o tom. Gate: `frontend/e2e/a11y.spec.ts` (WCAG 2.0/2.1 A e AA).

Medições já registradas: `ink` sobre branco 18,9:1; `brand-500` sobre branco 4,96:1; `brand-500` sobre `ink` **3,82:1** (reprova — use `brand-200`); `brand-700` sobre `brand-50` 6,1:1; `muted` sobre `canvas` 7,4:1; `danger` sobre branco 5,9:1 e sobre `red-50` 5,6:1.

## Página de prova

`/design-system` é a galeria viva, só admin, fora do menu lateral. O caminho de chegada é Configurações. Não-admin vê `.empty-state` sem botão primário.

## Fora deste contrato

Dark theme, redesign das telas existentes, clone do One, identidade Nexus, copy dos mocks do DAP.
