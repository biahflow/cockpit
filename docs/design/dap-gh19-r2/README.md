# DAP r2 — Pulse Design System foundations

**Issue:** [#19](https://github.com/biahflow/pulse/issues/19)

**ADR:** [0041](../../adr/0041-pulse-design-system-e-validacao-visual.md)

**Revisão:** 2

**Data da aprovação humana:** 2026-08-24

**Artefato congelado:** `approved-board.png` — SHA-256 `0d7fc05eea0ba4e52d552c53dac17f42ed57308d1b92dd1c377be5429477615a`

## Aprovação

O solicitante aprovou explicitamente a revisão 2 nesta sessão, em 2026-08-24. Esta é a autoridade de design para a implementação da Issue #19. A revisão 1 permanece apenas como histórico e não representa este gate.

## Direção aprovada

**Comando calmo, alerta por exceção.** Interface interna, compacta e precisa: hierarquia por superfícies planas e bordas, raios menores, sombras contidas; clay é identidade, seleção e foco. Informação é azul, separada de marca e perigo.

## Fundações normativas

| Grupo | Valores |
| --- | --- |
| Superfícies | `ink #12110F`, `muted #57534E`, `line #E7E5E4`, `line-strong #D6D3D1`, `canvas #FAFAF9`, `surface #FFF`, `surface-subtle #F5F5F4` |
| Marca | `brand-50 #FDF1EC`, `100 #FADFD4`, `200 #DD8B62`, `500 #BD4A30`, `600 #A8412A`, `700 #9C3C26`, `900 #5C2317` |
| Semântica | sucesso `#047857/#ECFDF5`; aviso `#B45309/#FFFBEB`; perigo `#B91C1C/#FEF2F2`; informação `#1D4ED8/#EFF6FF` |
| Tipo | Inter Variable; display 32/38 650; título 16/24 650; corpo 14/22 400; label 12/16 600; meta 11/16 500; métrica 28/32 650 tabular |
| Espaço | 4, 8, 12, 16, 20, 24, 32, 40, 48 px |
| Raios | 4 detalhe; 8 controles; 12 cartões/popover; `full` só status/avatar; sem botões pill |
| Elevação | base sem sombra; card `0 1px 2px rgba(18,17,15,.06)`; raised `0 8px 24px -12px rgba(18,17,15,.22)`; popover `0 16px 40px -16px rgba(18,17,15,.28)` |

## Interação e acessibilidade

- Foco: outline de 2 px em `brand-500`, offset 2 px.
- Primário: `ink`, hover `brand-700`, active `brand-900`.
- Secundário: branco/borda; hover `brand-50` + `brand-500`; active `brand-100` + `brand-600`.
- Selecionado: `brand-50` / `brand-700` / `brand-500`. Desabilitado: `line`/`muted`, sem depender de opacidade.
- Todo estado comunica ícone, texto e cor; controles têm 44 px; alvo mínimo é 24 px.
- Contrastes calculados: ink/canvas 18.07; muted/canvas 7.30; brand-500/branco 5.02; brand-700/brand-50 6.14; brand-200/ink 7.14; sucesso 5.21; aviso 4.84; perigo 5.91; informação 6.16.

## Escopo

Entrega: tokens, tema claro, contrato, página de prova e primitivas mínimas. Fora: redesign amplo/shell, tema escuro, motion, One, Nexus, funcionalidades, dados e copy nova. Um futuro tema escuro exige novo DAP aprovado.

## Evidência

| Arquivo | Conteúdo |
| --- | --- |
| [approved-board.png](approved-board.png) | quadro visual aprovado e congelado |
| [board.html](board.html) | transcrição auto-contida das decisões aprovadas |
| [browser-desktop.png](browser-desktop.png) | runtime desktop da revisão em análise |
| [browser-mobile.png](browser-mobile.png) | runtime responsivo da revisão em análise |
| [focus-desktop.png](focus-desktop.png) | botão primário com foco por teclado |

Capturas produzidas por `PULSE_DAP_EVIDENCE_DIR=docs/design/dap-gh19-r2 npx playwright test e2e/design-system.spec.ts --project=desktop` e `--project=mobile`, após lint, Vitest e build verdes. O próximo commit registra esta revisão de evidência imutável.
