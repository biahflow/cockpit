# ADR 0026 — As telas passam a chamar o design system (e a guarda que impede a volta)

**Status:** aceita
**Data:** 08/08/2026
**Fase:** transversal — front-end do portal operacional
**Completa:** ADR 0024, ADR 0025

## Contexto

A ADR 0025 deu ao produto o shell do portal do cliente — sidebar clara, brand mark, breadcrumb,
escala `brand-*`, gradiente do login. O shell ficou igual ao da referência **e as telas
continuaram diferentes**.

A causa foi medida, e não era a paleta nem a stack:

| Primitiva | Usos nas 20 páginas |
|---|---|
| `.panel` | **0** |
| `.metric-card` | **0** |
| `.page-head` | **0** |
| `.btn` | **0** |
| `.state--*` | **0** |
| `.eyebrow` | 2 |

**1.331 `className` inline.** O `index.css` da ADR 0024 já dizia isto por escrito — *"as 22
páginas ainda não as adotam… isto é o destino para onde migrar, não uma migração já feita"* —, e
a frase sobreviveu duas ADRs. A tela de Configurações reimplementava `.page-head` num `<header>`,
`.panel` numa `<section>`, `.state--0` num `<span>` e `.btn--secondary` em cada `<button>`.

**A alternativa considerada e descartada foi migrar para Next.js 16**, para igualar a stack do
portal do cliente. A medição derrubou a hipótese: lá os 8 `page.tsx` de servidor só **buscam
dado**, e os 9 componentes `"use client"` desenham a tela inteira. Trocar Vite por Next mudaria
zero pixel, e quebraria o mock de `page.route` de `e2e/matrix.ts` — com RSC o fetch sai do
browser, e são 21 telas × 3 larguras de gate de acessibilidade.

## Decisão

### 1. As 20 páginas passam a chamar as primitivas

Substituição, não redesenho. Onde a primitiva não coube, o utilitário inline ficou: inventar
`.panel--variante-da-tela-tal` para uma ocorrência recria o problema que a ADR 0024 nomeou. Duas
páginas usam `<table>` e nenhuma primitiva de tabela foi criada — dois consumidores não fazem um
padrão.

### 2. Onze primitivas novas, cada uma com a contagem que a justifica

| Primitiva | Ocorrências que substituiu |
|---|---|
| `.form-label` | **69** — o literal mais repetido do repositório |
| `.panel--flush` + `.panel-rows` + `.row` | 22 cartões com cabeçalho e lista dividida |
| `.btn--icon`, `.btn--icon-danger` | 14 botões quadrados |
| `.form-grid`, `.toolbar` | 16 |
| `.empty-state`, `.alert--error`, `.alert--ok` | 14 |
| `.filter-bar` + `.filter-chip` | 2 barras de filtro (Leads, Clientes) |
| `.back-link` | 5 links de subir um nível |
| `.btn--secondary-danger` | 4 botões `Arquivar` de tela de detalhe |

**A tabela acima é a regra inteira: a coluna da direita é a justificativa.** `.card-grid` entrou
numa versão anterior desta fatia alegando "grades de cartão" sem contar nenhuma, e saiu — assim
como `.btn--ghost`, herdada da ADR 0024 e nunca chamada. Classe sem consumidor é a mesma dívida
que a fatia veio pagar, escrita do outro lado: em vez de literal sem primitiva, primitiva sem
literal. `.btn--danger` parecia ser a terceira e não era — o `ConfirmDialog` a escrevia à mão, com
o vermelho certo e o nome nenhum.

`.state--off` fechou uma lacuna da escala: **"Desligada", "Arquivado" e "Expirado" não são aviso,
são ausência de estado.** Sem ele a migração empurraria essas linhas para o âmbar do `--2`, e uma
tela onde tudo é aviso não avisa nada. É o `.state--2` do portal do cliente, que na escala de lá
já é o cinza.

`.panel-heading--icon` nasceu de um defeito visto na captura: o `justify-between` do base existe
para "título à esquerda, ação à direita" e jogava o título para o outro lado da faixa quando o
cabeçalho é ícone + texto.

### 3. Dois ajustes que mudam pixel em todas as telas

- **`.page-head h1`: `text-2xl` → `text-3xl`.** As 19 páginas já escreviam `text-3xl` inline, e o
  `.hero h1` da referência também. A primitiva é que estava fora de passo; adotá-la sem isto teria
  **encolhido todo título do produto** — regressão que o axe não pega e que todo mundo vê.
- **`.eyebrow` passou a caixa alta em 19 cabeçalhos.** Era `text-sm font-semibold text-accent`
  ("Administração"); virou `text-[11px] uppercase tracking-[0.18em]` ("ADMINISTRAÇÃO"), que é o
  rótulo da referência. Nenhum teste quebrou: `text-transform` não altera o texto no DOM.

### 4. Os mapas de cor crus passam a devolver variante

Sete arquivos tinham `Record<Status, string>` devolvendo `"bg-emerald-50 text-emerald-700"`. Cada
um era uma **segunda definição de "concluído"**, e ela diverge da primeira sem nada ficar
vermelho. Agora devolvem `"state--1"`. O `ArtifactsPanel` tinha um quinto tom só dele
(`sky-50`); virou `state--0`, o informativo — um tom próprio de um painel é uma escala paralela.

### 5. A guarda: `src/test/primitivas.test.ts`

