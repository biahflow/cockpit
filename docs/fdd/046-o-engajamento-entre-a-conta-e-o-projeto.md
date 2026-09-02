# FDD 046 — O engajamento entre a conta e o projeto

> **Segunda fatia da ontologia operada (ADR 0050).** Entra o `Engagement`, o mandato de
> transformação que a conta contratou, e todo projeto passa a pertencer a exatamente um. A origem
> comercial do projeto deixa de ser 1-1, para a venda recorrente caber no modelo — e a garantia de
> que o botão "converter" não duplica projeto sai do banco e vira ato explícito na rota.

## Jornada

Uma conta compra um Discovery Sprint. Vira projeto. Meses depois compra um Feasibility, e depois
um PROVE. Três projetos, três vendas, e — para quem olha o Pulse — nenhuma relação entre eles além
de compartilharem o nome do cliente na tela.

Isso já era desconfortável. Virou defeito quando a casa passou a vender a Transformation
Partnership (ADR 0048): um contrato mensal e recorrente, que origina vários projetos ao longo do
mandato. O modelo tinha `Project.opportunity` como `OneToOneField`, então o **segundo** projeto
daquele contrato não tinha como apontar para a venda que o pagou. Ele nascia órfão de origem, e
com ele o funil por origem, o ciclo médio comercial e a receita por fonte — que leem exatamente
esse campo — passavam a contar uma história incompleta.

O outro lado do mesmo buraco é uma pergunta que ninguém conseguia responder olhando o produto:
**como vai a transformação daquela conta?** Existe a conta, que agrega tudo o que já se vendeu
para ela desde sempre. Existe o projeto, que agrega uma entrega. Entre os dois faltava o mandato —
o conjunto de vendas e projetos que são o *mesmo trabalho*, com um patrocinador, um começo, uma
definição de sucesso e um fim. Sem ele, a resposta era somar projetos a olho, e mudava conforme
quem somava.

## O que esta fatia entrega

**`Engagement`, o mandato como entidade.** Pende da conta (`account`), tem `name`, o `mandate` em
texto, um `sponsor` opcional (contato da própria conta), um `owner`, `status`
(`active`/`paused`/`closed`), `started_at`, `ended_at` e `success_definition`.

```
Account 1:N Engagement
Engagement 1:N CommercialOpportunity
Engagement 1:N Project
CommercialOpportunity 1:N Project     (origem, opcional no Project)
```

**Todo projeto pertence a um engajamento** — a coluna é NOT NULL. A venda avulsa **não** é
exceção: a `convert-to-project` cria um mandato de escopo único quando o payload não traz um,
usando o título e o escopo da oportunidade. É a decisão D3 do mapa de linguagem, e a razão dela é
prática: um `engagement` opcional custaria dois caminhos em cada agregador, cada permissão e cada
tela, e o caminho raro é o que ninguém testa.

**A origem comercial vira 1-N.** `Project.opportunity` vira
`Project.originating_commercial_opportunity`, `ForeignKey` opcional. É o que destrava a venda
recorrente.

## A invariante que mudou de lugar

Até esta fatia, "uma oportunidade vencida converte exatamente uma vez" era garantia **de banco**: o
`OneToOneField` a impunha, e a segunda conversão morria num `IntegrityError` que virava 409.

Só que essa garantia proibia duas coisas de uma vez, e apenas uma devia continuar proibida:

| O que era impedido | Continua proibido? |
| --- | --- |
| Dois projetos com a mesma origem comercial | **Não** — é o requisito da venda recorrente |
| Duplo clique em "converter" criando projeto duplicado | **Sim** — sempre foi defeito |

O banco não distingue as duas, então a garantia saiu dele e virou ato explícito na rota:

1. **O guard**: 409 quando já existe projeto **vivo** com aquela origem.
2. **`select_for_update()`** sobre a oportunidade, dentro da transação. É o que o `IntegrityError`
   dava de graça e deixou de dar — sem a trava, duas requisições simultâneas leem "não há projeto"
   ao mesmo tempo e ambas criam.

Projeto adicional com a mesma origem é legítimo e nasce por `POST /projects/`, com `engagement` e
`originating_commercial_opportunity` explícitos. Um botão que duplica sem ninguém pedir e uma rota
que duplica porque foi pedida são coisas diferentes.

