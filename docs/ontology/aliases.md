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

| Alias vivo hoje | Nome canônico | Onde vive | Morre em |
| --- | --- | --- | --- |
| modelo `Client` | `Account` | `backend/apps/core/models.py` | renome físico na Fase 6 |
| rota `/api/v1/clients/` | `/accounts/` | `backend/apps/core/urls.py` | `/api/v2/` |
| modelo `Opportunity` | `CommercialOpportunity` | `backend/apps/core/models.py` | renome físico na Fase 6 |
| rota `/api/v1/opportunities/` | `/commercial-opportunities/` | `backend/apps/core/urls.py` | `/api/v2/` |
| `Processo` / `ProcessoEtapa` / `Evidencia` | `Process` / `ProcessStep` / `Evidence` | `backend/apps/core/models.py` | Fase 3 (split Evidence/Finding) + Fase 6 (renome) |
| `GateOutcome` | `GateDecision` | `backend/apps/core/models.py` | Fase 6 |

`Evidencia` é o único que não é só renome: a Fase 3 a **divide** em `Evidence` (o registro bruto) e
`Finding` (a conclusão, com `epistemic_status`), conforme a decisão D6. Trocar o nome sem dividir
resolveria o idioma e preservaria o defeito de linguagem que a divisão existe para corrigir.

## As três regras

### 1. Alias é dívida com data

Enquanto o alias vive, **campo novo e código novo usam o nome canônico apontando para o modelo
legado**. É o que a Fase 1 faz: `Qualification.account` é uma `ForeignKey` para o modelo que ainda
se chama `Client`. O nome do campo é o compromisso público; o nome da tabela é detalhe que a Fase 6
acerta.

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
