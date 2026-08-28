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

**O contrato `/api/v1/` do pipeline.** `OpportunitySerializer.project` e `project_archived`
mantêm nome e forma — um id ou nulo, nunca uma lista. Passam a devolver o projeto vivo mais
antigo, e só na falta de qualquer vivo o arquivado mais antigo. `CommercialPage.tsx` não mudou.

**`Project.client`.** Segue existindo, agora como **projeção**: a conta canônica é
`engagement.account`. Remover é a Fase 6. O que impede a projeção de divergir da fonte é
`Project.clean()` (`engagement.account_id == client_id`) — e é o único lugar que o faz.

**`Processo` e o Discovery estruturado.** Continuam pendurados na **conta** (FDD 039). O projeto
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

Um engajamento por `Client` que tenha ao menos um projeto, com `name = "Engajamento — <conta>"`
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

Tela de Engagement, navegação por engajamento, redesenho de `ClientDetailPage` ou `ProjectsPage`,
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