**Uma garantia que sai do banco só continua valendo enquanto é testada**, e é por isso que
`tests/regression/test_conversion_is_single_use.py` cobre as duas metades — o 409 e a presença da
trava.

### O último beco da FDD 025 fecha aqui

Como o guard olha projeto **vivo**, reconverter uma oportunidade cujo único projeto está arquivado
passa a responder **201**, e não mais 409. Antes o slot do `OneToOneField` continuava ocupado por
um projeto que a interface esconde, e a única saída oferecida era restaurá-lo — a saída errada
para quem arquivou de propósito e quer recomeçar.

É mudança de comportamento do contrato, deliberada. O caminho antigo (restaurar o projeto) segue
disponível.

## O que **não** mudou

**O recorte de acesso da Entrega.** Continua sendo `ProjectMember` (RFC 0003, ADR 0010).
`project_scope_q` e `ProjectScopedMixin` não foram tocados.

A visibilidade do engajamento **deriva** dos projetos, nunca o contrário: a Entrega vê os mandatos
que têm ao menos um projeto visível para ela. Inverter isso — "vê o mandato, então vê os projetos
dele" — seria ampliação silenciosa de privilégio, porque o mandato agrupa a conta inteira e o
sintoma seria uma lista um pouco maior, não um erro. Há regressão dedicada a isso
(`tests/regression/test_engagement_nao_amplia_escopo.py`).

**O contrato `/api/v1/` do pipeline.** `CommercialOpportunitySerializer.project` e `project_archived`
mantêm nome e forma — um id ou nulo, nunca uma lista. Passam a devolver o projeto vivo mais
antigo, e só na falta de qualquer vivo o arquivado mais antigo. `CommercialPage.tsx` não mudou.

**`Project.client`.** Segue existindo, agora como **projeção**: a conta canônica é
`engagement.account`. Remover é a Fase 6. O que impede a projeção de divergir da fonte é
`Project.clean()` (`engagement.account_id == client_id`) — e é o único lugar que o faz.

**`Process` e o Discovery estruturado.** Continuam pendurados na **conta** (FDD 039). O projeto
segue sendo proveniência opcional (`source_project`, `SET_NULL`), e nada disso passou a pender do
projeto nem do engajamento.

## Permissões

| Papel | `/engagements/` |
| --- | --- |
| Admin | tudo |
| Vendas | leitura e escrita — o mandato é o que a casa vendeu, e quem negocia é quem descreve |
| Entrega | **somente leitura**, e só os mandatos com projeto visível |

A assimetria é a decisão: quem entrega precisa saber a que mandato o projeto pertence, sem poder
redefinir o que foi contratado.

`Engagement` **não** entra em `PROJECT_OF` — ele não pende de um projeto, são os projetos que
pendem dele. A permissão de objeto tem um ramo próprio, que faz a pergunta inversa por
`Project.objects.visible_to(user)`, a única expressão da regra.

## Arquivamento

Soft delete, como o resto (FDD 025), e com as duas pontas fechadas:

- **Arquivar mandato com projeto vivo é 409.** `ProjectViewSet` nunca olha o `archived_at` do
  engajamento, então arquivá-lo deixaria projetos listados apontando para um mandato escondido.
- **Arquivar a conta leva os mandatos junto**, na mesma transação, como já acontece com os
  contatos. O engajamento é listado sozinho em `/engagements/?account=`, então cairia na regra de
  órfão; mas chegar ali já significa que não sobrou projeto nem oportunidade viva na conta, e um
  mandato sem nenhum dos dois não é trabalho em aberto — é o resíduo dele.

## Migração, em três passos

| Migração | O que faz |
| --- | --- |
| `0055_engagement` | Cria `Engagement`; `Project.engagement` **nullable**; `Opportunity.engagement`; renomeia `Project.opportunity` e a converte em FK 1-N |
| `0056_backfill_engagement` | Um engajamento por conta que tenha projeto; aponta os projetos; carimba `needs_review` |
| `0057_project_engagement_obrigatorio` | `Project.engagement` vira NOT NULL |

