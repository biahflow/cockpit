# Design Approval Package — Engagements no detalhe do cliente

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **1**
Status: **Approved**
Data: 2026-08-28
Produzido por: harness (Claude Code), sob `workflows/design-approval.md`

> Este artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> dentro do código de aplicação. Nenhuma linha de `frontend/src/` muda nesta entrega.

## Por que existe um gate

`Engagement` (ADR 0050, FDD 046) é o mandato de transformação que a conta contratou: a camada
entre `Account` e `Project` que agrupa **várias vendas e vários projetos que são o mesmo
trabalho**. Ela governa permissão (`RolePermission`), arquivamento (`perform_destroy` recusa
mandato com projeto vivo) e conversão (`convert-to-project` cria um mandato de escopo único quando
o payload não traz um). `Project.engagement` é `NOT NULL` desde a migração `0057`.

**E a entidade não tem nenhuma tela.** A Fase 2 da migração de ontologia deixou a interface de fora
de propósito; hoje criar, editar ou encerrar um mandato é `curl` contra `/api/v1/engagements/` ou
Django admin. Criar essa superfície é, pela definição de `workflows/design-approval.md`, "criar ou
alterar materialmente uma superfície perceptível por humano" — e a mesma página diz explicitamente
que a classificação cobre os estados de erro, vazio, carregamento e não autorizado, que são os
descobertos tarde.

E há um segundo fato que dá peso à decisão: **`ClientDetailPage` não lista projetos hoje** — zero
ocorrências de `projects` nas 375 linhas do arquivo. A tela do cliente mostra saúde da relação,
satisfação, processos mapeados, cadastro, contatos e interações, e em nenhum lugar diz o que a casa
está entregando para aquela conta. Esta seção é **o primeiro lugar do produto onde a espinha
`Account → Engagement → Project` fica visível**, e é isso que justifica a superfície que ela ocupa:
não é mais um painel na pilha, é a resposta à pergunta que a ADR 0050 abre e que o produto ainda
não responde — *"como vai a transformação daquela conta?"*.

Nenhuma aprovação vigente cobre esta superfície: o DAP GH-26 r1 aprovou marca e fundações no shell
e listou "as outras 20 telas de produto" como **não** aprovadas
(`docs/design/dap-gh26-r1/README.md`), e o DAP perfil-e-contato r1 aprovou o painel de Contatos
desta mesma página, não uma seção nova.

O gate fica **antes do planejamento**, não antes da construção. Ele é pedido agora, com o
mapeamento de código já feito e nenhuma linha de implementação escrita.

## Onde a seção mora

Dentro de `ClientDetailPage`, como `<section className="panel">`, **entre "Saúde da relação"
(`ClientDetailPage.tsx:194-211`) e "Satisfação" (`:219-241`)**.

O raciocínio: a saúde é o relance de *como estamos indo*; o engajamento é *o que estamos fazendo*,
e **estrutura vem antes de histórico**. Quem abre a conta precisa saber qual é o mandato antes de
ler o que aconteceu dentro dele. As seções seguintes — Satisfação, Processos mapeados, Dados do
cliente, Contatos, Interações — **não mudam de ordem** e nenhuma delas é tocada.

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização auto-contida. Abre sem build, sem toolchain e sem rede. |
| `board-desktop.png` | Captura congelada do board a 1280px, `deviceScaleFactor: 2`. |
| `board-mobile.png` | Captura congelada do board a 390px. |

As capturas são a evidência fixa do que foi renderizado: um board depende de fonte, navegador e
plataforma, e é ao PNG que a aprovação se refere. Elas retratam o **board**, não o produto — a
evidência renderizada da tela implementada é `BROWSER_REQUIRED` e vem depois, contra o código. O
board cita, valor a valor, a origem de cada cor, corpo, raio e sombra em `frontend/src/index.css`.

## O que está sendo pedido

Duas decisões separadas, porque aprovar visual não aprova copy — e nesta revisão **as duas
decisões reais são de copy e de leitura**, não de forma. Elas estão **desenhadas lado a lado no
board**, para serem escolhidas olhando, e não descritas em prosa.

### Decisão A — o título da seção diz "Engagements", em inglês, numa interface em pt-BR

O mapa de linguagem (`docs/ontology/language-map.md` §1) é explícito: termos canônicos **em inglês
nas quatro superfícies**, `snake_case` em código/banco/API, `Title Case` em UI e prosa, e *"não se
traduz o termo — traduz-se o texto em volta dele"*. O exemplo da própria página é *"A Account tem
três Engagements ativos"* está certo; *"A Conta tem três Compromissos ativos"* está errado. A §2
lista `Engagement` com "Nunca chamar de: Projeto, Conta, Contrato".

