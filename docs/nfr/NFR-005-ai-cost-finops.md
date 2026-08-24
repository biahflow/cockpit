# NFR-005 — AI Cost & FinOps

## Objetivo

Controlar custo de modelos, tracing e automações desde o primeiro ambiente operacional.

## Requisitos

- toda execução de agente deve registrar modelo, tokens de entrada/saída quando disponíveis, latência e estimativa de custo;
- budgets devem poder existir por agente, projeto e período;
- mudanças de modelo/prompt que aumentem custo materialmente precisam de evidência de ganho de qualidade ou decisão registrada;
- tracing de LLM não precisa reter 100% das execuções quando o volume justificar sampling, exceto falhas, casos críticos e execuções selecionadas para eval;
- telemetria de plataforma deve usar sampling e controle de cardinalidade; erros e fluxos críticos têm prioridade de retenção;
- labels de métricas não devem incluir identificadores de alta cardinalidade como `event_id`, `user_id` ou `project_id`;
- custos de fornecedores devem ser reconciliáveis com eventos internos persistidos quando a cobrança for material;
- ausência de preço conhecido nunca deve ser silenciosamente tratada como custo zero.

## Gate

Toda feature agentic nova deve declarar budget inicial e métrica de valor antes de produção.