**Por que três arquivos e não um.** Nenhuma migração do repositório fazia isso antes — `0025`,
`0048` e `0050` resolvem esquema e dado juntos. A separação existe para o deploy ser reversível:
entre a `0056` e a `0057` há uma janela em que a coluna está populada e ainda aceita nulo, e nela
o código antigo roda, o novo também, e a volta é `migrate core 0055` sem perder dado. Numa
migração só, subir o código e apertar a restrição viram o mesmo instante, e desfazer exige mexer
em esquema e dado ao mesmo tempo, sob pressão.

O passo 3 **falha** se o passo 2 deixou algum projeto para trás, e falhar ali é o comportamento
certo: descobrir um projeto órfão no `ALTER TABLE` é melhor que descobrir num `NULL` que atravessa
a aplicação porque a coluna nunca foi fechada.

### O backfill agrupa por conta, e sinaliza o que não sabe

Um engajamento por `Account` que tenha ao menos um projeto, com `name = "Engajamento — <conta>"`
(nome derivado e reconhecível como automático, para ser trocado em vez de aceito por inércia),
`owner = client.owner`, `status = active` e `started_at` = o menor `start_date` entre os projetos.
Conta sem projeto **não** ganha engajamento: o mandato nasce quando a primeira venda vira projeto.

Agrupar por conta é a única regra que a base sustenta, e ela está **errada** para a conta que
comprou duas jornadas distintas com anos de intervalo — aquilo eram dois mandatos e vira um só.

A migração **sinaliza em vez de decidir**. `needs_review = True` quando:

1. há **mais de um `service_id` distinto** entre os projetos da conta (nulo não conta: projeto sem
   serviço é lacuna de cadastro, não sinal de outra jornada); **ou**
2. há **mais de 180 dias** entre o `start_date` de dois projetos consecutivos.

As duas são deliberadamente grosseiras. Separar exigiria saber o que foi contratado, e isso não
está em coluna nenhuma: a migração que adivinhasse produziria uma divisão plausível e falsa, que é
pior que uma junção visivelmente grosseira, porque ninguém a revisa. Falso positivo é barato
(alguém olha e desmarca); falso negativo é caro (dois mandatos somados para sempre, e ninguém
procura). Por isso o "ou" é inclusivo.

Separar os mandatos carimbados é trabalho humano. Não há automação prevista.

## Fora de escopo

Tela de Engagement, navegação por engajamento, redesenho de `AccountDetailPage` ou `ProjectsPage`,
e exposição do engajamento nos agregadores (`/clients/overview/`, `/risk/`, `/health/`,
`/dashboard/`). Interface nova exige Design Approval Package, e não há um aprovado para esta
superfície. O frontend recebeu apenas os tipos.

## Referências

- ADR 0050 — a decisão e as alternativas recusadas
- ADR 0048 — a escada FDE inteira como degrau comercial (de onde vem a venda recorrente)
- FDD 044, ADR 0049 — a fatia anterior da ontologia
- FDD 025 — arquivamento sem beco sem saída
- RFC 0003, ADR 0010 — o recorte de projeto da Entrega
- `docs/ontology/language-map.md` — D3 e invariante 7

## Emenda (28/08/2026) — o mandato passa a registrar a condição comercial

`Engagement` ganha `commercial_model` (`design_partner` | `paid`, default `paid`). Hoje ele não
dizia **em que condição** nasceu, e há dois modos reais: a conta que paga, e o **design partner** —
que recebe Discovery sem cobrança em troca de servir de caso e de campo de prova. Sem o campo, os
dois eram a mesma linha.

**O schema nunca exigiu o caminho Won, então nada foi derrubado.** Não existe FK nem constraint de
`Engagement` para `CommercialOpportunity` — a direção é a inversa (`CommercialOpportunity.engagement`,
opcional, `SET_NULL`) —, e o `EngagementSerializer` sempre exigiu só `account`, `name` e `owner`.
Um mandato de design partner já podia ser criado por `POST /engagements/` sem nenhuma oportunidade
antes desta emenda, e continua podendo: a emenda acrescenta um rótulo a uma origem que já era
livre, não abre um caminho novo. `convert-to-project` — o único lugar que cria `Engagement`
automaticamente — passa a declarar `commercial_model=paid` **explicitamente** em vez de herdar o
default em silêncio: ali é pago por construção, porque a action exige oportunidade em "Ganho".

