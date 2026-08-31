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
| rota `/api/v1/clients/` e chaves `client` / `status` | `/accounts/`, `account`, `lifecycle_status` | `urls.py`, `serializers.py` | `/api/v2/` |
| rota `/api/v1/opportunities/` e chave `opportunity` | `/commercial-opportunities/` e `commercial_opportunity` | `urls.py`, `serializers.py` | `/api/v2/` |
| chave de payload `gate_outcome` | `gate_decision` | `serializers.py` | `/api/v2/` |
| rotas `/processos/` e `/processo-etapas/` | `/processes/` e `/process-steps/` | `urls.py` | `/api/v2/` |
| chaves `kpi_baseline` / `kpi_current` (só leitura) | `Measurement(kind=baseline)` / `Measurement(kind=outcome)` | `serializers.py` | `/api/v2/` |
| chave `ai_opportunity` (só leitura) | `ai_potential` | `serializers.py` | `/api/v2/` |
| chave `client_consent` (só leitura) | `account_consent` | `serializers.py` | `/api/v2/` |

> **O recorte físico da Fase 6 foi concluído; a issue #70 permanece aberta.** Tabelas renomeadas
> (migração `0069`), dual-write e `Evidencia` removidos (migração `0068`), `Project.client`
> removido após prova automática de equivalência (migração `0070`), `ai_opportunity` renomeado
> para `ai_potential` (migração `0071`) e `client_consent` renomeado para `account_consent`
> (migração `0072`). A #70 só fecha depois do critério operacional que ela própria define e da
> `/api/v2/`, onde morrem rotas e chaves de payload; por isso a allowlist ainda não é zero.

### Já pagos pela #67 — 28/08/2026

Quatro renomes de classe saíram da tabela porque deixaram de ser alias: o nome antigo não existe
mais em código. **Sair daqui não é o fim da dívida** — é o fim de *uma* das três, e as outras duas
continuam listadas acima.

**A #67 fechou com a fatia 4, e a Fase 6 já pagou as tabelas.** O que a #67 deixou para trás eram as
**tabelas** (`core_client`, `core_opportunity`, `core_processo`, `core_processoetapa`) e
`Project.client`. As tabelas **saíram** na Fase 6 (migração `0069`, renome em lugar), e a classe
`Evidencia` também (migração `0068`, com o dual-write). Resta `Project.client`, que é projeção e não
alias. As **rotas** (`/clients/`, `/opportunities/`, `/processos/`, `/processo-etapas/`) e as
**chaves de payload** (`client`, `status`, `opportunity`, `gate_outcome`, `processo`, `etapa`)
morrem na `/api/v2/` — que agora **pode nascer**, porque as tabelas já foram concluídas.

| Foi | É | Fatia |
| --- | --- | --- |
| `GateOutcome` / `gate_outcome` | `GateDecision` / `gate_decision` | 1 |
| classe `Opportunity` e 5 campos `opportunity` | `CommercialOpportunity` / `commercial_opportunity` | 3 |
| classe `Client`, 10 campos `client`, `status` | `Account` / `account` / `lifecycle_status` | 2 |
| classes `Processo` / `ProcessoEtapa` e 3 campos `processo`/`etapa` | `Process` / `ProcessStep` / `process` / `step` | 4 |

**`Project.client` saiu na Fase 6** (migração `0070`). Ele era a projeção temporária cuja fonte
canônica é `engagement.account` (ADR 0050). A chave `client` continua saindo no `GET` como alias
de leitura (`source="engagement.account_id"`, `read_only`), e morre na `/api/v2/`.

