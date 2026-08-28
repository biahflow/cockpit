# Aliases de compatibilidade — o que ainda se chama errado, e até quando

**Normativo.** Complementa [`language-map.md`](language-map.md) §5 e §7. A página do Notion vence
no significado; este espelho vence no rótulo dentro do repositório. `CLAUDE.md` e `AGENTS.md`
apontam para cá e não podem enfraquecê-lo.

O vocabulário canônico chegou ao Pulse antes do schema. A consequência é que, por algumas fases, o
repositório tem **dois nomes para a mesma coisa**: o nome que o modelo carrega desde 2025 e o nome
que a Ontology v1 diz que ele tem. Este documento lista esses pares, diz qual é o canônico e
declara **em que fase cada alias morre** — porque alias sem data de morte não é compatibilidade, é
o nome novo virando sinônimo permanente do antigo.

A guarda que sustenta isto é `backend/tests/test_vocabulario.py`, e a dívida que ela tolera está
declarada, linha a linha, em [`legacy-allowlist.txt`](legacy-allowlist.txt).

## Os aliases vivos

**"Renome" eram três coisas, e a ADR 0052 as separou.** O nome da **classe** morre na issue #67,
uma fatia por PR; o nome da **tabela** morre na Fase 6; a **rota** e a **chave de payload** morrem
na `/api/v2/`. A tabela abaixo tem uma linha por prazo, e não uma por conceito, porque era a
compressão delas em "renome físico na Fase 6" que fazia o mesmo termo significar duas coisas.

| Alias vivo hoje | Nome canônico | Onde vive | Morre em |
| --- | --- | --- | --- |
| tabela `core_client` | `core_account` | `Meta.db_table` | Fase 6 |
| rota `/api/v1/clients/` e chaves `client` / `status` | `/accounts/`, `account`, `lifecycle_status` | `urls.py`, `serializers.py` | `/api/v2/` |
| campo `Project.client` | `engagement.account` (é projeção, não alias) | `backend/apps/core/models.py` | Fase 6 |
| tabela `core_opportunity` | `core_commercialopportunity` | `Meta.db_table` | Fase 6 |
| rota `/api/v1/opportunities/` e chave `opportunity` | `/commercial-opportunities/` e `commercial_opportunity` | `urls.py`, `serializers.py` | `/api/v2/` |
| chave de payload `gate_outcome` | `gate_decision` | `serializers.py` | `/api/v2/` |
| tabelas `core_processo` / `core_processoetapa` | `core_process` / `core_processstep` | `Meta.db_table` | Fase 6 |
| rotas `/processos/` e `/processo-etapas/` | `/processes/` e `/process-steps/` | `urls.py` | `/api/v2/` |
| classe `Evidencia` (o dual-write) | `Evidence` + `Finding` | `backend/apps/core/models.py` | Fase 6 |

### Já pagos pela #67 — 28/08/2026

Quatro renomes de classe saíram da tabela porque deixaram de ser alias: o nome antigo não existe
mais em código. **Sair daqui não é o fim da dívida** — é o fim de *uma* das três, e as outras duas
continuam listadas acima.

**A #67 fechou com a fatia 4.** O que ela deixa para trás está inteiro nas linhas de cima, e são
duas coisas: as **tabelas** (`core_client`, `core_opportunity`, `core_processo`,
`core_processoetapa`) e a classe `Evidencia`, que a Fase 6 remove junto com o dual-write, mais
`Project.client`, que é projeção e não alias. As **rotas** (`/clients/`, `/opportunities/`,
`/processos/`, `/processo-etapas/`) e as **chaves de payload** (`client`, `status`, `opportunity`,
`gate_outcome`, `processo`, `etapa`) morrem na `/api/v2/`, e a v2 não nasce antes da Fase 6.