**A correção das linhas existentes não é migração, e não é comando de terminal.** `AddField` com
`default=paid` carimba todo `Engagement` já existente como pago, e isso é inferência, não registro:
as linhas vieram do backfill da `0056`, que criou um mandato por conta que **tinha projeto**, e
projeto veio de venda — nenhuma foi observada como design partner. Uma lista de nome de cliente
dentro de migração histórica envelhece na primeira renomeação e não roda em ambiente nenhum além
daquele para o qual foi escrita — e um comando rodado por operador tem o problema oposto: a lista
de contas de design partner cresce por venda, não por deploy, e reservar um script para cada conta
nova é fricção que o negócio não tem por que carregar. A correção passou a ser **o admin do
Django**: `Engagement` ganha `EngagementAdmin` (`backend/apps/core/admin.py`), com
`commercial_model` visível e filtrável na lista. Não é a tela de Engagement — essa exige Design
Approval Package, e não há um aprovado (ver "Fora de escopo") — é o único lugar onde quem não é
engenharia consegue ler e mudar o campo sem depender de shell.

**O campo não atravessa para o One.** `commercial_model` é dado comercial, e a §3 do
`docs/ontology/language-map.md` é explícita: o One nunca vê dado comercial. Dizer ao cliente que
ele é "design partner" ou "pago" é exatamente a classe de coisa que fica fora.
`portal.build_snapshot` continua emitindo `project.engagement` como `{id, name, status}`, sem o
campo novo — há regressão dedicada a isso.

