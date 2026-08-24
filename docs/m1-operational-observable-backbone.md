# BiahflowOS M1 — Operational + Observable Backbone

## Objetivo

Entregar o primeiro backbone operacional do BiahflowOS, com ownership explícito, eventos confiáveis, observabilidade distribuída, runtime agentic e aceite de cliente separado de conclusão técnica.

## Princípios

- Pulse é o sistema de verdade de negócio/CRM.
- ClickUp é o sistema de verdade de Delivery.
- GitHub é o sistema de verdade de Engenharia.
- One é a projeção oficial client-facing.
- PR mergeado nunca implica `Done` automaticamente.
- `Done` exige aceite/homologação quando a entrega tiver validação de negócio/cliente.
- mudanças de estado relevantes produzem eventos.
- automações determinísticas usam n8n/code; decisões contextuais usam LangGraph.
- OpenTelemetry é o padrão canônico de telemetria; OTel Collector é vendor-neutral; Grafana Cloud é o backend inicial.
- LangSmith é a camada especializada de observabilidade/evals de LangGraph.
- auditoria de negócio é durável e independente da retenção de telemetria.

## Workstreams

### M1.1 — Architecture Decisions

Entregáveis:
- Sources of Truth e fronteiras;
- Delivery lifecycle e acceptance;
- Event backbone;
- Observability;
- Agent runtime/LLM observability;
- NFRs transversais.

Gate: decisões aceitas e sem conflito com ADRs anteriores não supersedidos.

### M1.2 — Event Contracts + Outbox

Implementar:
- envelope canônico;
- `event_id`, `correlation_id`, `causation_id`, `trace_id`;
- Outbox transacional;
- publisher para RabbitMQ;
- consumer idempotency;
- retry e DLQ.

Primeiros eventos: `opportunity.won`, `project.created`, `delivery.task.ready_for_engineering`, `engineering.pull_request.merged`, `delivery.client_review.requested`, `delivery.accepted`.

### M1.3 — OpenTelemetry Foundation

Implementar:
- OTel SDK nas aplicações/serviços relevantes;
- W3C Trace Context;
- OTel Collector;
- export OTLP para Grafana Cloud;
- métricas de RED/USE aplicáveis;
- logs estruturados correlacionados;
- tail/parent sampling conforme risco e custo;
- 100% de erros e fluxos críticos quando tecnicamente viável.

Preservar `X-Request-ID` quando útil à operação, sem confundi-lo com trace distribuído.

### M1.4 — ClickUp como Delivery SoR

Migrar responsabilidade de tarefas de Delivery do Pulse para ClickUp.

Pulse deve:
- criar/ligar projeto de Delivery;
- exibir projeção/resumo;
- reagir a eventos;
- não manter edição concorrente bidirecional como fonte primária.

### M1.5 — GitHub Engineering Flow

Fluxo:
`ClickUp Task -> GitHub Issue -> Planner/Builder Router -> Builder -> PR -> CI -> Reviewer -> Merge`.

Merge produz `delivery.ready_for_acceptance`, não `Done`.

### M1.6 — Acceptance / Client Review

Estados mínimos:
- Ready for Acceptance;
- Internal Review, quando aplicável;
- Client Review/Homologação;
- Accepted;
- Done.

Registrar evidência, ator, timestamp e decisão.

### M1.7 — One Projection

One recebe somente projeção client-facing:
- fase;
- progresso;
- milestones;
- entregas;
- pendências;
- aprovações;
- resultados/ROI;
- próximos passos.

Não expor detalhes internos de ClickUp, GitHub, agentes ou custos comerciais sem decisão explícita.

### M1.8 — LangGraph + LangSmith

Implementar o primeiro agente com:
- Agent Spec;
- tools com permissões explícitas;
- Human Gate quando necessário;
- LangSmith tracing;
- Eval Spec;
- correlação com OpenTelemetry e eventos.

### M1.9 — Business Automation

Converter integrações existentes para reagirem a eventos, iniciando por:
- contrato/assinatura;
- e-mail;
- Drive;
- calendário;
- WhatsApp quando adicionado;
- pagamento.

Evitar sincronizações bidirecionais desnecessárias e chamadas ferramenta-a-ferramenta em cascata.

### M1.10 — End-to-End Proof

Cenário de prova:

```text
Pulse: Opportunity WON
  -> evento opportunity.won
  -> projeto/tarefas no ClickUp
  -> task ready_for_engineering
  -> GitHub Issue
  -> Builder / PR / CI / Review
  -> Merge
  -> Ready for Acceptance
  -> One mostra Client Review
  -> cliente aprova
  -> Accepted
  -> Done
```

## Definition of Done do M1

O cenário E2E deve demonstrar:

- nenhuma duplicação por retry;
- eventos idempotentes;
- trilha de auditoria durável;
- trace distribuído correlacionável;
- métricas e logs operacionais;
- DLQ/reprocessamento para falhas assíncronas;
- LangSmith trace/eval quando houver agente;
- Human Gate/Client Acceptance registrado;
- One atualizado por projeção, sem virar SoR de Delivery;
- `Done` somente após regra de aceite aplicável.

## Ordem de implementação

A sequência M1.1 -> M1.10 é deliberada. Não iniciar automações de negócio em larga escala antes de Event Contract, idempotência e observabilidade estarem funcionais.
