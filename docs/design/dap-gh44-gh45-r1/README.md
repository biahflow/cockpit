# Design Approval Package — GH-44/GH-45 · Eyebrows, rótulos e estados

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **1**
Status: **Approved**
Data: 2026-08-31
Produzido por: Codex, sob `workflows/design-approval.md`

> Este artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> o código da aplicação.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | Decisões e limites da revisão 1 conforme `board.png` |
| Aprovado por | Daniel Campos, via conversa com Codex |
| Data | 2026-08-31 |
| Revisão aprovada | 1 |
| Explicitamente **não** aprovado | copy nova; redesign de telas; mudanças fora dos literais inventariados nas issues #44 e #45 |

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização autocontida, sem build, toolchain ou rede. |
| `board.png` | Captura congelada da revisão 1. É a ela que a aprovação se refere. |

SHA-256 de `board.png`: `b8bb67cd8472337591a49900088b3855bbc2c6d935621b1a5b094684e6b1d23e`.

## Superfícies e estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Eyebrow claro em detalhe de cliente/projeto | “Você está aqui” | sim — antes e proposta |
| Eyebrow escuro no login | “Operação Biahflow” | sim — antes e proposta |
| Rótulo neutro de seção | quatro consumidores inventariados | sim — antes e proposta |
| Cabeçalho de tabela neutro | um consumidor inventariado | sim — preservado como literal deliberado |
| Pastilhas `.state` | informativo, sucesso, aviso, perigo e neutro | sim |
| Pastilha da fase atual | ativo | sim — antes e proposta |
| Vazio, erro, não autorizado e carregando | — | não — as issues não alteram conteúdo, fluxo nem estado de tela; só a forma das primitivas já renderizadas |

## Proveniência dos valores visuais

| Valor | Fonte | Novo? |
| --- | --- | --- |
| `.eyebrow`: 11px, 700, caixa alta, tracking 0,18em, `brand-500` | `frontend/src/index.css` · ADR 0026 | não |
| `brand-200` sobre `brand-900` | `docs/design/pulse-design-system.md` · ADR 0025 | não |
| `.state`: 11px, 600, `px-2.5 py-1`, raio full | `frontend/src/index.css` · ADR 0026 | não |
| estados `--0`…`--3` e `--off` | Pulse Design System | não |
| papel *label*: 12/16, 600 | fundações r2, `docs/design/pulse-design-system.md` | não |
| `.eyebrow--dark` | composição de `.eyebrow` com o token existente `brand-200` | **sim — variante decidida aqui** |
| `.section-label` | papel *label* + caixa alta/tracking já presentes nos quatro consumidores + `muted` | **sim — primitiva decidida aqui** |
| `.state--active` | geometria de `.state` + tokens existentes `ink`/branco | **sim — variante decidida aqui** |

Design system consultado em 2026-08-31: `docs/design/pulse-design-system.md`, ADRs 0024, 0025,
0026 e 0041, e `frontend/src/index.css`. Se este pacote divergir dessas fontes, as fontes vencem.

## Entregue vs. reservado

| Elemento | Esta entrega | Reservado para | Vira real quando |
| --- | --- | --- | --- |
| Grupo A da #44 usa `.eyebrow` | entrega | — | — |
| Grupo B usa `.eyebrow eyebrow--dark` | entrega | — | — |
| Quatro rótulos neutros do Grupo C usam `.section-label` | entrega | — | — |
| Cabeçalho de tabela em `ProjectsPage` | preserva literal | primitiva de tabela | houver um pacote de tabela com mais de um consumidor |
| Seis bases manuais da #45 usam `.state` | entrega | — | — |
| Fase atual usa `.state--active` | entrega | — | — |
| Outros literais ou redesign das telas | não entrega | issues próprias | contrato próprio aprovado |

## Decisões que este pacote carrega

1. **A geometria da `.eyebrow` fica única.** Os dois “Você está aqui” passam a 11px/700/0,18em.
2. **Superfície escura muda só a tinta.** `.eyebrow--dark` compõe a base e troca `brand-500` por
   `brand-200`; tamanho, peso e tracking deixam de formar uma segunda primitiva.
3. **Rótulo neutro é outro papel.** `.section-label` formaliza os quatro consumidores em 12px/600,
   caixa alta, tracking `wide` e `muted`; não usa a tinta da marca.
4. **Um cabeçalho de tabela não cria primitiva sozinho.** O único caso sem peso permanece literal,
   porque é semântica de tabela, não rótulo de seção.
5. **A base de toda pastilha é `.state`.** As seis geometrias locais convergem para
   11px/600/`px-2.5 py-1`.
6. **“Ativo” é estado nomeado, não cor crua.** `.state--active` usa `ink`/branco sobre a base.

## Questões em aberto

- Nenhuma dentro do recorte proposto. Rejeitar qualquer decisão acima produz uma revisão 2 antes
  de implementação.

## Notas para quem implementa

- Preservar textos e comportamento; só as classes dos sites inventariados mudam.
- A captura usa dados ilustrativos. Os rótulos reais continuam os do produto.
- A guarda deve reconhecer a forma das primitivas independentemente de ordem de utilitários ou de
  variante interpolada, sem tornar botões, pontos ou barras de progresso falsos positivos.
- Runtime deve provar 390, 768 e 1280 px e passar axe; foco, teclado e fluxos não mudam.