| Foi | É | Fatia |
| --- | --- | --- |
| `GateOutcome` / `gate_outcome` | `GateDecision` / `gate_decision` | 1 |
| classe `Opportunity` e 5 campos `opportunity` | `CommercialOpportunity` / `commercial_opportunity` | 3 |
| classe `Client`, 10 campos `client`, `status` | `Account` / `account` / `lifecycle_status` | 2 |
| classes `Processo` / `ProcessoEtapa` e 3 campos `processo`/`etapa` | `Process` / `ProcessStep` / `process` / `step` | 4 |

**`Project.client` sobreviveu à fatia 2 de propósito, e é a única exceção.** Ele não é alias: é a
**projeção** temporária cuja fonte canônica é `engagement.account` (ADR 0050), mantida honesta por
`Project.clean()`. Renomeá-lo para `account` criaria duas coisas com o nome canônico no mesmo
objeto — `project.account` e `project.engagement.account` — que podem divergir, e aí o nome
canônico deixaria de identificar a fonte. Quem o remove é a Fase 6.

`Evidencia` é o único que não é só renome, e por isso é o único que **não** entra na #67: a Fase 3
a **dividiu** em `Evidence` (o registro bruto) e `Finding` (a conclusão, com `epistemic_status`),
conforme a decisão D6. Trocar o nome sem dividir resolveria o idioma e preservaria o defeito de
linguagem que a divisão existe para corrigir. A classe legada segue de pé porque ainda tem leitor
vivo (`process.custo_do_estado_atual` e `ProcessDetailPage`), e quem a remove é a Fase 6, junto
com o dual-write. Os **campos** dela, esses sim, passaram a `process` e `step` na fatia 4 — renome
de campo é `RenameField`, e ele preserva linha e pk.

Depois da #67 sobra uma dívida com forma nova e nome antigo: a tabela `core_processo` guardando
linhas de uma classe chamada `Process`. É desconfortável no `dbshell` e é de propósito — o risco
que a espera protegia é o da **pk**, e pk é o que a §2b trata.

## As três regras

### 1. Alias é dívida com data

Enquanto o alias vive, **campo novo e código novo usam o nome canônico apontando para o modelo
legado**. É o que a Fase 1 fez: `Qualification.account` é uma `ForeignKey` para o modelo que ainda
se chamava `Client` quando ela foi escrita. O nome do campo é o compromisso público; o nome da
tabela é detalhe que a Fase 6 acerta.

A #67 não revoga essa regra — ela reduz o alcance dela. Depois de cada fatia, o modelo legado que
aquela fatia renomeou deixa de existir sob o nome antigo, e a regra passa a valer só para os que
ainda não foram renomeados. Enquanto isso, um campo canônico apontando para um modelo já renomeado
é só um campo com o nome certo apontando para a classe certa, que é onde tudo isto queria chegar.

Escrever `Qualification.client` "porque o modelo se chama Client" seria criar o alias de novo, em
código que nasceu depois da decisão — e é exatamente isso que a regra `client-como-organizacao`
reprova. Ela casa `client`, nunca `account`.

### 2. `/api/v1/` não quebra

A remoção dos aliases de rota é a **`/api/v2/`**, e a v2 só nasce depois de a Fase 6 concluir os
renomes físicos. Até lá `/api/v1/clients/` e `/api/v1/opportunities/` respondem como sempre
responderam, com o mesmo payload — inclusive depois de o modelo Python trocar de nome, porque
`basename` e `queryset` do router são independentes do nome da classe.

**Não há data de calendário; há ordem de fases.** Uma data que ninguém pode cumprir vira um
comentário `# TODO(2026)` que sobrevive a três reorganizações do time. A ordem, não: a Fase 6 não
começa antes da 5, e a v2 não nasce antes da 6.

### 2b. Seis pks são identidade pública — e a Fase 6 tem de preservá-las

**Normativo.** Todo renome de modelo desta migração se faz com `RenameModel`, que preserva tabela,
linhas e **pk**. Nunca com modelo novo mais migração de dados, ainda que a tabela nova ficasse mais
limpa.

