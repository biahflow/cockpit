# ADR 0037 — Backbone event-driven, Outbox e idempotência

**Status:** Accepted  
**Data:** 2026-08-24

## Contexto

Pulse já integra múltiplos provedores, mas o novo BiahflowOS precisa evitar integrações ponto a ponto e efeitos colaterais acoplados a uma única transação HTTP.

## Decisão

O BiahflowOS adotará arquitetura orientada a eventos para mudanças relevantes de domínio.

Eventos serão publicados de forma durável usando **Transactional Outbox** no PostgreSQL e entregues ao barramento assíncrono. RabbitMQ é o broker inicial.

Formato canônico mínimo:

```json
{
  "event_id": "uuid",
  "event_type": "proposal.approved",
  "aggregate_type": "opportunity",
  "aggregate_id": "...",
  "occurred_at": "2026-08-24T12:00:00Z",
  "correlation_id": "...",
  "causation_id": "...",
  "schema_version": 1,
  "payload": {}
}
```

Consumidores devem ser idempotentes. `event_id` é a chave padrão de deduplicação; quando o efeito externo possuir sua própria idempotency key, ela deve derivar do evento ou ser persistida junto ao resultado.

## Regras

1. Persistir estado de domínio e Outbox na mesma transação.
2. Não publicar diretamente no broker antes do commit da transação de domínio.
3. Consumidores assumem entrega **at least once**.
4. Retry deve ter política explícita; falhas permanentes vão para DLQ/quarentena operacional.
5. Efeitos externos devem registrar provider id, tentativa, resultado e `correlation_id`.
6. Eventos são contratos versionados; mudança incompatível exige nova versão.
7. Evento de domínio não carrega segredo nem conteúdo sensível desnecessário.

## Automação versus agente

- Workflow determinístico: código/n8n.
- Decisão contextual/stateful: LangGraph.
- Ambos recebem eventos pelo mesmo backbone e obedecem às mesmas regras de auditoria/idempotência.

## Eventos iniciais

- `opportunity.won`
- `contract.generated`
- `contract.signed`
- `payment.received`
- `project.created`
- `task.ready_for_engineering`
- `pull_request.merged`
- `delivery.ready_for_client_review`
- `client.accepted`
- `human_gate.created`
- `human_gate.resolved`
