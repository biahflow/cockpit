# Design Approval Package — o rótulo "cliente" e o `lifecycle_status` da Account

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **1**
Status: **Approved**
Data: 2026-08-28
Produzido por: harness (Claude Code), sob `workflows/design-approval.md`
Issue: #67 (ontologia, P1), fatia 2 de 4

> Este artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> dentro do código de aplicação. Nenhuma linha de `frontend/src/` muda nesta entrega.

## Por que existe um gate

A issue #67 tem, no meio dos renomes, um item que não é renome:

> `Account.lifecycle_status` ∈ `prospect` · `active` · `inactive`; rótulo "cliente" na UI só em
> `active`

A primeira metade é dado — um campo com um valor a mais, e uma migração. A segunda metade é
**superfície**: ela diz o que a tela pode chamar de cliente, e a tela hoje chama de cliente tudo.
Pela definição de `workflows/design-approval.md` isso é "alterar materialmente uma superfície
perceptível por humano", e a mesma página inclui na classificação os estados de vazio e de erro —
que aqui não são detalhe, porque o estado novo nasce sem nenhum registro e o vazio dele é a
primeira coisa que alguém vai ver.

O que existe hoje, medido em `frontend/src/pages/ClientsPage.tsx`:

| Onde | Linha | O que diz |
| --- | --- | --- |
| Menu lateral | `components/Layout.tsx:17` | **Clientes**, rota `/clientes` |
| Pastilhas de filtro | `ClientsPage.tsx:12-13` | Ativos · Prospects (+ Todos, Arquivados) |
| Vazios | `ClientsPage.tsx:22-23` | "Nenhum cliente ativo" · "Nenhum prospect" |
| Formulário | `ClientsPage.tsx:57` | "Novo cliente" · "Nome do cliente" · "Cadastrar cliente" |
| Pílula da linha | `ClientsPage.tsx:60` | "Ativo" (`.state--0`) · "Prospect" (`.state--off`) |
| Situação (edição) | `ClientDetailPage.tsx:483` | mesmo `<select>` de duas opções |

O botão **"Cadastrar cliente" cria um prospect**. É a violação em forma mais nítida: não é uma
palavra mal escolhida num rótulo, é o produto afirmando uma relação comercial que ainda não
existe, no ato em que ela não existe.

Nenhuma aprovação vigente cobre esta superfície. O DAP GH-26 r1 aprovou marca e fundações no shell
e listou "as outras 20 telas de produto" como **não** aprovadas; o DAP perfil-e-contato r1 aprovou
o painel de Contatos do detalhe, não a listagem; o DAP engagement r1 aprovou a seção de Engagements
da mesma página, e nada além dela.

O gate fica **antes da construção da fatia 2**. O renome `Client` → `Account` no backend não
depende dele e segue em paralelo; o que espera aqui é a copy.

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

Três decisões, todas de copy. **Nenhuma forma nova, nenhum par de cor novo, nenhuma primitiva
nova.** Elas estão desenhadas lado a lado no board para serem escolhidas olhando.

### Decisão A — como a seção se chama, se ela contém prospects

O `language-map` §4 diz *rótulo "cliente" só em `active`*, e a §2 lista, para `Account`, o rótulo
comercial "Cliente (só com `lifecycle_status=active`)" e os nomes proibidos "Client (no modelo),
Empresa". A palavra portuguesa "Conta" **não** é proibida em nenhum lugar — ao contrário de
`Engagement`, que não tem tradução e por isso ficou em inglês no DAP anterior.

- **A1 — "Contas".** Menu, rota `/contas`, "Nova conta", "Nome da conta", "Cadastrar conta".
- **A2 — "Accounts".** O termo canônico em inglês, no molde da decisão A1 do DAP de Engagements.
- **A3 — manter "Clientes".** Nada muda no menu nem no formulário; a regra do §4 passa a valer só
  para a pílula.

