# ADR 0050 — O Engagement como espinha dorsal, e a origem comercial deixando de ser 1-1

**Status:** aceita
**Data:** 2026-08-28

## Contexto

O modelo do Pulse ia da conta direto ao projeto: `Project.client` apontava para `Client`, e
`Project.opportunity` era um `OneToOneField` para a venda que o originou. Isso descreve com
precisão o que a casa vendia quando o modelo foi escrito — um projeto, uma venda, um cliente — e
descreve mal o que ela vende hoje.

Dois defeitos concretos, e nenhum deles é hipotético:

**A venda recorrente não cabe.** A Transformation Partnership (ADR 0048) é mensal e origina vários
projetos ao longo de meses. Com a origem em 1-1, o segundo projeto daquele contrato não tem como
apontar para a venda que o pagou: ou mente sobre a origem, ou fica sem nenhuma. O funil por
origem, o ciclo médio e a receita por fonte leem esse campo.

**Não existe onde a transformação mora.** "Como vai a transformação daquela conta?" não tem
resposta no modelo. Existe a conta (que agrega tudo o que já se vendeu a ela, para sempre) e
existe o projeto (que agrega uma entrega). Entre os dois falta o mandato: o conjunto de vendas e
projetos que são o **mesmo trabalho**, com um patrocinador, um início, uma definição de sucesso e
um fim. Sem ele, a resposta é somar projetos a olho, e ela muda conforme quem soma.

O mapa de linguagem (`docs/ontology/language-map.md`) já nomeava a entidade — `Engagement`, com a
decisão D3 registrada — e a fatia 2 da migração de ontologia é implementá-la.

## Decisão

**`Engagement` entra entre `Account` e `Project`, e todo projeto pertence a exatamente um.**

```
Account 1:N Engagement
Engagement 1:N CommercialOpportunity
Engagement 1:N Project
CommercialOpportunity 1:N Project     (origem, opcional no Project)
```

### Obrigatório, e a venda avulsa não é exceção

`Project.engagement` é NOT NULL (invariante 7 do mapa de linguagem). A venda avulsa cria um
engajamento de escopo único — a `convert-to-project` o cria sozinha quando o payload não traz um,
usando o título e o escopo da oportunidade.

A alternativa era `engagement` opcional, com o projeto avulso pendurado direto na conta. Ela custa
mais: cada agregador, cada permissão e cada tela passaria a ter dois caminhos, e o caminho raro é
justamente o que ninguém testa. Uma linha a mais na tabela é mais barata que um `if` a mais em
cada consumidor.

### `Project.client` sobrevive como projeção, com uma amarra

A conta canônica do projeto passa a ser `engagement.account`. `Project.client` fica, porque metade
do produto — agregadores, permissões, portal — ainda pergunta pelo cliente direto, e removê-lo é a
Fase 6 do renome.

Uma projeção sem amarra diverge da fonte em silêncio, e é o defeito que projeções introduzem. A
amarra é `Project.clean()`: `engagement.account_id == client_id`. Sem ela, um projeto apareceria
na carteira de uma conta e no mandato de outra, e nenhuma tela acusaria.

### A origem comercial vira 1-N — e a garantia de conversão única muda de lugar

`Project.opportunity` (`OneToOneField`) vira
`Project.originating_commercial_opportunity` (`ForeignKey`, 1-N, opcional).

**Esta é a parte que exige registro explícito, porque uma invariante documentada deixa de valer
como estava escrita.** Até aqui, "uma oportunidade vencida converte exatamente uma vez" era uma
garantia **de banco**: o `OneToOneField` a impunha, a segunda conversão morria num `IntegrityError`
e a view o traduzia em 409. Era barato e era sólido.

Só que essa garantia proibia duas coisas ao mesmo tempo, e só uma delas devia ser proibida:

1. **dois projetos com a mesma origem** — que é exatamente o requisito da venda recorrente;
2. **o duplo clique no botão "converter" criando projeto duplicado** — que continua sendo defeito.

O banco não distingue as duas, então a garantia sai dele e vira ato explícito na
`OpportunityViewSet.convert_to_project`, em duas partes:

- **o guard**, que recusa com 409 quando já existe projeto **vivo** com aquela origem;
- **`select_for_update()`** sobre a oportunidade, dentro da transação. É o que o `IntegrityError`
  fazia de graça e deixou de fazer: sem a trava, duas requisições simultâneas leem "não há
  projeto" ao mesmo tempo e ambas criam.

O `except IntegrityError` fica no lugar, mas **já não carrega unicidade nenhuma** — o comentário no
código diz isso. Ele passa a ser só o que transforma uma falha de integridade residual em 409 com
a transação inteira desfeita, em vez de 500 com projeto pela metade.

Projeto adicional com a mesma origem é legítimo e nasce por `POST /projects/`, com `engagement` e
`originating_commercial_opportunity` explícitos. Um botão que duplica sem pedir e uma rota que
duplica porque foi pedida são coisas diferentes, e agora o código as distingue.

### Consequência de comportamento: projeto arquivado deixa de bloquear a reconversão

O guard olha projeto **vivo**. Antes, o slot do `OneToOneField` continuava ocupado por um projeto
arquivado, e reconverter respondia 409 mandando restaurá-lo — a saída errada para quem arquivou de
propósito e quer recomeçar. Era o último beco da FDD 025, e ele fecha aqui: com 1-N, projeto
arquivado não ocupa lugar nenhum.

`OpportunitySerializer.project` e `project_archived` **mantêm nome e forma** — um id ou nulo, nunca
uma lista. Passam a devolver o projeto vivo mais antigo, e só na falta de qualquer vivo o
arquivado mais antigo.

### O engajamento não é fronteira de acesso

