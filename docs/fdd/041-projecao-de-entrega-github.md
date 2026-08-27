# FDD 041 — Projeção de entrega GitHub (Issue/PR/CI) no Pulse

> GitHub Issue [#41](https://github.com/biahflow/pulse/issues/41).
> Superfície: `INTEGRATION_CHANGE`. Browser: `BROWSER_REQUIRED` para a prova visual dos estados
> projetados; o aceite desta fatia é a API + a projeção observável no projeto. Merge do PR ≠ Done.

## Jornada

Uma Issue de engenharia (o Task Contract provisionado na FDD 040) ganha vida no GitHub: abre, recebe
um PR, o PR muda de SHA, o CI roda, a revisão aprova. O Pulse — a superfície de comando operacional
— precisa **ver** esse estado sem sair para o GitHub e sem virar um segundo sistema de registro de
engenharia. Esta fatia projeta o estado observado para dentro do projeto Pulse: estado da Issue, do
PR, SHA/ref do head, prontidão de revisão quando derivável e estado do CI quando disponível.

A projeção é **leitura**. O que a engenharia decide continua no GitHub; o Pulse espelha para operar
e nunca reescreve o estado técnico. Uma edição normal do Pulse não muda a Issue nem o PR.

## Distinção da FDD 040 (e da FDD 004)

A FDD 040 (flag `github_provisioning`) é a direção de **escrita**: o Pulse cria a GitHub Issue a
partir de um `EngineeringHandoff`. Esta FDD é a direção de **leitura**, complementar: observa
Issue/PR/CI e projeta. Reusa a referência que a 040 já persiste (`repository`,
`github_issue_number`) — a projeção pode apontar para o handoff que a originou (`handoff`), sem
duplicar a referência. As duas flags, os dois recursos e os dois conjuntos de rotas não se misturam.

A FDD 004 (flag `tasksync`) é outra coisa ainda: espelha o **status de uma `Task`** do portal contra
uma issue, nos dois sentidos. Aqui não há `Task` espelhada — há um item de entrega que referencia uma
Issue e projeta o estado de engenharia dela. Três flags, três recursos, três contratos.

## Contrato de dados / mapeamento

O modelo `GithubDeliveryProjection` é a referência canônica entre um item de entrega do Pulse e uma
Issue/PR do GitHub:

- **Âncora:** `project` + `repository` (`owner/repo`) + `issue_number`, único por
  `(repository, issue_number)` — a chave por onde o webhook resolve a projeção. `handoff` (opcional)
  guarda a proveniência de escrita quando a referência veio da FDD 040.
- **Estado de engenharia projetado (somente-projeção):** `issue_state` (open/closed), `pr_state`
  (none/draft/open/closed/merged), `pr_number`, `pr_url`, `head_sha`, `head_ref`, `review_state`
  (pending/approved/changes_requested), `ci_state` (pending/success/failure). Todos começam
  `unknown` e só se movem por evento ou reconciliação.
- **Proveniência e frescor:** `issue_url`/`pr_url` (URLs canônicas), `observed_at` (última
  confirmação boa), `last_event_at` (marca d'água contra out-of-order), `last_delivery_id` e
  `last_event_type` (identidade do evento de entrega), `last_error_code`/`last_error_message`.

`projection_status` é o desfecho persistido da última observação: `pending` (criada, nunca
observada), `current` (confirmada), `unavailable` (GitHub não respondeu), `permission_denied` (403),
`reference_missing` (404). O **estado visível** (`state`, derivado em `display_state`) dobra o
frescor: uma projeção `current` cuja `observed_at` passou de `GITHUB_PROJECTION_STALE_AFTER_SECONDS`
aparece como `stale`. Assim os cinco estados exigidos — `current`/`stale`/`unavailable`/
`permission_denied`/`reference_missing` — são sempre distintos, e **status nunca é inventado**.

## Regras

- Atrás da flag `github_delivery` (`GITHUB_DELIVERY_ENABLED`, `GITHUB_TOKEN`,
  `GITHUB_WEBHOOK_SECRET`), desligada por padrão. Sem ela, `POST` de mapeamento, `reconcile` e o
  webhook respondem **503** e não criam linha (fail closed, ADR 0018, mesmo molde da FDD 040).
  `GITHUB_REPO` **não** é exigido: o repositório é por-projeção.
- **Webhook-first.** `POST /github/webhook/` autentica pelo HMAC-SHA256 do corpo cru
  (`X-Hub-Signature-256`); assinatura ausente/errada → 401. Evento de tipo desconhecido ou sem
  projeção correspondente → 200 "ignorado" (um erro faria o GitHub reentregar para sempre, e o Pulse
  não inventa referência que não mapeou).
- **Idempotência.** A reentrega literal do GitHub carrega o mesmo `X-GitHub-Delivery`; um inbox
  (`GithubWebhookDelivery`, `delivery_id` único) absorve o duplicado e o handler vira no-op. Inbox e
  aplicação commitam na mesma transação: se o apply falhar, o inbox reverte junto e a reentrega
  reprocessa.
- **Out-of-order.** Um evento mais antigo que a marca d'água `last_event_at` é replay atrasado e não
  regride o estado; a reconciliação recupera o que faltou. Reaplicar o mesmo estado é naturalmente
  idempotente. Um `head_sha` novo zera o `ci_state` (verde de commit velho não vale para o novo).
- **Reconciliação por poll** (`POST /github-projections/{id}/reconcile/`, e via código para um job):
  confirma a Issue sempre; PR e CI são best-effort quando já há `pr_number`. Falha do GitHub vira
  estado degradado explícito (404→`reference_missing`, 401/403→`permission_denied`, resto
  →`unavailable`), preservando `observed_at` e os valores já projetados para leitura.
- **Vínculo PR→Issue determinístico**, sem LLM: o corpo do PR com `Closes/Fixes/Resolves #N` liga o
  PR à projeção da Issue; depois disso, eventos de PR/CI casam por `pr_number` e `head_sha`.
- **Zero LLM** (NFR / EngineeringOS FinOps): verificação de assinatura, parsing, comparação de
  SHA/status, idempotência, reconciliação e serialização são determinísticos.
- **O Pulse não vira autoritativo** (ADR 0046): os campos de engenharia são somente-leitura no
  serializer; um PATCH normal do Pulse não os reescreve. Escopo de projeto (`ProjectScopedMixin`) e
  papel (`resource = "github_projection"`, nega-por-padrão) valem como nas irmãs — Entrega no próprio
  projeto, Vendas 403, recurso novo nasce fechado.

## Aceite

Com a flag ligada, mapear projeto+repo+Issue devolve 201 `pending`. Um webhook de `issues` assinado
move a projeção para `current` com `issue_state` observado; a reentrega do mesmo `delivery_id`
devolve `duplicate` e não reaplica. Um evento fora de ordem não regride o estado. `reconcile` sobre
um GitHub indisponível marca `unavailable` sem apagar a última observação boa. Com a flag desligada,
503 e nenhuma linha. Assinatura inválida no webhook → 401.

## Regressão crítica

Reprocessar o mesmo `delivery_id` não reaplica o evento; um evento antigo não sobrescreve um estado
novo; um PATCH do Pulse não muda `issue_state`/`ci_state`/`projection_status`; a referência
`(repository, issue_number)` não muda depois de criada; o provisionamento (FDD 040) e o `tasksync`
(FDD 004) seguem intactos.

## Contrato

Rotas aditivas em `/api/v1/`:

| Rota | Quem |
| --- | --- |
| `/github-projections/` (CRUD-de-mapeamento + `?project=` + `?projection_status=` + `?archived=1` + `unarchive`) | delivery no próprio projeto / admin |
| `POST /github-projections/{id}/reconcile/` | delivery no próprio projeto / admin |
| `POST /github/webhook/` | GitHub (HMAC, sem sessão) |

Nada foi removido ou alterado no contrato existente. Provisionamento e `tasksync` não foram
estendidos.

## Fora deste recorte

- Merge automático de PR, release automática, aceite do cliente (One) — a promoção de merge a Done é
  explicitamente vedada (ADR 0040).
- Kanban de engenharia (GitHub Projects), Outbox/RabbitMQ e o event store (ADR 0037 fica como
  contexto de idempotência, não é implementado aqui).
- Watermark por-stream (issue/PR/CI têm hoje uma marca d'água única; a reconciliação cobre a folga).
- Registro de check-runs individuais: o CI é agregado a um veredito (`success`/`failure`/`pending`).
- SPA além da superfície mínima de leitura no detalhe do projeto.