Na #67 ele preserva ainda mais do que isso, e é o que autoriza antecipar o renome de classe: com
`Meta.db_table` fixado no nome legado **antes** da operação, `RenameModel` não emite SQL nenhum —
`alter_db_table` abre com `if old_db_table == new_db_table: return`. Cada fatia escreve as duas
operações na ordem, e a primeira é no-op por já ser verdade:

```python
migrations.AlterModelTable(name="client", table="core_client"),
migrations.RenameModel(old_name="Client", new_name="Account"),
```

Invertê-las, ou omitir a primeira, faz o banco renomear a tabela e renomeá-la de volta — duas
`ALTER TABLE` para chegar onde já se estava, num caminho em que falhar no meio deixa a tabela com
o nome errado. Ver ADR 0052.

A proibição não é estética. **Estas pks saíram deste repositório.** O snapshot do portal
(`portal.build_snapshot`) emite onze ids, e o One deriva chave de identidade de seis deles e a
**persiste** — medido no código de lá em 28/08/2026, não estimado:

| pk daqui | o que o One persiste | o que quebra se ela mudar |
| --- | --- | --- |
| `Client` (→ `Account`) | `organization.slug` = `biahflow-client-{id}` | organização órfã: o cliente perde acesso ao projeto, em silêncio |
| `Project` | `project.slug` = `biahflow-{id}` | o projeto inteiro é recriado ao lado, com membership, documentos indexados e histórico apontando para a linha velha |
| `Engagement` | `engagement.slug` = `biahflow-engagement-{id}` | duplicata do programa; os projetos ficam apontando para o antigo |
| `ProjectDeliverable` | `phase_deliverable.external_ref` | **o pior dos seis — ver abaixo** |
| `Document` | `document.external_id` | documento duplicado e reindexado; citação já dada ao cliente passa a apontar para a linha antiga |
| `Pendencia` | `pending_item.external_ref` | pendência duplicada, e o cliente recebe o aviso de novo |

**O entregável é o pior, e vale saber por quê.** O `external_ref` dele é o caminho da rota de
aceite do One (`/api/v1/me/deliverables/{external_ref}/acceptance`) e é por ele — **não por chave
estrangeira** (ADR 0077 de lá) — que a tabela de aceites se liga ao entregável. Aquela tabela
guarda a decisão do cliente: quem aprovou, quando, e o comentário de quem pediu ajuste. Se a pk
mudar, o registro da aprovação não some: ele **desgruda**, e passa a ser o aceite de um entregável
que ninguém mais acha. É o único dos seis em que o dado órfão é uma afirmação que o cliente fez.

Duas notas que completam o inventário, e que existem para ninguém generalizar demais:

- **`Meeting` não guarda id externo de propósito** — o One a recria por inteiro a cada sync. A pk
  de reunião pode mudar à vontade.
- **`notification.dedupe_key` congela alguns desses ids na linha** (`document:{external_id}`,
  `pending:{external_ref}:opened`). A consequência ali é de outra natureza e menor: não há órfão,
  há **reaviso** — o cliente recebe de novo um aviso que já tinha lido.

Os cinco ids restantes que o snapshot emite (`ProjectPhase`, `Milestone`, `Decisao`,
`DigitalEmployee`, `Meeting`) **não** são persistidos hoje do lado de lá. Isso é uma medição, não
uma garantia: se o One passar a derivar chave de um deles, ele entra nesta tabela **antes** de
entrar no código. A fronteira que importa é o snapshot — id que atravessa é id que alguém pode
começar a guardar.

O modo de falha, em todos os casos, é o pior possível: não é erro, é silêncio. Nenhum dos dois
lados levanta exceção, e o registro duplicado parece apenas um cadastro novo.

Enquanto isso, `project.account.id` e `project.client.id` continuam iguais na projeção — hoje por
construção (`Project.clean()` amarra `engagement.account_id == client_id`), e há teste que compara
os dois. Isso protege a invariante de **hoje** e não alcança a de amanhã, porque a migração ainda
não existe.

