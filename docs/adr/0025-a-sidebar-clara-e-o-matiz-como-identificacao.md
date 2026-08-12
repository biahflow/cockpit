# ADR 0025 — A sidebar clara, e o matiz como única identificação

**Status:** aceito
**Data:** 07/08/2026
**Fase:** transversal — front-end do portal operacional
**Revisa:** ADR 0024

## Contexto

A ADR 0024 portou metade do design system do portal do cliente — as primitivas, as sombras em
camadas, a hierarquia tipográfica — e deixou de fora, **de propósito**, a paleta e o shell. O
argumento estava escrito em `docs/design/referencia-portal-do-cliente.md`: *"o ponto do pedido
era justamente não ficarem iguais em cor"*.

O argumento estava certo sobre a cor e errado sobre o resto. Posta uma captura de cada portal
lado a lado, o que salta não é o matiz: é a **forma**. Lá a barra lateral é branca, tem uma marca
com quadradinho colorido, um rótulo de seção e um rastro de navegação no topo; aqui a barra era
preta e o topo trazia uma frase decorativa. Duas telas do mesmo ecossistema que ninguém reconhece
como parentes.

O pedido desta fatia inverte a divisão da ADR 0024, e não a contradiz:

> **A forma passa a ser comum aos dois portais. O que identifica é só o matiz.**

Quem abre uma captura precisa saber em qual dos dois está sem ler o texto — e a cor é a única
coisa na tela cuja função é essa.

## Decisão

### 1. A barra lateral fica clara, como a do portal do cliente

Branca, 254px, `border-r`, com `.brand-row` (quadrado `brand-500` + "Biah**flow**", o sufixo no
matiz da marca), `.nav-label` de seção, `.nav-item` e uma nota no rodapé. O topo ganhou
`.breadcrumb` no lugar da frase "Acompanhe o que importa para a Biahflow." — o rastro sai do mesmo
array `links` que desenha o menu, de modo que uma rota nova ganha rastro sem ninguém lembrar de
uma segunda lista, que é como um breadcrumb passa a mentir.

Ela também virou **fixa, com o menu rolando por dentro**. Com 15 itens a barra transbordava em
800px de altura: "Configurações" e a nota do rodapé só apareciam depois de rolar o *conteúdo*, e a
navegação sumia justamente quando a pessoa descia a página. Não era regressão desta fatia — era
assim desde sempre —, mas é a peça do shell que faltava e o custo era `sticky top-0 h-screen` mais
um container com `overflow-y-auto`.

### 2. `accent*` vira a escala `brand-50…900`

Quatro tokens avulsos bastavam enquanto o laranja era um detalhe sobre superfície branca. O shell
claro precisa da escala: o item de menu ativo quer um fundo tinto e um texto escuro do mesmo
matiz, e *"um pouco mais claro que o acento"* não é um valor que se escreva inline.

```
brand-50   #fdf1ec   fundo tinto: nav ativo, ícone de métrica, selo
brand-100  #fadfd4   ::selection, contador do item ativo
brand-200  #dd8b62   o acento que sobrevive a fundo escuro
brand-500  #bd4a30   primário: brand mark, foco, contador de notificação
brand-600  #a8412a   hover, link de texto sobre branco
brand-700  #9c3c26   texto do nav ativo, texto de selo
brand-900  #5c2317   ponta escura do gradiente do login
```

**O laranja não muda de hex.** `#bd4a30` é resultado da medição da FDD 022; inventar tom novo
refaria aquela medição do zero, com chance de repetir o defeito que ela consertou (`#d05d45` dava
3,9:1 e reprovava como texto).

Os degraus **espelham um a um** os do portal do cliente (`brand-50…900`, lá roxos). É isso que
torna o port do shell uma tradução de cor em vez de um redesenho: a marcação é a mesma nos dois
repositórios, e a folha de estilo é que diz qual produto é.

**Não há `brand-300`**, e a ausência é a regra da ADR 0024 aplicada a token: lá ele é a borda do
`.filter-chip` em hover, componente que este produto não tem. O Tailwind v4 nem o emitiria — ele
existiria só no arquivo, dando a impressão de uma escala mais completa que a em uso.

