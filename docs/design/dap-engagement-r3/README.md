# Design Approval Package — criar o projeto a partir do mandato

Classificação: `INTERFACE_CHANGE` · `BROWSER_REQUIRED`
Revisão: **3**
Status: **Approved**
Data: 2026-09-02

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | Posição, forma, campos e alcance da ação de criar projeto a partir de um mandato |
| Aprovado por | Daniel Campos, nesta sessão |
| Data | 2026-09-02 |
| Revisão aprovada | r3 |
| Decisões | **A1** (botão com rótulo na linha) · **B2** (modal) · **C1** (nome, degrau, início, prazo) · **D1** (todos os mandatos ativos) |
| Explicitamente não aprovado | Criar mandato por esta ação; escolher equipe, marcos ou faturas no ato; editar ou arquivar o projeto daqui; qualquer mudança na lista e nas ações das revisões 1 e 2; alterar o caminho de conversão do Comercial |

**Sobre a B2, que contraria a decisão 3 da r1 nesta seção:** a exceção é deliberada e o motivo fica
registrado — a decisão 3 governa formulários que **editam a lista que está ali** (contato, mandato);
criar projeto produz algo que **sai** desta tela. A r1 segue valendo para o que ela decidiu.
Produzido por: harness (Claude Code), sob `docs/engineering-os/workflows/design-approval.md`

> Este artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para o
> código da aplicação. As revisões 1 e 2 continuam valendo; esta decide **apenas** como um projeto
> nasce a partir de um mandato já existente.

## Por que existe um gate

`Project.engagement` é `NOT NULL`: todo projeto pende de um mandato. Hoje há **um** caminho para
criar projeto na SPA — o modal "Criar projeto" do Comercial, que exige oportunidade **ganha** e
sempre carimba o mandato como `paid`. O Design Partner não passa por venda, então esse caminho não
existe para ele: o mandato nasce (agora sozinho, na assinatura do acordo) e o Discovery não vira
projeto sem um `POST /projects/` fora da tela.

A r2 aprovou a seleção do instrumento de origem e listou como **explicitamente não aprovado**
"criação/upload/assinatura do acordo dentro do formulário". Criar projeto dali é superfície nova na
mesma seção, e por isso volta ao gate em vez de entrar por julgamento.

Não é só o Design Partner: uma Transformation Partnership origina **vários** projetos ao longo do
mandato (ADR 0050), e hoje o segundo também só nasce por API.

## Artefato

| Arquivo | O que é |
| --- | --- |
| `board.html` | Renderização auto-contida; abre sem build, toolchain ou rede |
| `board-desktop.png` | Captura congelada a 1280px |
| `board-mobile.png` | Captura congelada a 390px |

## Decisão A — onde a ação mora

A seção lista mandatos em `.row`, cada um com `.metric-icon`, `.row-main` e um par de ícones
(Editar, Arquivar) à direita.

- **A1 — botão com rótulo, na linha do mandato.** "Novo projeto" ao lado dos dois ícones.
- **A2 — terceiro ícone**, no grupo de Editar/Arquivar.
- **A3 — botão único no cabeçalho da seção**, que pergunta de qual mandato.

**Recomendação: A1.** A A2 esconde a ação mais consequente da seção atrás de um ícone sem rótulo,
ao lado de duas ações de manutenção — criar projeto não é da mesma família que editar nome. A A3
repete o beco que `App.tsx` já rejeitou para a Priorização: ação que abre perguntando "qual?"
quando o "qual" está na tela.

O preço da A1 está declarado: a linha do mandato fica mais cheia, e no celular o botão desce para
baixo do texto.

## Decisão B — modal ou formulário embutido

Aqui **dois precedentes da casa discordam**, e é por isso que a decisão existe:

- a **decisão 3 da r1** governa esta seção e diz *sem modal*: os formulários de Contatos e de
  Engagement abrem dentro do próprio painel;