**Recomendação: A1.** Ela é a única que resolve o problema onde ele está. A A3 deixa "Cadastrar
cliente" criando prospect, que é a violação inteira, e transforma a decisão do §4 numa regra sem
consequência visível. A A2 é defensável e eu não a recomendo por um motivo específico: o
precedente do Engagement foi *"em inglês porque não existe palavra em português"*, e aqui existe —
copiar a forma do precedente sem o motivo dele é como se herda vocabulário errado. Além disso a A2
custa uma palavra nova na boca do time comercial para nomear a coisa que eles já nomeiam bem.

O preço da A1 está declarado: **é a mudança de maior alcance deste pacote**. Muda um item do menu
lateral, a rota que as pessoas têm no favorito e sete strings. `/clientes` deve continuar
respondendo com redirecionamento para `/contas` — link antigo que morre é o mesmo defeito que a
`aliases.md` descreve para rota de API, na camada de cima.

### Decisão B — o que a pílula diz em cada um dos três estados

- **B1** — `prospect` → "Prospect" (`.state--off`) · `active` → **"Cliente"** (`.state--1`) ·
  `inactive` → "Inativo" (`.state--off`).
- **B2** — mantém "Ativo" em `.state--0` e acrescenta só "Encerrado" para o terceiro.

**Recomendação: B1.** É o que faz a palavra "cliente" carregar informação: ela passa a aparecer
exatamente onde a conta é cliente de fato, em vez de aparecer em toda parte e não distinguir nada.
"Ativo" é vocabulário de banco — diz que a linha não está arquivada, não que a empresa comprou.

Duas notas de desenho que a B1 arrasta e que ficam registradas:

- **`active` sai de `.state--0` (azul) para `.state--1` (verde).** `.state--1` é o "concluído/ok"
  do produto e é o que a satisfação e a saúde já usam para "está bem"; azul de informação é o tom
  errado para o estado que a operação inteira persegue. Contraste medido: 5,21:1, passa AA.
- **"Prospect" e "Inativo" dividem `.state--off`.** É deliberado, e é a regra que a ADR 0026
  escreveu para o neutro: nenhum dos dois é aviso nem falha. Quem os distingue é a palavra, não a
  cor — e é por isso que a Decisão B escolhe palavras.

"Inativo" e não "Encerrado" porque encerrar é ato, e o estado não é um ato: uma conta fica inativa
por parar de ter trabalho, sem ninguém encerrar nada. "Encerrado" já é, além disso, o rótulo de
`EngagementStatus.closed` na mesma página (`ClientDetailPage.tsx:38`), e duas coisas diferentes com
a mesma palavra a dois cliques de distância é como se cria a próxima linha do language map.

### Decisão C — o filtro ganha uma pastilha, ou `inactive` só aparece em "Todos"

- **C1** — cinco pastilhas: Todos · Prospects · Clientes · Inativos · Arquivados.
- **C2** — quatro, como hoje; a conta inativa aparece só em "Todos".

**Recomendação: C1.** O estado foi criado para responder "quem parou de comprar?", e sem pastilha
não há como fazer a pergunta. "Todos" continua trazendo os três estados vivos: inativo é uma conta
que existe, e some da lista só quem foi **arquivado** — os dois eixos são independentes e não devem
se confundir.

Copy do vazio de "Inativos", que é o estado que nasce vazio e portanto o primeiro a ser visto:

> **Nenhuma conta inativa**
> Inativa é a conta que já foi cliente e hoje não tem trabalho em andamento. Ela continua no
> histórico e volta a ser cliente quando uma oportunidade for ganha.

## O que este pacote **não** decide

- **Como uma conta vira `inactive`.** É comportamento, não superfície, e fica na fatia 2 com
  decisão própria. Hoje existe uma promoção automática — `signals.py:283-287` promove
  `prospect` → `active` quando uma oportunidade é ganha — e uma guarda que impede a regressão por
  PATCH (`ClientSerializer.validate_status`). A entrada em `inactive` **não** ganha automação
  nesta fatia: é escolha explícita de quem edita a conta, pelo mesmo motivo que `gate_outcome`
  entra só pela action — estado que muda sozinho e ninguém pediu é estado que ninguém explica
  depois. Se um dia houver automação, ela precisa de sua própria decisão.