Os quatro nomes antigos ficam como **apelidos** em `@theme inline`, porque as 22 páginas os usam
inline centenas de vezes e trocá-los no mesmo commit que muda o shell juntaria duas fatias que
falham por motivos diferentes. Medido no CSS de saída: `focus:ring-accent/10` compila para
`#bd4a301a`, idêntico ao que `brand-500/10` produziria. É compatibilidade de migração, não
desenho.

### 3. `.nav-item` perde a segunda pele

Eram duas — a escura da barra lateral e `.nav-item--light` para a gaveta do celular. Com a barra
clara elas colapsam numa. O modificador foi apagado junto do parâmetro `light` de `nav()`: um
modificador que não modifica nada é a próxima coisa que alguém aplica por engano.

### 4. O login vira a única superfície escura, e ganha o gradiente da marca

Com a barra lateral clara, o painel esquerdo do login é o único lugar onde o `ink` ainda aparece
como superfície — e por isso é onde a cor da marca precisa aparecer inteira.

## O que a fatia mediu

**Duas medições mudaram a decisão, e as duas foram contra copiar o portal do cliente ao pé da
letra.**

### O gradiente do login reprova se for copiado

O `.auth-brand` de lá vai de `brand-900` a `brand-600`. Traduzido para o clay:

| Par | Razão | |
|---|---|---|
| `brand-200` sobre `brand-900` `#5c2317` | 4,6:1 | passa |
| `brand-200` sobre `brand-600` `#a8412a` | **2,28:1** | **reprova** |

O eyebrow "Portal operacional" corre sobre o gradiente inteiro, então a ponta clara o reprovaria.
O gradiente daqui vai do clay profundo ao **preto quente** — 4,6:1 numa ponta, 7,2:1 na outra:

```css
background: linear-gradient(150deg, var(--color-brand-900) 0%, var(--color-ink) 100%);
```

Vale a pena nomear a causa: `brand-200` existe desde a ADR 0024 porque `brand-500` sobre `ink` dá
3,82:1. O tom que resolve o preto é claro demais para o laranja médio. Não há um único acento que
sirva às duas superfícies, e é por isso que são dois tokens.

### `.nav-label` reprova, e o portal do cliente reprova junto

O rótulo de seção lá é `slate-400`, que sobre branco dá ~3,0:1. Portado tal e qual, o axe reprovou
**19 telas de uma vez** — `color-contrast (serious) — .nav-label`. Ficou em `muted` (7,4:1), o
cinza quente que a paleta já tinha.

É o achado mais transferível da fatia: **copiar a forma copia junto os defeitos de contraste da
fonte**, e aqui existe um gate que os pega. Não é conjectura sobre o outro repositório — é um fato
sobre o tom, e lá ele aparece no mesmo componente.

## Consequências

- Os dois portais passam a ser reconhecíveis como o mesmo sistema, e distinguíveis pela cor.
  **Roxo = portal do cliente. Clay = portal operacional.** Nunca o inverso.
- O sistema está descrito numa skill só, `portal-design`, com um arquivo de tema por produto. A
  skill `biahflow-design` foi estreitada para nomear apenas o OikOS, que é o que ela sempre
  descreveu — ela disputava gatilho com este repositório e o `CLAUDE.md` precisava de um parágrafo
  mandando não segui-la.
- As 22 páginas **não foram tocadas**. Elas herdaram cor e acabamento pelos tokens e continuam com
  utilitário inline; migrá-las para as primitivas segue sendo o destino, não uma migração feita.
- `.nav-item--light`, `.nav-item` escura e o cartão `bg-white/5` da barra saíram. Quem reintroduzir
  uma superfície escura precisa lembrar de `brand-200` — o `brand-500` cru ali reprova.

## Verificação

`npm run build`, `npm run lint`, `npm test` (28 arquivos, 179 testes) e `npm run e2e` (147),
todos verdes. O `e2e/a11y.spec.ts` é o gate que decidiu o `.nav-label` e confirmou o gradiente.
`Layout.test.tsx` passou **sem edição**: ele consulta por papel e por texto, não por classe, o que
é a razão de um teste de shell sobreviver a um redesenho de shell.
