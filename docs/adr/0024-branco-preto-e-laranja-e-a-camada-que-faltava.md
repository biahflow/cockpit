# ADR 0024 — Branco, preto e laranja, e a camada que faltava

**Status:** aceita
**Data:** 07/08/2026
**Fase:** transversal — front-end do portal operacional

## Contexto

O portal Biahflow e o portal do cliente não se falam visualmente. O pedido foi aproximar os
dois usando o design do portal do cliente como referência, mantendo branco e ganhando toques
de laranja e preto para não virarem a mesma marca.

Medido antes de decidir, e o número que muda o diagnóstico:

| | portal do cliente | Biahflow |
|---|---|---|
| CSS | `app/globals.css`, **761 linhas** | `frontend/src/index.css`, **45 linhas** |
| Camada de componentes | ~200 classes semânticas | **nenhuma** — só um `@utility field` |
| Sombras | três em camadas, aplicadas por classe | **12 `shadow-sm`** no app inteiro |
| Estilo nas telas | markup referencia `.panel` | utilitário Tailwind inline em 22 páginas |

**Metade da distância não era cor.** Era a ausência de tratamento de superfície: não havia uma
definição única de "o que é um card aqui", e por isso nenhum card tinha sombra. Trocar a paleta
sozinha deixaria os dois portais com cores parentes e acabamento diferente.

O que jogou a favor: os cinco tokens eram usados **629 vezes** em 27 arquivos (`ocean` 253×,
`ink` 238×, `signal` 76×, `mint` 52×, `sand` 10×). Redefinir o token repinta o produto inteiro
sem tocar em página nenhuma.

## Decisão

### A paleta: preto primário, laranja de acento, fundo quase-branco

```
ink        #12110f   texto, títulos, sidebar, botão primário
muted      #57534e   texto secundário
line       #e7e5e4   bordas
canvas     #fafaf9   fundo da página
accent     #bd4a30   laranja: eyebrow, link, selo, foco, contador
accent-50  #fdf1ec   tinte do acento
accent-700 #9c3c26   hover do acento
danger     #b91c1c   erro, atraso, ação destrutiva
```

**O primário é preto e não laranja**, e a razão é aritmética: o acento vale por ser raro. Uma
tela com seis botões laranja não tem acento nenhum.

**O fundo é quase-branco e não branco puro**, contra o pedido literal e a favor do que o pedido
queria. Com `canvas` e `.panel` ambos brancos o card desaparece, e é exatamente a hierarquia de
superfície que faz o portal do cliente parecer acabado. `#fafaf9` lê como branco e mantém a
profundidade.

**O laranja é o hex de antes, `#bd4a30`, sem um dígito de diferença.** Ele não é escolha de
gosto: é resultado de uma medição de contraste da FDD 022 — o tom anterior, `#d05d45`, dava
3,9:1 e reprovava em AA como texto. Inventar um laranja novo aqui seria refazer aquela medição
do zero, com chance de repetir o defeito que ela consertou.

### O acento e o perigo deixaram de poder ser a mesma cor

`signal` era o clay laranja **e era a cor de erro** — quase sempre dentro de um `bg-red-50`:
mensagem de falha, selo "Vencido", valor em atraso, o item Sair. Promover o laranja a acento da
marca colidiria os dois: a mensagem de erro ficaria idêntica ao eyebrow de uma seção, e ninguém
teria como distinguir "isto é a marca" de "isto deu errado".

Então o perigo virou vermelho de verdade (`#b91c1c`, 5,9:1 sobre branco e 5,6:1 sobre `red-50`)
e o laranja ficou com a marca. **A exceção deliberada é o contador de notificação**, que era
`bg-signal` por ser marca e não erro: ele fica em `accent`.

*Esta consequência não estava no pedido e é forçada por ele.* Não dá para ter laranja como
acento da marca e como cor de erro ao mesmo tempo.

### Os nomes dizem o papel, não a cor

`ocean`→`ink`/`accent`, `mint`→`accent-50`, `sand`→`canvas`, `signal`→`danger`. Um token
chamado `ocean` valendo `#12110f` é o tipo de nome mentiroso que este repositório costuma
consertar depois com um commit próprio.

