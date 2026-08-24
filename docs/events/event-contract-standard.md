# BiahflowOS — Event Contract Standard

## Objetivo

Definir o envelope canônico dos eventos de domínio e integração do BiahflowOS. Este contrato existe para desacoplar Pulse, ClickUp, GitHub, One, automações e agentes, preservando auditabilidade, idempotência e evolução de schema.

## Envelope canônico

Todo evento publicado no backbone deve conter, no mínimo:

```json
{
  "event_id": "evt_...",
  "event_type": "domain.action",
  "schema_version": 1,
  "occurred_at": "2026-08-24T12:00:00Z",
  "producer": "pulse",
  "aggregate_type": "opportunity",
  "aggregate_id": "...",
  "correlation_id": "corr_...",
  "causation_id": "evt_...",
  "trace_id": "...",
  "tenant_id": "...",
  "payload": {}
}
```

## Regras

- `event_id` é globalmente único e usado para deduplicação.
- `event_type` segue `dominio.acontecimento`, em minúsculas, estável e sem dados variáveis no nome.
- `schema_version` inicia em 1 e só muda quando o contrato do payload muda de forma incompatível.
- `correlation_id` liga toda a cadeia de uma mesma operação de negócio.
- `causation_id` aponta para o evento que causou o evento atual; no evento raiz pode ser nulo.
- `trace_id` deve carregar o identificador distribuído OpenTelemetry quando disponível.
- `tenant_id` nunca deve ser inferido apenas do payload quando a operação for multitenant.
- `payload` contém somente dados necessários ao consumidor; dados sensíveis, comerciais ou pessoais devem ser minimizados.
- consumidores devem ser idempotentes por `event_id`.
- publicação transacional deve usar Outbox quando o evento nasce de uma mudança persistida.

## Eventos iniciais do M1

- `opportunity.won`
- `project.created`
- `delivery.task.created`
- `delivery.task.ready_for_engineering`
- `engineering.issue.created`
- `engineering.pull_request.opened`
- `engineering.pull_request.merged`
- `delivery.ready_for_acceptance`
- `delivery.client_review.requested`
- `delivery.accepted`
- `delivery.completed`
- `contract.generated`
- `contract.signature.requested`
- `contract.signed`
- `payment.requested`
- `payment.received`
- `notification.requested`
- `agent.run.started`
- `agent.run.completed`
- `agent.run.failed`
- `human_gate.created`
- `human_gate.approved`
- `human_gate.rejected`

## Compatibilidade

Campos novos podem ser adicionados de forma retrocompatível. Remoção, mudança de significado ou alteração de tipo requer nova `schema_version`.

## Observabilidade e auditoria

O evento operacional pode aparecer em traces e logs, mas o backbone de eventos e a trilha de auditoria de negócio não dependem da retenção do backend de observabilidade.