O recorte da Entrega continua sendo `ProjectMember` (RFC 0003, ADR 0010). `project_scope_q` e
`ProjectScopedMixin` não mudam.

A visibilidade do engajamento **deriva** dos projetos, e não o contrário:
`Engagement.objects.filter(projects__in=Project.objects.visible_to(user))`. Ver um mandato não dá
acesso a projeto nenhum dele — a inversão seria uma ampliação silenciosa de privilégio, porque o
mandato agrupa a conta inteira e o sintoma seria uma lista um pouco maior, não um erro.

Vendas escreve, Entrega **só lê**: o engajamento é o mandato comercial, e quem entrega precisa
saber a que mandato o projeto pertence sem poder redefinir o que foi contratado.

### Três migrações, e o precedente que elas abrem

`0055` (esquema), `0056` (backfill), `0057` (NOT NULL). Nenhuma migração do repositório fazia isso
antes — `0025`, `0048` e `0050` resolvem esquema e dado no mesmo arquivo.

A separação existe para o deploy ser reversível. Numa migração só, o instante em que o código novo
sobe é o mesmo em que a coluna deixa de aceitar nulo, e voltar atrás exige desfazer esquema e dado
juntos, sob pressão. Separadas, existe uma janela — depois da `0056`, antes da `0057` — em que a
coluna está populada e ainda aceita nulo: o código antigo roda, o novo também, e a volta é
`migrate core 0055` sem perder dado.

O backfill agrupa **por conta**: um engajamento por `Client` que tenha ao menos um projeto. É a
única regra que a base sustenta, e está errada para a conta que comprou duas jornadas distintas
com anos de intervalo. Ele **sinaliza em vez de decidir**: `needs_review = True` quando há mais de
um `service_id` distinto ou mais de 180 dias entre projetos consecutivos. Separar exigiria saber o
que foi contratado, e isso não está em coluna nenhuma — a migração que adivinhasse produziria uma
divisão plausível e falsa, que é pior que uma junção visivelmente grosseira, porque ninguém a
revisa.

## Consequências

- A venda recorrente passa a ter representação: várias vendas e vários projetos sob um mandato.
- "Como vai a transformação daquela conta?" passa a ser uma consulta, e não uma soma a olho.
- **A invariante de conversão única deixou de ser estrutural.** Ela agora vive em código, e código
  só continua valendo enquanto é testado: `tests/regression/test_conversion_is_single_use.py`
  cobre o 409 e a presença do `select_for_update`.
- Reconverter uma oportunidade cujo único projeto está arquivado passa a responder **201** em vez
  de 409. É mudança de comportamento do contrato, deliberada, e o caminho antigo (restaurar o
  projeto) continua disponível.
- `Project.client` fica com duas fontes possíveis até a Fase 6. O `clean()` é o que impede a
  divergência, e é o único lugar que o faz.
- O backfill agrupa jornadas distintas num mandato só nas contas antigas. `needs_review` marca as
  suspeitas; a separação é trabalho humano, e não há automação prevista para ela.
- `Engagement` é mais uma entidade com soft delete e regra de órfão: arquivar mandato com projeto
  vivo é 409, e arquivar a conta leva os mandatos junto.

## Alternativas consideradas

**Manter `Project.opportunity` 1-1 e representar a recorrência com uma oportunidade por projeto.**
Faria o pipeline exibir vendas que não aconteceram — cada renovação mensal viraria um card —, e o
funil mediria atos administrativos em vez de negociação. É o mesmo defeito que a ADR 0049 acabou de
corrigir para a qualificação.

**`Project.engagement` opcional.** Mais barata na migração e mais cara em todo consumidor: dois
caminhos por agregador, e o raro sem cobertura. A D3 do mapa de linguagem já tinha decidido o
contrário; esta ADR só a implementa.

**Engajamento como fronteira de acesso, substituindo `ProjectMember`.** Simplificaria o modelo de
permissão e ampliaria privilégio: participar de um projeto passaria a dar acesso a todos os outros
da mesma conta. Recusada — e há regressão fixando a recusa.

**Uma migração só, com backfill e NOT NULL juntos.** É o precedente da casa e é o que torna o
deploy irreversível na prática. O custo da alternativa é um arquivo a mais.

## Referências

- FDD 046 — o Engagement entre a conta e o projeto
- ADR 0048 — a escada FDE inteira como degrau comercial (de onde vem a venda recorrente)
- ADR 0049 — a qualificação como entidade (a fatia anterior desta migração de ontologia)
- ADR 0010, RFC 0003 — o recorte de projeto da Entrega, que esta ADR **não** altera
- FDD 025 — arquivamento sem beco sem saída
- `docs/ontology/language-map.md` — D3 e invariante 7

## Emenda (Issue #67 fatia 3, 28/08/2026) — os nomes de classe desta ADR mudaram

A ADR 0052 antecipou o renome de classe da issue #67 para antes da Fase 6, e a fatia 3 o executou.
Onde esta ADR diz `OpportunityViewSet.convert_to_project` e `OpportunitySerializer.project`, leia
`CommercialOpportunityViewSet` e `CommercialOpportunitySerializer`. Onde ela diz `Opportunity`, o
modelo hoje se chama `CommercialOpportunity`.

**Nada da decisão muda.** A tabela continua `core_opportunity` (`Meta.db_table`), a rota continua
`/api/v1/opportunities/` com `basename="opportunity"`, e o par `project`/`project_archived` do
serializer mantém nome e forma. O guard de 409 mais `select_for_update()` — a parte que esta ADR
existe para registrar — está no mesmo lugar, com o mesmo comportamento.

`Project.originating_commercial_opportunity` já tinha o nome canônico desde esta ADR; o que a
fatia 3 fez foi trocar o alvo da FK.