Aplicado: cabeçalho **"Engagements"**, copy em volta em pt-BR — *"2 engagements ativos nesta
conta"*, *"Novo engagement"*, *"Editando {nome}"*.

**Isto é apresentado como decisão a aprovar, não como fato consumado.** É a primeira vez que um
termo canônico em inglês aparece como **título de seção** na interface: hoje todos os títulos da
tela são pt-BR ("Saúde da relação", "Satisfação", "Processos mapeados", "Contatos", "Interações").
O board mostra as duas versões do cabeçalho lado a lado — **A1 "Engagements"** e **A2 "Mandatos"**
—, visualmente idênticas, para que a escolha seja sobre a palavra.

**Recomendação: A1.** "Mandatos" lê mais liso em português e é o que a docstring do modelo usa em
prosa, mas cria um **quinto** nome para o conceito — `Engagement` no modelo, na API, no One e no
Notion, "Mandato" só na tela do Pulse. Quem lê "Mandatos" na interface e `/engagements/` no log não
sabe que são a mesma coisa, e é exatamente isso que a regra de ouro do mapa existe para impedir.

Se A2 for escolhida, a troca é só de strings: nenhum valor visual muda.

### Decisão B — como o modelo comercial aparece

`commercial_model` (`design_partner` | `paid`) diz se a conta paga pelo trabalho ou é parceira de
desenho. As duas leituras estão desenhadas no board:

- **B1 (recomendada)** — as duas pílulas sempre visíveis. `paid` como `.state--off` (o neutro
  cinza) e `design_partner` como `.state--0`. A exceção fica com a tinta, a regra fica quieta, e
  **nenhuma linha obriga a inferir o modelo pela ausência de selo**.
- **B2** — pílula só quando `design_partner`; a linha da conta paga não mostra nada. Mais limpo, e
  o custo é que **"sem selo" passa a significar duas coisas** para quem olha: conta paga, ou campo
  que ninguém preencheu. A segunda leitura é impossível no banco (a coluna será `NOT NULL`), mas
  quem lê a tela não sabe disso — e o produto inteiro tem campo opcional que fica em branco. Uma
  tela que exige conhecer o schema para ser lida corretamente pede a coisa errada de quem a usa.

**Recomendação: B1.**

Nota de precisão sobre `.state--0`: o spec desta tarefa o descreveu como "marca". Ele **não** é —
desde a ADR 0041 / DAP GH-19 r2, `.state--0` é `bg-info-50 text-info`, o **azul de informação**,
com o comentário do próprio arquivo dizendo "informação é azul e perigo usa o próprio par claro"
(`index.css:365-369`, tokens em `:110-111`). A escolha de variante permanece a mesma e fica ainda
melhor justificada: `.state--0` é o selo que **esta mesma página já usa** em "Recebe cobrança" na
linha do contato (`ClientDetailPage.tsx:309`), e pelo mesmo motivo — é um fato sobre o registro,
não um aviso nem uma falha.

### Status — sem alternativa a decidir

`active` → `.state--1` (verde de sucesso), `paused` → `.state--2` (âmbar de aviso, o único dos três
que pede alguém), `closed` → `.state--off` (**neutro**).

A justificativa da terceira, que é a que costuma sair errada, está no `CLAUDE.md`: *"Desligada" e
"Arquivado" não são aviso* — são a ausência de um estado. Um mandato encerrado é um mandato que
terminou, muitas vezes bem; pintá-lo de perigo faria a conta de melhor histórico parecer a mais
problemática, e uma tela onde tudo avisa não avisa nada. `.state--3` (vermelho) não é usado nesta
seção.

## Novo versus consumido

**Nenhum valor visual é novo nesta revisão.** A lista de "novo nesta revisão" está **vazia**, e é
esse o resultado que estava em julgamento.

A seção consome, sem exceção: `.panel`, `.panel-heading`, `.panel-rows`, `.row`, `.row-main`,
`.metric-icon`, `.state` (`--0`, `--1`, `--2`, `--off`), `.btn`, `.btn--secondary`,
`.btn--secondary-danger`, `.btn--icon`, `.empty-state`, `.alert--error`, `field`, `.form-label`,
`.form-grid` e a regra global de `:focus-visible`. Nenhuma cor nova, nenhum corpo fora dos papéis
`display/title/body/label/meta`, nenhum raio fora do par 8px/12px das fundações r2 (com o
`rounded-full` das pílulas, que o contrato r2 já reserva a status e avatar), nenhuma sombra além de
`--shadow-card`, **nenhuma classe nova em `index.css`**.

