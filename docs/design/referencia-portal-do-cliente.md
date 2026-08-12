# A referência: o design system do portal do cliente

De onde o redesenho da ADR 0024 foi portado, e o bastante para refazer o port sem adivinhar.

**Este arquivo não é backup do portal do cliente.** Aquele repositório não foi alterado por
esta fatia — ele é a fonte, não o alvo. O que está aqui é a fotografia do que copiamos, para
que "portamos do portal do cliente" seja uma afirmação conferível em vez de uma lembrança.

## A fonte

| | Primeiro port (ADR 0024) | Segundo port (ADR 0025) |
|---|---|---|
| Repositório | `biahflow-portal-cliente` | idem |
| Arquivo | `app/globals.css` (**761 linhas**) | idem |
| `HEAD` na data do port | `90417bc` | `e95d8b2` |
| Data | 07/08/2026 | 07/08/2026 |

*Ressalva honesta:* na data do primeiro port o `globals.css` daquele repo tinha alteração **não
commitada** — o bloco `.setting-field` da ADR 0043 de lá, para o campo de telefone da tela de
Configurações. Nada disso entrou naquele port; é registrado para quem comparar os arquivos não
concluir que a diferença veio daqui.

## O que foi portado

**A ideia central, e é ela que explica a diferença de acabamento:** aquele arquivo tem uma
`@layer components` com ~200 classes semânticas, e o markup referencia `.panel` em vez de
repetir doze utilitários. O Biahflow tinha 45 linhas e **nenhuma** camada de componentes — o
estilo vivia inline nas 22 páginas, sem uma definição única de "o que é um card aqui".

Portadas (adaptadas à paleta preta e laranja):

| Nossa classe | Origem | O que mudou na adaptação |
|---|---|---|
| `.panel`, `.panel-heading` | `.panel` / `.panel-heading` | `border-line` na nossa escala |
| `.eyebrow` | `.eyebrow` | roxo → **laranja** (`accent`) |
| `.page-head` | `.hero` / `.hero-copy` | simplificada: sem a coluna de ação decorativa |
| `.metric-card`, `.metric-icon` | idem | tinte roxo → tinte laranja |
| `.btn` e variantes | `.admin-submit`, `.text-button` | primário roxo → **preto** (`ink`) |
| `.nav-item`, `.nav-item--active` | idem | ativo em `accent-50`, e branco sobre a sidebar escura |
| `.state`, `.state--0..3` | idem | mesma forma, tons de estado próprios |
| Sombras em camadas | `--shadow-card/raised/pop` | mesma geometria, sombra recolorida para o preto quente |

## O que o segundo port trouxe (ADR 0025)

A ADR 0024 deixou de fora a paleta e o shell, *de propósito*, e a ADR 0025 reverteu essa metade:
a **forma** passou a ser comum aos dois portais e o que identifica cada um é só o matiz.

| Nossa classe | Origem | O que mudou na adaptação |
|---|---|---|
| `.sidebar`, `.brand-row`, `.brand-mark` | idem | roxo → clay; `sticky h-screen`, que lá é o `.portal-shell` |
| `.nav-label` | idem | **`slate-400` → `muted`**: o tom de lá reprova no axe (~3,0:1) |
| `.nav-item` (reescrita) | idem | pele **única**; ativo em `brand-50`/`brand-700` |
| `.topbar`, `.breadcrumb`, `.topbar-actions` | idem | mesma forma; sem o `--menu-open` (não temos o conflito de z-index de lá) |
| `.icon-button`, `.avatar`, `.notification-dot` | idem | `size-10` em vez de `p-1.5`, por causa do alvo de toque de 24px |
| `.popover*` | idem | mesma forma, tokens próprios |
| `.auth-brand` | idem | **gradiente em outra direção** — ver abaixo |
| Escala `brand-50…900` | idem | mesmos degraus, matiz clay; **sem `brand-300`** |

**Não** portadas, e o motivo é o mesmo para todas: descrevem telas que este produto não tem —
`.journey-*`, `.chat-*`, `.message-*`, `.pending-*`, `.employee-*`, `.milestone*`,
`.project-switcher`. Copiar classe sem consumidor seria trazer para cá o defeito que aquele
repositório passou nove ADRs consertando.

## O que o terceiro port trouxe (ADR 0026)

Os dois ports anteriores puseram as primitivas no `index.css` e **nenhuma página as chamava** —
1.331 utilitários inline contra adoção zero de `.panel`, `.btn`, `.page-head` e `.state`. Esta
fatia migrou as 20 páginas e trouxe o que a migração exigiu:

| Nossa classe | Origem | O que mudou na adaptação |
|---|---|---|
| `.panel--flush`, `.panel-rows`, `.row` | `.field-row`/`.setting-row`/`.member-row` | **uma** declaração no lugar de três: o que muda entre elas é o conteúdo |
| `.filter-bar`, `.filter-chip` | idem | ganhou consumidor aqui (Leads, Clientes) e por isso entrou |
| `.empty-state` | idem | tokens próprios |
| `.back-link` | `.admin-back` | idem |
| `.form-label`, `.form-grid`, `.toolbar` | não há equivalente lá | nasceram da contagem daqui (69, 9 e 7 ocorrências) |
| `.state--off` | `.state--2` de lá | o **neutro** que faltava na nossa escala |
| `.btn--icon`, `.btn--icon-danger` | não há equivalente lá | 14 botões quadrados |

`brand-300` continua fora: o `.filter-chip` daqui usa `brand-500` na borda ligada, e o degrau
intermediário segue sem consumidor.

**A lição transferível do terceiro port:** o `.state--2` de lá é cinza e o daqui é âmbar, e a
diferença importa. "Desligada", "Arquivado" e "Expirado" caíram no âmbar durante a migração antes
de `.state--off` existir — e uma tela onde tudo é aviso não avisa nada.

## O que **não** foi portado, e é deliberado

- **A paleta.** Lá a marca é roxa (`brand-500 #6e56cf`) sobre `canvas #f6f8fc`; aqui é clay
  `#bd4a30` sobre `#fafaf9`. **É o único eixo de diferença que sobrou, e é intencional:** com a
  forma igual, a cor é o que diz em qual portal a pessoa está.
- **Dois tons que reprovam se copiados**, e os dois foram medidos nesta casa:
  - `.nav-label` em `slate-400` sobre branco dá ~3,0:1 e reprovou 19 telas de uma vez.
  - O `.auth-brand` de lá vai de `brand-900` a `brand-600`; no clay o eyebrow em `brand-200` dá
    **2,28:1** na ponta clara. O nosso vai de `brand-900` ao `ink`.
- **Os media queries.** Lá são 761px / 980px / 760px; aqui valem os breakpoints do Tailwind, e
  `e2e/responsive.spec.ts` afirma o comportamento da sidebar em `lg` = 1024px.
- **A arquitetura.** Lá é Next.js com server components; aqui é React + Vite com
  `AuthContext`. A regra do design system vale: *portar o visual, não o mecanismo*.

## Como refazer o port

```bash
git -C ../biahflow-portal-cliente show e95d8b2:app/globals.css | less
```

As primitivas relevantes estão no `@layer components`, a partir de `.panel`; o shell começa em
`/* ---------- Shell ---------- */`.

O sistema também está descrito na skill `portal-design`, com um arquivo de tema por produto — é
lá que moram os pares de contraste já medidos, para não serem remedidos a cada tela nova.