`Evidencia` era o único que não é só renome, e por isso foi o único que **não** entrou na #67: a
Fase 3 a **dividiu** em `Evidence` (o registro bruto) e `Finding` (a conclusão, com
`epistemic_status`), conforme a decisão D6. Trocar o nome sem dividir resolveria o idioma e
preservaria o defeito de linguagem que a divisão existe para corrigir. A classe legada ficou de pé
enquanto teve leitor vivo (`process.custo_do_estado_atual` e `ProcessDetailPage`); a **Fase 6
(issue #70, migração `0068`) a removeu** quando o custo passou a ler o `Finding(fact)` e a tela
migrou para o split — ver a nota de Fase 6 abaixo. Os **campos** dela já haviam passado a `process`
e `step` na fatia 4 — renome de campo é `RenameField`, e ele preserva linha e pk.

Depois da #67 sobrava uma dívida com forma nova e nome antigo: a tabela `core_processo` guardando
linhas de uma classe chamada `Process`. Era desconfortável no `dbshell` e proposital — o risco que a
espera protegia é o da **pk**, e pk é o que a §2b trata. A **Fase 6 pagou** essa dívida (migração
`0069`): renomeou as tabelas em lugar, sem tocar na pk (nota abaixo).

### Fase 6 (issue #70) — o dual-write e a `Evidencia` saíram

A primeira fatia do recorte físico da Fase 6 removeu o dual-write e a `Evidencia` legada
(migração `0068`). O gatilho era ter um leitor: enquanto `process.custo_do_estado_atual` e
`ProcessDetailPage` liam o modelo fundido, ele não podia sair. A fatia repontou o custo para o
`Finding(epistemic_status=fact)` vivo do processo e migrou a tela para o split; sem leitor, a classe
foi apagada. **Não houve perda de dado**: o backfill da `0054` já traduzira cada `Evidencia` para o
par `Evidence`/`Finding`, e `legacy_evidencia` era só o ponteiro de reconciliação — removido junto,
com o comando `reconciliar_evidence_finding` que o lia. O gate operacional é rodar esse comando na
base alvo **antes** do deploy (`"Split reconciliado: todo legado tem par"`) e conferir backup
restaurável, na ordem que a issue #70 fixa. Consequência da ancoragem na conta: arquivar o processo
deixou de arquivar os achados — `Evidence`/`Finding` têm `process` `SET_NULL`, não são filhos do
processo, e uma afirmação sobre a operação do cliente sobrevive ao arquivamento do mapa que a citava.

### Fase 6 (issue #70) — as tabelas foram renomeadas

A segunda fatia (migração `0069`) pagou as quatro tabelas que a #67 fixou em `Meta.db_table`:
`core_client`→`core_account`, `core_opportunity`→`core_commercialopportunity`,
`core_processo`→`core_process`, `core_processoetapa`→`core_processstep`. Cada uma saiu por um
`AlterModelTable(table=None)`, que emite um `ALTER TABLE ... RENAME TO` e **preserva linha e pk** —
a garantia normativa da §2b, porque o One deriva chave de identidade de seis dessas pks e a persiste,
e o renome da tabela não toca o `id`. Fazer com modelo novo + migração de dados criaria pk nova e
desgrudaria os registros externos em silêncio; por isso a §2b proíbe esse caminho e por isso os pins
saíram do `Meta` sem nenhuma outra operação junto. A reversa reaplica o `db_table` legado. Com as
tabelas concluídas, a `/api/v2/` — onde morrem as **rotas** e as **chaves de payload** — pode
finalmente nascer.

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

A projeção `Project.client` foi removida na Fase 6 (migração `0070`). A invariante de igualdade
entre `project.engagement.account_id` e o antigo `project.client_id` já não precisa ser guardada —
a fonte canônica é a única que resta.

**Identidade tem de ser a pk estável da linha**, nunca valor recalculável — slug, hash do nome,
número de sequência por conta. Identificador que alguém pode recalcular é identificador que alguém
vai recalcular diferente.

Regra prática: **em toda travessia de nome, a linha e a pk sobrevivem; só o rótulo muda.** O
renome de tabela da `0069` seguiu isso à risca — `AlterModelTable` não toca a pk. Uma migração
que crie linha nova para o mesmo fato precisa dizer, no próprio arquivo, como o consumidor externo
continua achando o registro antigo.

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

**A depreciação, desde a issue #67, é visível no próprio contrato — não só nesta página.** Até
aqui, quem lia `openapi.yaml` ou o Swagger de `/api/docs/` não tinha como distinguir `client` de
`account`: as duas chaves apareciam como campo comum, sem nenhum sinal de que uma delas morre na
`/api/v2/`. `backend/apps/core/openapi_aliases.py` declara `ALIASES_DEPRECIADOS`, o espelho manual
desta seção para o vocabulário do OpenAPI (componente do schema → propriedades-alias), e um
`POSTPROCESSING_HOOKS` em `SPECTACULAR_SETTINGS` (`backend/config/settings.py`) marca
`deprecated: true` em cada uma na geração do esquema. É manual e não inferido de `source=` por
regex, de propósito: a maioria dos `source=` do repositório é projeção legítima, não alias — marcar
os dois igual mentiria sobre o que vai morrer. Um teste (`backend/tests/test_openapi_aliases.py`) garante que
o mapa não fica atrás do código nem apodrece com entrada morta.

### 2d. A exceção da regra 2: `kpi_baseline` e `kpi_current` pararam de **aceitar** escrita

A regra 2 diz que a `/api/v1/` não quebra. Esta é a única exceção viva, e ela é **deliberada,
aprovada num gate humano e datada**: a decisão **C1** do DAP `docs/design/dap-prove-e-valor-r1/`
(28/08/2026), implementada pela ADR 0055 e pela FDD 049.

O que aconteceu: `DigitalEmployee.kpi_baseline` e `kpi_current` eram colunas do ativo de solução e
viraram `Measurement` de um `KPI`. Se as duas chaves continuassem **graváveis**, passariam a existir
dois lugares escrevendo a mesma medição, e a que valeria seria a última salva — a fonte da verdade
voltaria a ser o ativo de solução, que é precisamente o que a extração desfaz.

| Verbo | Antes | Agora | Por quê |
| --- | --- | --- | --- |
| `PATCH /digital-employees/{id}/` com `kpi_baseline`/`kpi_current` | gravava as colunas | aceito com 200 e **ignorado** | campos derivados, só de leitura — a forma dos três snapshots congelados do `Case` (ADR 0020) |
| `POST /projects/{id}/digital-employees/from-blueprint/` com `kpi_baseline` | gravava a coluna | chave fora do corpo aceito e do esquema | `blueprints.instantiate` perdeu o parâmetro |

**A leitura não quebrou, e não vai quebrar antes da hora.** As duas chaves continuam saindo no
`GET`, derivadas da baseline viva e do `Outcome` mais recente do KPI referenciado — `null` quando
não há, nunca zero. Elas morrem na `/api/v2/`, como toda chave de payload (§2c e ADR 0052), e é por
isso que entram na tabela de aliases vivos acima.

Como todo alias, a leitura precisa de regressão, e pelo motivo da §2c: um campo derivado sem
chamador **dentro** do repositório — a SPA lê, o backend não — é o que a próxima varredura atrás de
campo morto remove achando que paga dívida. Ela está em
`backend/tests/regression/test_a_medicao_do_ativo_sobrevive_na_v1.py`.

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
