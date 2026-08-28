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