**Um card escrito à mão renderiza *quase* igual a um `.panel`, e a divergência não deixa nada
vermelho.** Foi assim que o produto chegou a 1.331 literais com adoção zero: o axe mede contraste
e papel — um card inline passa; os testes de página consultam por papel e texto — um card inline
passa. O que se perde não é acessibilidade nem comportamento, é a definição única de "o que é um
card aqui".

É o desenho do `inertButtons()` do portal do cliente, que existe porque um `<button>` sem handler
renderiza HTML idêntico a um que funciona: são as duas asserções deste ecossistema que olham a
**forma do código** em vez de um valor. A segunda asserção — allowlist sem linha obsoleta — é a
lição da ADR 0033 de lá: allowlist que ninguém revisa vira permissão permanente.

A allowlist **nasce vazia, e a meta é que continue.**

O arquivo mora em `src/test/` porque é lá que o vitest o encontra, mas está no
`tsconfig.node.json` e **excluído** do `tsconfig.app.json`: ele lê `src/**` do disco com
`node:fs`, e alargar os tipos do tsconfig do bundle levaria os globais do Node para dentro do
navegador.

## O que a fatia mediu

**A guarda nasceu vermelha com 29 achados, e três coisas nela valem registro.**

1. **Ela achou o que o levantamento manual não viu: os `components/`.** A conta de 1.331 literais
   era sobre `pages/`. `StatusDot`, `ArtifactsPanel`, `AgentPanel` e `ErrorBoundary` tinham os
   mesmos mapas de cor crus e os mesmos cartões à mão — e são compartilhados, então cada um
   espalhava a divergência por várias telas.

2. **Duas regras minhas nasceram largas demais, e a medição mostrou onde.** A do selo casava
   `rounded-lg px-2 py-1 text-xs font-semibold text-slate-600`, que é um **botão de texto** — e
   trocá-lo por um selo transformaria um controle em rótulo. Passou a exigir `bg-`: selo tem
   fundo. A do eyebrow casava a pastilha de contagem "8 novos". Uma guarda que cobra a troca
   errada é pior que guarda nenhuma, porque ensina a ignorá-la.

3. **47 botões tinham `hover:bg-ink` sobre `bg-ink`** — o hover não fazia nada em nenhum deles,
   desde sempre. Adotar `.btn` (que tem `hover:bg-brand-700`) consertou os 47, e a guarda agora
   reprova o padrão.

4. **A guarda ficou verde com 13 cópias do secundário ainda no disco, e essa é a medição mais
   importante das quatro.** O padrão do `.btn` descrevia só o primário (`bg-ink … text-white`); a
   forma de contorno — `rounded-xl border px-4 py-2.5 text-sm font-semibold text-ink
   hover:border-accent` — sobrou idêntica em 9 arquivos e passou por baixo. Uma guarda que cobre
   metade de um par não está incompleta: ela **certifica** a metade que não vê, e o verde dela é o
   que convence a próxima pessoa de que não há nada ali. O mesmo aconteceu em escala menor com
   quatro literais que escapavam por sintaxe, não por ausência de regra — uma utilitária no meio
   (`grid flex-1 gap-2 …`), um `p-6` onde o padrão dizia `p-[45]`, um `border-dashed` sem
   `text-center`, um selo em `text-[11px]` onde o padrão dizia `text-xs`. Os padrões que casam por
   substring em ordem fixa erram para o lado do silêncio.

## Consequências

- A adoção das primitivas saiu de 2 para **399 usos**. O que separa as duas telas dos dois
  portais passou a ser o matiz, que era o objetivo desde a ADR 0025.
- Página nova nasce chamando primitiva ou reprova no `npm test`. Quem precisar de exceção escreve
  o motivo na allowlist.
- A frase *"as 22 páginas ainda não as adotam"* saiu do `index.css` e do `CLAUDE.md`. Ela era
  verdadeira e passou a não ser; a guarda é o que a mantém falsa.
- Restam utilitários inline onde não há primitiva — tabelas, barras de progresso, decoração do
  login. Isso é o desenho, não dívida: a regra continua sendo classe com consumidor.
- **A guarda passou a cobrar 13 padrões, e a `@layer components` perdeu duas classes.** Saíram
  `.btn--ghost` e `.card-grid` (zero consumidores) e os apelidos `accent-200`/`accent-700` (zero
  usos); entrou `.btn--secondary-danger` (4). `.btn--danger` trocou `bg-red-700` por `bg-danger` —
  mesma tinta, mas a única primitiva de perigo estava fora do token de perigo.
- **Os três banners verdes escritos à mão ficam.** `TeamPage.tsx:40`, `ProjectDetailPage.tsx:552` e
  `CommercialPage.tsx:121` dizem sucesso em `emerald`, e `.alert--ok` é tinta de **marca**
  (`brand-50/60`), não verde. Trocá-los mudaria a cor de três confirmações para laranja, que é o
  desenho da fatia anterior aplicado ao caso errado; dar uma variante verde ao `.alert--ok` criaria
  uma segunda gramática de sucesso. Três ocorrências não decidem isso — fica nomeado, não
  implícito, e a próxima que aparecer é que traz a decisão.

## Verificação

`npm run build`, `npm run lint`, `npm test` (29 arquivos, **181** testes — os dois novos são a
guarda) e `npm run e2e` (147), rodados **entre cada lote** de páginas e todos verdes ao fim.

Os 179 testes que já existiam passaram **sem edição**, e isso não é sorte: eles consultam por
papel e por texto, e os únicos seis `querySelector` do repositório apontam para
`input[type="date"]` e um data-attribute. É a razão de um teste de tela sobreviver a um redesenho
de tela.