- **A regra de despromoção.** `validate_status` hoje impede voltar de `active` para `prospect`
  quando já houve venda ganha. `active` → `inactive` **é** permitido, e é o caminho que o estado
  existe para ter; `inactive` → `prospect` continua proibido pela mesma razão de antes.
- **O renome de backend.** `Client` → `Account`, `status` → `lifecycle_status` e a rota
  `/accounts/` são a fatia 2 e não passam por este gate — a ADR 0052 já os cobre.
- **As outras telas.** `ClientDetailPage`, `LeadsPage`, `CommercialPage` e o Dashboard citam
  "cliente" em copy que **não** é rótulo de estado ("Cliente" como coluna, "cliente" em prosa).
  Elas não estão neste pacote e não mudam.

## Consequências que o board não desenha

- **`/clientes` precisa redirecionar.** Sob A1, a rota muda em `App.tsx:57-61` e o link antigo
  existe no navegador de todo mundo. Um `match` que devolve redirecionamento é o mínimo; ele fica
  até a `/api/v2/`, junto dos outros aliases.
- **`e2e/matrix.ts` e `e2e/a11y.spec.ts` nomeiam as telas.** As 24 telas × 3 larguras incluem a
  listagem; mudar o rótulo do menu mexe no seletor e no nome do caso. Está previsto.
- **O `<select>` "Situação" aparece em dois arquivos**, com as mesmas três opções. Um mapa
  compartilhado, no molde de `StatusDot.tsx`, e não duas listas — uma cópia por tela é a segunda
  definição que diverge sem nada ficar vermelho (ADR 0026).
- **A copy do vazio de "Ativos" hoje explica a promoção automática** (`ClientsPage.tsx:22`). Sob
  B1 ela precisa passar a dizer "Cliente" onde diz "Ativo", e continuar explicando a promoção,
  que não muda.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que está sendo pedido | **copy** da revisão 1, com as decisões **A**, **B** e **C** aprovadas explicitamente |
| Aprovado por | Daniel Campos |
| Data | 2026-08-28 |
| Revisão aprovada | r1 |
| Decisão **A** | **A1 — "Contas"**: menu, rota `/contas`, "Nova conta", "Nome da conta", "Cadastrar conta" |
| Decisão **B** | **B1 — "Prospect" · "Cliente" · "Inativo"**, com `active` saindo de `.state--0` para `.state--1` |
| Decisão **C** | **C1 — cinco pastilhas**, com "Inativos" própria |
| Explicitamente **não** aprovado | o que está nas seções "O que este pacote não decide" e "Consequências que o board não desenha" |

**Status: aprovado.** Copy da revisão 1, com A1, B1 e C1.

Três consequências que a aprovação arrasta e que ficam registradas aqui, porque o board não traça
consequência fora da tela:

- **`/clientes` precisa redirecionar para `/contas`.** O link antigo está no navegador de quem usa
  o produto todo dia, e link que morre é o mesmo defeito que a `aliases.md` descreve para rota de
  API, uma camada acima. O redirecionamento é alias com data: sai na `/api/v2/`, com o resto.
- **A copy do vazio de "Ativos" muda de nome, não de conteúdo.** Ela hoje explica a promoção
  automática (`ClientsPage.tsx:22`); sob B1 passa a dizer "Cliente" onde dizia "Ativo", e continua
  explicando a promoção, que não muda.
- **O `<select>` "Situação" vive em dois arquivos** e passa a ter três opções nos dois. Um mapa
  compartilhado, no molde de `StatusDot.tsx`, e não duas listas — uma cópia por tela é a segunda
  definição que diverge sem nada ficar vermelho (ADR 0026).

Aprovação da revisão 1 não é aprovação de uma revisão posterior: um pacote materialmente alterado é
revisão nova e precisa do próprio registro.