- o **"Criar projeto" que já existe** (`CommercialPage.tsx`) é um `<Modal>`, com `Field` e
  `.form-grid`, pedindo início e prazo.

- **B1 — embutido**, no molde da própria seção.
- **B2 — modal**, no molde do outro "Criar projeto".

**Recomendação: B2.** A decisão 3 vale para formulários que **editam a lista que está ali** —
contato, mandato. Criar projeto produz algo que **sai** desta tela (o projeto vive em `/projetos`),
e o modal marca essa saída. Mais forte que a simetria de forma: um usuário que já criou projeto
pelo Comercial encontra a mesma caixa, com os mesmos campos, no mesmo lugar da cabeça. Divergir aí
custaria mais que divergir do padrão local da seção.

Se a preferência for coerência interna da seção, a B1 é defensável e não está errada.

## Decisão C — o que o formulário pede

O modal do Comercial pede **só** início e prazo, porque herda o serviço da oportunidade. Aqui não
há oportunidade da qual herdar.

- **C1 — nome, degrau, início, prazo.**
- **C2 — só início e prazo**, como o do Comercial, com o degrau em branco.

**Recomendação: C1**, e o degrau é o motivo. `kickoff.template_for` escolhe o cronograma **pelo
`tier` do serviço** e, sem serviço, cai num template genérico — o projeto nasceria sem os marcos do
Discovery Sprint (walkthrough, apuração do custo, Executive Readout) e ninguém veria que faltou.
O nome entra junto porque "Discovery Sprint — Rio Home Care" e "Continuidade 2027" são coisas
diferentes dentro do mesmo mandato, e derivar um nome aqui esconderia essa escolha.

Só degraus **vendáveis** aparecem: oferta de aquisição não gera projeto (invariante 6 do mapa de
linguagem), e o backend recusa com 400.

## Decisão D — quais mandatos oferecem a ação

- **D1 — todos os mandatos ativos.**
- **D2 — só os `design_partner`.**

**Recomendação: D1.** A D2 resolveria o caso de hoje e criaria o de amanhã: a Transformation
Partnership origina vários projetos por desenho, e o segundo continuaria só por API. Mandato
encerrado (`closed`) não oferece a ação — projeto novo em mandato encerrado é contradição.

## Estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Linha do mandato | ação disponível | sim |
| Linha do mandato | mandato encerrado (sem ação) | sim |
| Formulário | preenchimento, com degraus vendáveis | sim |
| Formulário | erro do servidor | sim |
| Seção | sem permissão de escrita | sim, preserva a r1 |
| Linha do mandato | contagem de projetos após criar | sim |

## Proveniência visual

Nenhum valor visual novo. `.btn`, `.btn--secondary`, `Modal`, `Field`, `.form-grid`, `.field`,
`.alert--error` — todos já consumidos pelas revisões anteriores e pelo modal do Comercial.

## Fora da aprovação

- Alterar a lista, os selos ou as ações aprovadas nas revisões 1 e 2.
- Criar mandato a partir desta ação.
- Editar ou arquivar o projeto criado, daqui.
- Escolher membros de equipe, marcos ou faturas no ato da criação.
- Mudar o caminho de conversão do Comercial.

## Notas para implementação

- A ação chama uma rota própria com guarda de papel, e não `POST /projects/` cru: o `RolePermission`
  hoje só deixa **admin** criar projeto, e a seção é visível a Vendas.
- O backend semeia marcos e tarefas (`kickoff.seed_work_items`) e faturas
  (`invoices.seed_invoices`, que devolve zero quando o valor contratado é zero — o caso do Design
  Partner) dentro da mesma transação.
- `seed_work_items` **não** é idempotente: a rota precisa de guarda contra duplo clique.
- A copy de `kickoff.finalize` afirma "a partir de uma oportunidade ganha" e é falsa neste caminho;
  precisa ser parametrizada.
- `projects_count` na linha é recortado por `project_scope_q` — dois usuários veem números
  diferentes, e isso não muda aqui.