**O renomeio de `ocean` não era mecânico, e essa foi a parte que exigiu decisão.** Medido: 136
linhas continham `ocean` e `ink` ao mesmo tempo — os pares `text-ocean hover:text-ink`,
`hover:border-ocean`, item ativo. Um `ocean`→`ink` cego achataria as 136 numa cor só e apagaria
justamente os estados de hover. A regra que resolveu é a própria decisão de design:

- `ocean` como **superfície** (fundo de botão, logo, item ativo) → `ink`;
- `ocean` como **ênfase** (link, texto de destaque, borda de foco, contador) → `accent`.

É onde entram os "toques de laranja": o que era teal de destaque virou laranja, o que era teal
de superfície virou preto. Na prática: 59 `bg-ocean` viraram preto e 134 `text-ocean` viraram
laranja — quase todos ícones dentro de chips tingidos, eyebrows e links, que é o tamanho certo
para um acento.

De carona, o `ScoreBar` de `ProjectDetailPage` tinha `tone: "ocean" | "mint"` — uma união de
tipos nomeada por **cor**. Virou `"brand" | "positive"`, que é o que ela sempre quis dizer.

### A camada de componentes que não existia

Um `@layer components` no `index.css`, portando do portal do cliente **só as primitivas que
este produto usa**: `.panel`, `.panel-heading`, `.eyebrow`, `.page-head`, `.metric-card`,
`.btn` (+ variantes), `.nav-item`, `.state`, `.popover`.

**Não** foram portadas `.journey-*`, `.chat-*`, `.message-*`, `.pending-*`, `.employee-*` — elas
descrevem telas que este produto não tem, e copiar classe sem consumidor traria para cá o
defeito que aquele repositório passou nove ADRs consertando.

### O shell escuro

A barra lateral saiu de `bg-mint/50` para `bg-ink`, que é metade da identidade visual do portal
do cliente. Consequência que virou código: o menu precisa de **duas peles** — escura na lateral,
clara no menu mobile —, e isso é uma função com um parâmetro, não duas cópias da marcação.
Duplicar faria um item novo aparecer só numa das larguras.

De carona, o item ativo ganhou `aria-current="page"`, que faltava.

## Consequências

**O portão é o axe, e ele decide o tom, não o contrário.** `e2e/a11y.spec.ts` varre 21 telas ×
3 larguras em WCAG 2.0/2.1 A e AA, contraste incluído. O pré-cálculo desta paleta (`ink` 18,9:1;
`accent` 4,96:1 nas duas direções; `accent` sobre `canvas` 4,76:1) existe para não descobrir
tarde, mas quem valida são as 63 varreduras. **Se elas reprovarem, cede o tom.**

**As 22 páginas mantêm o utilitário inline.** Elas trocaram de cor pelos tokens e não adotaram
`.panel`/`.page-head` — a camada nova é o destino para onde migrar, não uma migração feita. É a
diferença entre "os dois portais conversam" e "os dois portais são iguais", e a segunda é um
diff que não cabe numa revisão honesta. Fica nomeado como fatia seguinte, com a matriz do axe a
reconferir a cada passo.

**O que voltar atrás exige.** O marco é `design/antes-do-redesenho` (commit `99ce39e`) e o
snapshot legível é `docs/design/paleta-anterior.md`. Uma tag sozinha não bastava: ela ajuda quem
lembra que ela existe, e daqui a seis meses quem quiser saber por que o laranja era `#bd4a30`
vai procurar num documento. **O snapshot carrega as duas correções que um "voltar atrás"
reintroduziria** — o escurecimento do laranja e a remoção do `focus:outline-none`, esta última
com a armadilha do `--tw-outline-style: none` que faz qualquer `:focus-visible` posterior
resolver para `none` em silêncio.

**A skill `biahflow-design` está desatualizada, e já estava antes desta fatia.** Ela descreve
`pine green + clay orange + paper` e aponta o `biahflowOS-frontend` como implementação canônica
— e **este repositório nunca casou com ela**: usava `ocean`/`mint`/`sand`. A decisão aqui é
**não** editá-la: ela governa o OikOS, e o portal Biahflow passa a ter design system próprio,
documentado em `docs/design/`. Editar a skill sem decidir a quem ela pertence trocaria uma
divergência silenciosa por outra.

**Fica aberto, e nomeado:** dark mode continua fora, nos dois portais; e a migração das páginas
para as primitivas.
