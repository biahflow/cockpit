# FDD 035 — Activities no CRM

## Jornada

O material do Notion trazido pela ADR 0030 tem uma database `Activities`: o registro de cada
interação comercial com uma conta — ligação, reunião, e-mail, nota — que hoje só existe como
memória de quem participou ou, na melhor das hipóteses, numa linha solta do `Opportunity.scope`.
Quem chega numa oportunidade parada não tem como responder "quando foi o último contato, e o que
foi dito" sem procurar a pessoa que fez a ligação.

O CRM deste portal já tem `Client`, `Contact` e `Opportunity` — os equivalentes diretos de
Accounts/Contacts/Opportunities do Notion (ADR 0030). Faltava só a quarta entidade: a que registra
o histórico de contato como dado consultável, não como texto solto.

## O que esta fatia entrega

Um modelo `Activity`: interação comercial (ligação, reunião, e-mail, nota) ligada sempre a um
`Client` e, opcionalmente, a uma `Opportunity` — desde que a oportunidade seja do mesmo cliente.
CRUD em `/api/v1/activities/`, com o mesmo regime de arquivamento reversível da casa (FDD 025).
No frontend, um painel "Interações" no detalhe do cliente (lista em ordem cronológica inversa +
formulário de criação + arquivar) e, no detalhe da oportunidade (modal do `CommercialPage`), o
mesmo painel filtrado pela oportunidade aberta.

## Critérios de aceite

1. **Vendas lê e escreve, Entrega só lê, admin tudo.** Mesmo regime de `client`/`contact`
   (`RolePermission`): a Entrega participa de oportunidades ganhas e projetos, mas não é quem
   registra o histórico comercial.
2. **A oportunidade, quando preenchida, tem de ser do mesmo cliente.** Um cliente errado no corpo
   da requisição — ou herdado de um formulário que trocou de cliente sem limpar a oportunidade —
   grava um registro que aponta para o histórico errado. Recusado com 400, no `clean()` do modelo
   e replicado no `validate()` do serializer (é o mesmo par que `Task`/`Document` já usam para
   validação cruzada).
3. **Filtro por cliente e por oportunidade.** `?client=<id>` alimenta o painel do
   `ClientDetailPage`; `?opportunity=<id>` alimenta o painel do detalhe da oportunidade.
4. **A Entrega só vê interação de cliente com projeto seu.** Mesma fronteira do `Contact`
   (`project_scope_q` sobre `client__projects`) — sem ela, a Entrega enxergaria o histórico
   comercial de clientes fora do seu escopo de projeto, o que a RFC 0003 já fecha para
   cliente/contato.
5. **Arquivar não perde o histórico.** `archive()`/`?archived=1`/`unarchive` no padrão da casa.

## Desvio consciente do spec de handoff

O spec de handoff sugeria `create_kwargs()` (padrão `PendenciaViewSet`) para gravar `owner` na
criação. Esse hook pertence a `ProjectScopedMixin`, e `Activity` não é um recurso de projeto — é
um recurso de cliente, como `Contact`. `ActivityViewSet` usa o mesmo mecanismo que
`ClientViewSet` já usa para o próprio `owner`: `perform_create` sobrescrito diretamente. O
resultado observável (owner = quem criou) é o mesmo; muda só o hook usado, e cada um está
disponível pela cadeia de mixins correta.

O frontend também não tem funções dedicadas em `api.ts` para `contact`/`pendencia` — essas telas
chamam `api<T>()` diretamente com a URL. `Activity` segue esse padrão real (nenhuma função nova
em `api.ts`).

## Testes

- `test_activities.py` — CRUD como Vendas, leitura/escrita negada para Entrega (403), Entrega
  não vê interação de cliente fora do seu projeto, admin gerencia qualquer cliente, oportunidade
  de outro cliente recusada (400) tanto pela API quanto pelo `clean()` do modelo direto, filtro
  por cliente e por oportunidade, arquivar e restaurar.
- `ClientDetailPage.test.tsx` — lista e registra interação, arquiva interação, Entrega não vê
  formulário nem botão de arquivar.
- `CommercialPage.test.tsx` — mesmo trio de casos, no painel do detalhe da oportunidade.

## Fora deste recorte

- **Timeline unificada de conta** (ligações + reuniões de projeto + decisões num só feed). Cada
  entidade continua na sua tela; cruzar as três é problema de agregação, não deste recorte.
- **Vínculo com `Meeting`** (reunião de projeto, com transcrição e IA). São entidades
  deliberadamente distintas: `Meeting` é de projeto e nasce de uma pauta de entrega; `Activity` é
  de cliente e nasce de um contato comercial. Fundi-las custaria a mesma coisa que a FDD 032
  documentou para `Pendencia`/`Decisao` — dois estados e dois propósitos que não cabem num
  modelo só.
- **Superfície de detalhe de oportunidade nova.** O spec de handoff previa criar uma tela dessas
  caso não existisse; ela já existe (o modal "Detalhe da oportunidade" do `CommercialPage`), e é
  onde o painel entrou.
