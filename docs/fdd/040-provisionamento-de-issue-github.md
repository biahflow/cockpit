# FDD 040 — Provisionamento de Issue GitHub a partir de um handoff Pulse

> GitHub Issue [#18](https://github.com/biahflow/pulse/issues/18), workstream **M1.4**.
> Superfície: `NO_INTERFACE_CHANGE`. Browser: `BROWSER_CONDITIONAL` — a flag
> `github_provisioning` aparece em Configurações via `flags.all_status()`, sem alteração de SPA.
> O aceite desta fatia é a API; evidência de browser não é exigida enquanto a tela não consumir o
> recurso. Merge do PR ≠ Done operacional.

## Jornada

Quando o planejamento de negócio decide que um item exige engenharia, o Pulse persiste um handoff
estruturado e o backend provisiona uma GitHub Issue — o Task Contract que o harness do
EngineeringOS consome. A transformação é determinística: os campos do handoff viram markdown em
inglês, com um bloco-máquina de correlação. Nenhum modelo de linguagem entra neste fluxo.

A Issue provisionada **não** significa que a execução começou. Merge de PR **não** é Done. Este
fluxo não consome webhooks e não espelha status de `Task`.

## Distinção da FDD 004

A sincronia de tarefas (FDD 004, flag `tasksync`) vincula uma `Task` do portal a uma issue
existente (`link-external`) ou cria uma issue-espelho (`push-external`) e troca status nos dois
sentidos. Aqui a GitHub Issue **é** o contrato de engenharia; o handoff vive em
`EngineeringHandoff`, com chave de idempotência `pulse_work_item_id`. As duas flags, os dois
recursos e os dois conjuntos de rotas não se misturam.

## Regras

- A integração fica atrás da flag `github_provisioning` (`GITHUB_PROVISIONING_ENABLED`,
  `GITHUB_TOKEN`, `GITHUB_REPO`), desligada por padrão. Sem ela, `POST` e `retry` respondem 503 e
  **não** criam linha (fail closed, ADR 0018).
- `pulse_work_item_id`, `title`, `objective` e `acceptance_criteria` são obrigatórios. Validação
  no serializer devolve 400, não 500.
- `pulse_work_item_id` é único. Um segundo POST com o mesmo id **não duplica**: provisiona o
  registro existente e devolve 200. `create_issue` é chamado no máximo uma vez.
- Já `provisioned` com número: o orquestrador retorna sem HTTP.
- Janela 201-sem-persistir: `find_by_handoff_id` busca no corpo da Issue o
  `Pulse-Handoff-ID`; se achar, persiste número/URL/`node_id` e marca `provisioned` sem criar
  outra Issue.
- Falha remota (4xx/5xx/timeout): status `failed`, `github_issue_number` permanece vazio, a linha
  existe para retry. O primeiro POST devolve **201** com `status=failed` — o operador precisa do
  id. `POST .../retry/` reexecuta; se já provisioned, 200 no-op.
- Sem token ou repositório efetivo, o adaptador **não** chama HTTP. `str(GitHubIssuesError)` e os
  logs nunca carregam o token (NFR-004). A sonda `check_integrations` faz GET no repositório
  (FDD 024): valida credencial sem criar Issue.
- Zero LLM (NFR-005, EngineeringOS FinOps): este trabalho é determinístico.
- Merge ≠ Done. Webhooks GitHub, sync de PR, One, LangGraph, RabbitMQ e Outbox ficam fora desta
  fatia (ADR 0040 / ADR 0037 como contexto de idempotência, sem implementá-los aqui).
- Entrega escreve no próprio projeto; Vendas leva 403; recurso novo nasce fechado (`PROJECT_OF`).

## Aceite

Com a flag ligada, um POST de handoff válido cria a GitHub Issue, persiste número/URL/correlação e
devolve 201 `provisioned`. O mesmo `pulse_work_item_id` de novo devolve 200 na mesma Issue. Com a
flag desligada, 503 e nenhuma linha. Token canário não aparece em resposta nem em log.

## Regressão crítica

Reprocessar o mesmo `pulse_work_item_id` não cria segunda GitHub Issue; GitHub 500 persiste
`failed` com number vazio e o retry posterior provisiona; a sincronia FDD 004 (`tasksync`)
continua intacta.

## Contrato

Rotas aditivas em `/api/v1/`:

| Rota | Quem |
| --- | --- |
| `/engineering-handoffs/` (CRUD + `?project=` + `?status=` + `?archived=1` + `unarchive`) | delivery no próprio projeto / admin |
| `POST /engineering-handoffs/{id}/retry/` | delivery no próprio projeto / admin |

Nada foi removido ou alterado no contrato existente. `link-external` / `push-external` /
`tasks/sync` não foram estendidos.

## Fora deste recorte

- Webhooks GitHub, sincronia de PR, One, LangGraph, RabbitMQ, Outbox.
- Frontend SPA (a flag aparece sozinha em Configurações via `flags.all_status()`).
- `roadmap.md` e qualquer promoção de merge a Done.
- `apps.core.ai` / `agents`.
- Comportamento de `tasksync.py`.
