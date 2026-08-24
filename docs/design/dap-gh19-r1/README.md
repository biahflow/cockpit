# DAP r1 — Pulse Design System foundations

> **Superado pela [revisão 2](../dap-gh19-r2/README.md).** A aprovação histórica desta revisão não é a autoridade do Design Approval Gate atual da Issue #19.

**Issue:** [#19](https://github.com/biahflow/pulse/issues/19)
**ADR:** [0041](../../adr/0041-pulse-design-system-e-validacao-visual.md)
**Revisão:** 1
**Data da aprovação humana:** 2026-08-24

## Aprovação

Humano aprovou em 2026-08-24: **Pulse Design System foundations r1 (visual + valores da tabela)**.

A aprovação cobre o visual da revisão 1 e os valores da tabela de tokens (hexes, papéis de tipo, espaço, raio, elevação). Não cobre texto inventado nos mocks.

## O que esta revisão formaliza

A linguagem clay **já medida** no produto (ADR 0024, ADR 0025, ADR 0026, FDD 022):

- primário **ink** (`#12110f`), não laranja;
- acento clay `#bd4a30` (`brand-500`) e a escala `brand-50…900` **sem `brand-300`**;
- perigo **vermelho** (`#b91c1c`), distinto da marca;
- sucesso `#047857` / `#ecfdf5` e aviso `#b45309` / `#fffbeb` — hexes emerald-700/50 e amber-700/50, mudança estrutural não visual;
- info = `brand-700` / `brand-50`.

O artefato de aprovação visual é evidência da decisão, não o código de produção.

## Capturas da revisão

| Arquivo | Conteúdo |
| --- | --- |
| [foundations.jpg](foundations.jpg) | Paleta, tipo, espaço, raio, elevação |
| [primitives.jpg](primitives.jpg) | Botões, selos, campo, alertas |
| [states.jpg](states.jpg) | Loading, empty, error, unauthorized (mock) |
| [surface.jpg](surface.jpg) | Superfície operacional (mock) |
| [mobile.jpg](mobile.jpg) | Recorte estreito (mock) |
| [board.html](board.html) | Quadro auto-contido com os hexes da tabela |

## Explicitamente não aprovado

- **Copy dos mocks.** Os textos de "handoff", "fila de engenharia", "provisionar issue" etc. são ilustração; não viram copy de produto.
- **Fila de engenharia.** Superfície de produto fora desta fatia.
- **Dark theme.** Não há tema escuro nesta revisão.
- **Redesign de telas.** As 21 telas existentes e o shell não foram redesenhados.

## Implementação correspondente

Contrato de consumo: [`docs/design/pulse-design-system.md`](../pulse-design-system.md).
Página de prova no produto: `/design-system` (admin).
Evidência renderizada da implementação: [browser-desktop.png](browser-desktop.png), [browser-mobile.png](browser-mobile.png).
