# NFR-001 — Observability

**Status:** Active  
**Data:** 2026-08-24

## Objetivo

Toda capacidade crítica do Pulse/BiahflowOS deve ser observável sem depender de um fornecedor específico.

## Requisitos

- OpenTelemetry é obrigatório para novos serviços distribuídos, workers e consumers.
- Contexto W3C deve atravessar HTTP, filas e jobs assíncronos quando tecnicamente aplicável.
- Erros e fluxos críticos devem ser retidos com prioridade sobre tráfego normal.
- Sampling é permitido e esperado; ingestão de 100% não é requisito.
- Métricas não devem usar labels de alta cardinalidade como `event_id`, `customer_id`, `project_id` ou conteúdo livre.
- Logs estruturados devem evitar PII e segredos por padrão.
- Toda integração externa deve expor latência, sucesso/falha e motivo de erro de forma investigável.
- Consumers devem expor throughput, latency, retries e DLQ/quarantine.
- Dashboards técnicos vivem no backend de observabilidade; Pulse mostra apenas resumo operacional necessário ao negócio.
- Audit trail de negócio não pode depender da retenção de logs/traces.

## SLOs iniciais

SLOs quantitativos serão definidos por feature quando houver baseline real. Antes disso, instrumentação e capacidade de medir são gate obrigatório.
