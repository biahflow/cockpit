# ADR 0038 — OpenTelemetry como padrão canônico e Grafana Cloud como backend inicial

**Status:** Accepted  
**Data:** 2026-08-24

## Contexto

A observabilidade atual cobre request-id, logs estruturados, health/readiness e rastreamento de erro. O BiahflowOS passará a operar serviços, filas, workers, integrações e agentes distribuídos; correlação por requisição isolada não é suficiente.

A base deve permanecer vendor-neutral.

## Decisão

**OpenTelemetry** será o padrão canônico de instrumentação e propagação de contexto da Biahflow.

Componentes:

- OpenTelemetry SDKs nas aplicações e workers;
- **OpenTelemetry Collector** como camada de coleta, processamento, sampling e exportação;
- W3C Trace Context (`traceparent`, `tracestate`, `baggage`) para propagação distribuída;
- Grafana Cloud como backend inicial de metrics, logs e traces;
- Prometheus/Loki/Tempo são tecnologias de backend compatíveis, não dependências de domínio da aplicação.

`X-Request-ID` pode continuar como identificador amigável, mas não substitui o trace distribuído.

## Sampling e custo

Não há requisito de ingestão de 100% da telemetria.

Diretriz inicial de traces:

- erros: 100%;
- fluxos críticos de negócio: 100%;
- integrações externas com falha: 100%;
- traces lentos: 100%;
- tráfego normal: amostragem reduzida configurável;
- preferir tail sampling no Collector quando a decisão depender do resultado do trace.

Métricas devem controlar cardinalidade. `customer_id`, `project_id`, `event_id`, conteúdo e IDs de usuário não entram como labels de alta cardinalidade; esses dados pertencem a logs/traces/auditoria quando necessários.

## Separação entre telemetria e auditoria

Telemetria responde "como o sistema se comportou". Auditoria responde "qual decisão/ação de negócio aconteceu".

Eventos de negócio e evidências críticas permanecem persistidos em storage durável da Biahflow e não dependem da retenção do backend de observabilidade.

## Correlação

Quando aplicável, registrar e propagar:

- `trace_id`;
- `correlation_id`;
- `event_id`;
- `agent_run_id`;
- identificadores de domínio não sensíveis necessários à investigação.