Isso não é sorte: a seção é uma *lista com cabeçalho, selos e um par de ações*, e é exatamente o
que Satisfação, Processos mapeados e Contatos já são na mesma página. Uma seção nova que precisasse
de um valor visual novo estaria afirmando que não se parece com nada do produto — e aqui essa
afirmação seria falsa.

O board também registra as duas armadilhas que a página já documentou por escrito e que o desenho
respeita em vez de redescobrir:

- **as pílulas são irmãs de `.row-main`, não filhas.** `.row-main span` declara `block text-xs
  text-muted` (`index.css:216`), e um `.state` aninhado ali perderia a própria pele sem nada ficar
  vermelho. Os comentários de `ClientDetailPage.tsx:234-237` e `:350-351` descrevem exatamente esse
  defeito;
- **`.state` recebe variante, nunca cor** — `"state--1"`, jamais `"bg-emerald-50 text-emerald-700"`
  —, pela regra do `CLAUDE.md` e da ADR 0026.

## Decisões registradas

| # | Decisão | Alternativa rejeitada |
| --- | --- | --- |
| **A** | Título **"Engagements"**, em inglês, com a copy em volta em pt-BR | "Mandatos" — cria um quinto nome para o conceito, contra o mapa de linguagem §1 |
| **B** | As **duas** pílulas de modelo comercial sempre visíveis | Pílula só no `design_partner` — faz "sem selo" significar duas coisas |
| 1 | Seção entre Saúde da relação e Satisfação | Depois de Contatos — enterraria a estrutura embaixo do histórico |
| 2 | `closed` em `.state--off`, neutro | `.state--3` vermelho — encerrado não é falha |
| 3 | Formulário embutido, com "Editando {nome}" | Modal dedicado — superfície nova para o que o padrão de Contatos já resolve na mesma página |
| 4 | Erro no `.alert--error` do topo da página | Alerta dentro do painel — abriria uma segunda convenção de erro na mesma tela |
| 5 | Ícone `Target` do `lucide-react` | `Handshake` — quase idêntico ao `HeartHandshake` da Satisfação, que fica logo abaixo |
| 6 | Período com precisão de **mês** ("Desde 03/2026") | Data completa, como Satisfação e Interações usam — mais consistente, e mais ruído numa linha com quatro informações |
| 7 | Cabeçalho consome `.panel-heading` | Copiar o literal `flex items-center gap-3` dos vizinhos — dívida existente que esta revisão não propaga |
| 8 | Sem selo para `needs_review` | Selo na linha — promoveria um carimbo de backfill a estado de produto sem ação que o resolva |

## Explicitamente fora desta aprovação

Tela de lista de Engagements no menu lateral; listar os projetos de cada mandato expandidos na
linha; mover projeto entre mandatos; encerrar mandato em lote; expor `commercial_model` no portal
do cliente (One); aviso ao usuário Entrega de que a lista está recortada pelos projetos dele;
esqueleto de carregamento próprio da seção; superfície para o carimbo `needs_review`; a pendência
A2 do `language-map` §9; e qualquer edição em `frontend/src/` — o DAP precede a construção.

## Consequências que o board não decide, e que a implementação vai enfrentar

Registradas aqui porque afetam o custo e a corretude, não o desenho. Todas foram verificadas no
código, não supostas.

- **`commercial_model` ainda não existe.** Zero ocorrências de `commercial_model` ou
  `design_partner` em `backend/`, `frontend/src/` e `docs/`. O campo está entrando por **outra PR,
  em paralelo**; o board o desenha como se já existisse. **Esta é uma dependência declarada**: a
  seção só pode ser construída com a decisão B implementada depois que aquele campo estiver em
  `main` e no `EngagementSerializer`.
- **A contagem de projetos não está no payload.** `EngagementSerializer`
  (`serializers.py:466-479`) expõe `account_name`, `owner_name` e `status_display`, e **não** expõe
  contagem de projetos. Dois caminhos, e eles significam coisas diferentes na tela: (a) anotar
  `projects_count` no `get_queryset` conta **todos** os projetos do mandato; (b) buscar
  `/projects/?client={id}` e agrupar no cliente conta só os **visíveis para quem olha**, porque
  `ProjectViewSet` é `ProjectScopedMixin`. Para um usuário Entrega os dois números divergem. O
  caminho (b) tem a vantagem de não custar campo novo na API e de casar com o recorte que a mesma
  pessoa já vê; o (a) diz a verdade sobre o mandato. **A escolha muda o significado do número na
  tela e deveria ser decidida antes de implementar.**