**O que esta emenda não decide.** A pendência A2 do `docs/ontology/language-map.md` §9 ("Design
Partner é condição comercial de um degrau ou oferta própria?") continua aberta. Gravar o modo no
mandato e decidir se existe um sétimo degrau no catálogo são coisas diferentes: nenhuma regra de
preço, fatura ou catálogo lê este campo hoje.

## Emenda (28/08/2026) — o mandato ganha superfície no detalhe do cliente

A seção "Fora de escopo" acima dizia *"Tela de Engagement … Interface nova exige Design Approval
Package, e não há um aprovado para esta superfície"*. **Agora há**:
[`docs/design/dap-engagement-r1/`](../design/dap-engagement-r1/README.md), revisão 1, aprovado com
as decisões **A1** e **B1**. O pacote é a especificação da superfície, e é ele que governa forma e
copy — não esta FDD.

O que entrou: uma `<section className="panel">` em `AccountDetailPage`, **entre "Saúde da relação" e
"Satisfação"**, que lista os mandatos da conta com status, modelo comercial, patrocínio, período e
contagem de projetos, e permite criar, editar e arquivar. É a primeira superfície do produto onde a
espinha `Account → Engagement → Project` fica visível. O que **continua** fora: tela de lista no
menu, os projetos de cada mandato expandidos na linha, mover projeto entre mandatos, encerrar em
lote, `commercial_model` no portal do cliente, e superfície para o carimbo `needs_review`.

### A contagem de projetos é recortada pelo escopo de quem lê

`EngagementSerializer` passa a expor `projects_count`, anotado em `EngagementViewSet.get_queryset`
com `Count("projects", filter=… & project_scope_q(user, "projects"), distinct=True)` sobre projetos
vivos.

**Ela não é o total do mandato.** O DAP deixou a escolha em aberto e registrou que os dois caminhos
significam coisas diferentes na tela; a decisão é o recorte, por consistência com a regra do
`CLAUDE.md` de que agregador que escapa do queryset é *narrowed by hand* e tem teste próprio. Um
total cru contaria, para a Entrega, projetos que ela não pode ver — sinal fraco, mas ainda assim
informação sobre o que está fora do recorte dela, e este repositório não abre essa exceção.

**A consequência é assumida: dois usuários veem números diferentes para o mesmo mandato.** É
honesto — cada um vê o que alcança — e é o mesmo comportamento que `/clients/overview/`, `/risk/` e
`/health/` já têm. O aviso ao usuário Entrega de que a lista está recortada está **reservado** no
DAP e fora desta aprovação. O `distinct=True` não é enfeite: o recorte atravessa `projects__members`
e o filtro da Entrega atravessa `projects` de novo, e sem ele a repetição do join infla o número.

### O que mais mudou no contrato

- **`sponsor_name`**, read-only, nulo quando não há patrocinador — o board desenha "Patrocínio de
  {nome}" e o payload não trazia o nome.
- **`owner` deixa de ser obrigatório no `POST`.** `EngagementViewSet.perform_create` grava
  `owner=request.user` quando o payload não o traz, no precedente da `convert-to-project`: o
  formulário aprovado não pergunta quem é o responsável, porque quem cria o mandato dentro do
  detalhe do cliente é quem está logado. O campo **continua gravável** — relaxar exigência não é
  tirar o campo.
- **Copy: "engajamento" vira "engagement"** na recusa de arquivar mandato com projeto vivo. É a
  consequência que a decisão A1 arrasta e que o registro de aprovação do DAP anota: com o título em
  inglês, a tela mostraria três palavras para o mesmo conceito — `Engagements` no cabeçalho,
  "engagement" na copy corrente e "engajamento" vindo do servidor.

A guarda de conta da `convert-to-project` também teve a string trocada, mas ela é **ramo
inalcançável**: `ProjectSerializer.validate` recusa `engagement.account != client` antes, e a
comparação de cliente da própria action fecha o resto. Quem responde de fato ali é o serializer, com
uma mensagem que continua em português — é superfície de Projetos/Comercial, fora deste DAP, e
trocá-la é varredura própria. `test_a_guarda_de_conta_da_conversao_e_inalcancavel_pelo_serializer`
fixa o achado.

## Emenda (31/08/2026) — o instrumento assinado fecha a invariante 13

A emenda de `commercial_model` acima preservou a origem livre porque o schema não tinha vínculo.
Essa frase descrevia o estado implementado, mas contrariava D8 e a invariante 13 do mapa de
linguagem. A decisão humana da issue #62 resolve o conflito em favor da regra normativa, registrada
na [ADR 0058](../adr/0058-o-engagement-nasce-do-instrumento-assinado-e-o-legado-declara-a-lacuna.md).

Toda criação nova referencia exatamente um instrumento:

- `paid` → `originating_commercial_opportunity`, da mesma Account e ganha;
- `design_partner` → `originating_design_partner_agreement`, um Document da mesma Account com
  assinatura concluída e datada.

Design Partner **continua sem CommercialOpportunity de origem**. O que deixa de existir é o
Engagement novo sem instrumento nenhum. `convert-to-project` grava a oportunidade ganha nos dois
lados: como origem do Engagement e como primeira `CommercialOpportunity.engagement` daquele
mandato.

A migração `0074` não escolhe candidatos nem cria contrato retroativo. Todos os Engagements
anteriores entram com as duas referências nulas e `needs_review=True`; permanecem válidos até
remediação humana. Preencher a origem não limpa o carimbo automaticamente, pois ele também cobre a
ambiguidade de agrupamento herdada da migração 0056.

A interface segue o DAP
[`docs/design/dap-engagement-r2/`](../design/dap-engagement-r2/README.md), revisão 2 aprovada: na
criação, o modelo comercial mostra um único select com instrumentos elegíveis. Sem oportunidade
ganha ou acordo assinado, a ação fica desabilitada e orienta o pré-requisito. Upload, assinatura e
remediação em lote continuam fora dessa superfície.

## Emenda (02/09/2026) — o mandato origina projeto, e a parceria não fatura

A emenda de 31/08 fechou a invariante 13 pela origem do mandato. Ficou de fora o passo seguinte, e
ele era um beco: **o mandato nascia e o projeto não**. `Project.engagement` é `NOT NULL`, e havia um
único caminho para criar projeto na SPA — o modal do Comercial, que exige oportunidade **ganha** e
carimba o mandato como `paid`. Para o Design Partner, que por desenho não passa por venda, esse
caminho não existe: o Discovery não virava projeto sem um `POST /projects/` fora da tela.

### A rota é própria, e as três razões não são de estilo

`POST /engagements/{id}/create-project/` (`EngagementViewSet.create_project`), com guarda de papel
própria no molde da `convert-to-project`. Não é `POST /projects/` cru porque:

- **`POST /projects/` só passa para admin.** `RolePermission` fecha a Entrega e deixa Vendas só com
  leitura de `project`, e a seção de Engagements é visível a Vendas — quem negocia o mandato é quem
  cria o projeto dele. Afrouxar a permissão para resolver isto abriria a criação crua de projeto
  para todo o comercial, que é mais do que se pediu.
- **`POST /projects/` não semeia nada.** `perform_create` só grava o dono: sem marcos, sem tarefas,
  sem faturas, sem kickoff. Um Discovery Sprint nascido por lá perde os marcos que **são** a
  metodologia — walkthrough, custo do estado atual, Executive Readout.
- **A invariante 6 (oferta de aquisição não gera projeto) não roda no serializer.** Ela vive em
  `Project.clean()`, e o `ProjectSerializer` não chama `full_clean()`.

**A trava não é a mesma da conversão, e a diferença é sutil o bastante para enganar quem comparar
as duas.** Lá o `select_for_update` sustenta um "converte uma vez só". Aqui não há o que impedir —
um mandato origina vários projetos por desenho (ADR 0050, e é o caso da Transformation Partnership),
e o segundo é legítimo. A trava existe porque `kickoff.seed_work_items` **não** é idempotente: ela
serializa duas requisições simultâneas para que o duplo clique produza dois pedidos em fila, e não
dois cronogramas gravados um por cima do outro.

O mandato da rota entra no **corpo** antes da validação, em vez de `engagement_optional` mais um
`save(engagement=…)`. Com a segunda forma, duas chaves passariam a ser ignoradas em silêncio só
nesta rota: um `engagement` divergente seria sobrescrito — 201 para um pedido que escolheu outro
mandato — e a chave legada `client` deixaria de ser conferida contra a conta, porque
`ProjectSerializer.validate` só a compara quando tem o engajamento em `attrs`.

### Design Partner não fatura, e a guarda mora onde a cobrança se decide

Consequência que só apareceu com a rota nova: sem oportunidade de origem,
`invoices.contracted_value` cai no `Service.list_price` do degrau — e o Discovery Sprint vale
**R$ 3.000** desde a migração `0064`. Um mandato `design_partner` criando projeto por aqui semearia
dois rascunhos de cobrança contra exatamente quem a casa decidiu não cobrar.

A guarda entrou em `invoices.seed_invoices` e não na action, porque é ali que a cobrança se decide:
quem semeia fatura pergunta uma vez só, e a próxima rota que criar projeto herda a resposta em vez
de repetir a pergunta. A regra é sobre o **modelo comercial**, não sobre o degrau — mandato pago com
o mesmo Discovery Sprint continua faturando, e há teste para as duas metades.

### O kickoff parou de afirmar uma venda que não houve

`kickoff.finalize` dizia, no e-mail e na notificação, que o projeto nasceu *"a partir de uma
oportunidade ganha"*. Neste caminho não há venda: a frase seria falsa em todo projeto de Design
Partner. A origem virou parâmetro, com o texto anterior como default — a conversão não mudou, e há
teste afirmando que ela continua dizendo o que dizia.

Junto veio um corte em `notifications.notify`: `Notification.message` é `max_length=255`, e a frase
nova junta nome de projeto e de mandato, dois campos de 255 cada. O estouro trunca em silêncio no
SQLite e **levanta** no Postgres — e quem levanta é efeito de pós-commit, então o projeto já existe
e a rota devolveria 500 por causa do aviso.

### A superfície

Botão **"Novo projeto"** com rótulo na linha do mandato, e **modal** — DAP `dap-engagement-r3`,
decisões A1 · B2 · C1 · D1. A B2 é exceção deliberada à decisão 3 da r1 ("sem modal" nesta seção):
a decisão 3 governa formulários que **editam a lista que está ali**, e criar projeto produz algo que
**sai** desta tela. O formulário pede nome, degrau, início e prazo — o degrau porque
`kickoff.template_for` escolhe o cronograma pelo `tier`, e sem ele o projeto nasceria com marcos
genéricos sem nada ficar vermelho. Mandato encerrado não mostra o botão.