**Identidade tem de ser a pk estável da linha**, nunca valor recalculável — slug, hash do nome,
número de sequência por conta. Identificador que alguém pode recalcular é identificador que alguém
vai recalcular diferente.

Regra prática, para a fase que ainda não começou: **em toda travessia de nome, a linha e a pk
sobrevivem; só o rótulo muda.** Uma migração que crie linha nova para o mesmo fato precisa dizer,
no próprio arquivo, como o consumidor externo continua achando o registro antigo.

### 2c. Campo renomeia; **chave de payload** não

A #67 renomeia o campo junto da classe — `Document.opportunity` vira
`Document.commercial_opportunity`, `Contact.client` vira `Contact.account`, `Evidencia.etapa` vira
`Evidencia.step`. É `RenameField`, que
renomeia coluna e preserva linha e pk.

**O que não muda é o corpo da requisição.** Cada chave legada continua saindo no `GET` e continua
sendo aceita no `POST`/`PATCH`, com um mecanismo só para todas elas, e não uma cópia por
serializer:

- **leitura** — a chave antiga é um campo declarado com `source=` apontando para o canônico,
  `read_only=True`. As duas saem, com o mesmo valor.
- **escrita** — um mixin de serializer normaliza a chave antiga para a canônica antes da
  validação. Quando as duas vêm no mesmo corpo, **a canônica vence**: um corpo com as duas é
  confusão do chamador, e resolver pela nova é o que não trava quem já migrou. É a mesma regra que
  `apply-gate` usa desde a fatia 1.

O mecanismo é um só porque a alternativa é `if` de compatibilidade espalhado por dezessete
serializers, e o décimo oitavo esquece — que é a mesma razão de `StatusDot.tsx` guardar os mapas de
estado num lugar em vez de um por tela (ADR 0026).

Cada alias de escrita precisa de regressão. Sem ela, a linha do serializer não tem chamador
**dentro** do repositório — a SPA escreve o nome canônico — e a próxima varredura atrás do último
resquício do nome antigo a remove achando que está pagando dívida. Estaria quebrando a `/api/v1/`
em silêncio, no único lugar onde nada aqui dentro fica vermelho.

### 3. `legacy_` é o escape reservado

`legacy_opportunity` e `legacy_evidencia` são nomes **legítimos em código novo**, e a guarda os
deixa passar de propósito. Um campo com esse prefixo declara, no próprio nome, que aponta para o
registro antigo — que é o oposto de esconder o mapeamento atrás de um nome bonito. É o que permite
backfill e leitura dupla durante a transição sem que a coluna nova finja ser a canônica.

O prefixo não é permissão geral: `legacy_` diz "isto mapeia para o legado", não "isto está isento".
Um campo `legacy_client` que na verdade é a organização corrente continua sendo defeito — só que um
defeito que o revisor humano precisa pegar, porque a guarda não consegue.

## O que a guarda **não** reprova, e por quê

Referência ao nome legado é livre: `self.opportunity`, `opportunity_id`, `Client.objects.filter(…)`
e `from .models import Client` são uso do modelo que existe hoje, e o modelo existe hoje por
decisão. A guarda casa **declaração** — o ato de batizar. O detalhe está na docstring de
`backend/tests/test_vocabulario.py` e a decisão, na [ADR 0049](../adr/0049-a-ontologia-entra-pela-linguagem-antes-do-schema.md).

A única exceção é `GateOutcome`/`gate_outcome`: ali o identificador inteiro está errado em qualquer
posição, porque não existe uso legítimo do nome antigo.

## Termos ainda sem nome canônico

`Pendencia`, `Decisao`, `Risco`, `Satisfacao` e a família `Cobranca*` estão em português no modelo
e **a Ontology v1 não os cobre** — não há para onde renomeá-los ainda. Eles estão na allowlist
mesmo assim, e isso é deliberado: sem a linha, a ausência de decisão viraria ausência de dívida.

O caminho é o da §8 do language-map: o termo entra primeiro na página do Notion, depois aqui,
depois no Pulse.