- **O nome do patrocinador também não está no payload** — `EngagementSerializer` expõe `sponsor`
  como id, sem `sponsor_name`. Aqui não há custo: `ClientDetailPage` já carrega
  `/contacts/?client={id}` no mesmo `Promise.all` (`:72`), então o nome se resolve no cliente com
  **zero requisição a mais**, e o mesmo array alimenta o `<select>` de patrocinador do formulário.
- **`owner` é obrigatório e o formulário desenhado não o expõe.** `Engagement.owner` é
  `ForeignKey(User, on_delete=PROTECT)` não-nulo e `EngagementSerializer` o traz como campo
  gravável. O formulário do board tem sete campos e nenhum deles é "Responsável", por decisão de
  desenho — a seção vive dentro do detalhe do cliente, onde quem cria é quem está logado. A
  implementação precisa preenchê-lo em `perform_create` com `request.user`, e **o precedente
  existe no próprio código**: `convert-to-project` cria o mandato de escopo único com
  `owner=request.user` (`views.py:1016-1021`). Se o produto quiser um responsável escolhível, isso
  é um campo a mais e uma revisão nova do DAP.
- **Arquivar mandato com projeto vivo é 409, e é o erro mais provável da seção.**
  `EngagementViewSet.perform_destroy` (`views.py:1113-1124`) levanta `StateConflict` com a
  mensagem que o board desenha literalmente. A linha que mais convida a arquivar — a que tem três
  projetos — é justamente a que vai recusar. Isso é comportamento correto e desenhado, não defeito.
- **A Entrega pode ver menos mandatos do que a conta tem, sem nenhuma indicação.**
  `EngagementViewSet.get_queryset` filtra por `projects__in=Project.objects.visible_to(user)`. Um
  usuário Entrega vê só os mandatos de que participa; a contagem do cabeçalho ("2 engagements
  ativos nesta conta") vai refletir o recorte dele, não a conta. Um aviso está **reservado** e fora
  desta aprovação; se ele for pedido depois, é revisão nova.
- **Arquivar a conta arquiva os mandatos junto**, na mesma transação (`views.py:757-759`). A seção
  não precisa fazer nada a respeito, mas quem for testar a tela precisa saber.
- **A tela já está no gate de acessibilidade.** `{ path: "/clientes/1", name: "Detalhe do cliente" }`
  está em `e2e/matrix.ts:21`, então a seção nova entra em `e2e/a11y.spec.ts` (25 telas × 3
  larguras, contraste AA incluído) **sem uma linha nova na matriz**.

## Contraste

O board traz a tabela completa. O que importa registrar aqui: **nenhum par novo é introduzido**.
Os pares da marca são reuso das medições já feitas (`ink`/branco 18,9:1, `muted`/`canvas` 7,4:1,
`brand-500`/branco 4,96:1, `danger`/`danger-50` 5,6:1). Os cinco pares da escala de selo e do
`.metric-icon` já estão em produção e só não tinham a medição escrita — foram calculados para este
pacote: `brand-500`/`brand-50` 4,53:1, `success`/`success-50` 5,21:1, `warning`/`warning-50`
4,84:1, `info`/`info-50` 6,16:1, `slate-600`/`slate-100` 6,91:1. A pílula `.state` é 11px em peso
600, medida contra o mínimo de **texto normal (4,5:1)**; os quatro passam.

Estes números não substituem `e2e/a11y.spec.ts`, que é o árbitro. **Quando o axe e o tom
discordarem, cede o tom.**

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que está sendo pedido | **visual** e **copy** da revisão 1 da seção, com as decisões **A** e **B** aprovadas explicitamente |
| Aprovado por | Daniel Campos |
| Data | 2026-08-28 |
| Revisão aprovada | r1 |
| Decisão **A** | **A1 — "Engagements"**, o termo canônico em inglês como título, com a copy em volta em pt-BR |
| Decisão **B** | **B1 — as duas pílulas sempre visíveis**: "Pago" em `.state--off`, "Design partner" em `.state--0` |
| Explicitamente **não** aprovado | o que está na seção "Explicitamente fora desta aprovação" |

**Status: aprovado.** Visual e copy da revisão 1, com A1 e B1.

**Consequência de A1, registrada na aprovação:** a mensagem de conflito que
`EngagementViewSet.perform_destroy` levanta diz "engajamento" em português. Com o título em inglês,
a tela mostraria **três** palavras para o mesmo conceito — `Engagements` no cabeçalho, "engagement"
na copy corrente e "engajamento" vindo do servidor. A implementação troca essa string junto; é
mudança de copy de backend que a decisão A arrasta, e ela não estava no board porque o board não
traça consequências fora da tela.
Aprovação da revisão 1 não é aprovação de uma revisão posterior: um pacote materialmente alterado é
revisão nova e precisa do próprio registro.
