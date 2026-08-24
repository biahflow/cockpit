# ADR 0039 — LangGraph como runtime agentic e LangSmith para observabilidade/evals de IA

**Status:** Accepted  
**Data:** 2026-08-24

## Contexto

O BiahflowOS terá agentes especializados e fluxos stateful com ferramentas, human gates e decisões condicionais. A operação precisa de runtime explícito e de observabilidade/evaluation especializada para LLMs.

## Decisão

- **LangGraph** será o runtime padrão para workflows agentic/stateful.
- **LangSmith** será a plataforma inicial para tracing especializado, debugging, datasets e evals de LLM/agents.
- OpenTelemetry continua sendo a telemetria canônica de plataforma; LangSmith não substitui OTel.
- Auditoria de negócio permanece em storage da Biahflow e não depende de LangSmith.

## Regras de uso

1. Ações determinísticas simples não devem ser implementadas como agente; usar código/n8n.
2. Agentes que possam causar efeito externo de alto impacto exigem política de human gate explícita.
3. Cada run relevante deve ser correlacionável com `correlation_id`, `event_id` e, quando disponível, `trace_id`.
4. Prompts, ferramentas e políticas críticas devem ser versionados em Git.
5. A expectativa de qualidade vive em Eval Specs versionadas; LangSmith executa e mede os experimentos.
6. Nenhum trace deve enviar segredo, credencial ou conteúdo sensível sem política explícita de redaction.
7. Custos, tokens, modelo, latência e falhas devem ser observáveis por agente/feature.

## Agent Specs

Cada agente de produção deve possuir uma especificação com, no mínimo:

- purpose;
- inputs/outputs;
- tools e permissões;
- ações proibidas;
- memória/contexto;
- human gates;
- failure modes;
- métricas/evals;
- budget/cost controls.

## Consequências

A integração estreita entre LangGraph e LangSmith é aceita como vantagem operacional. O lock-in é limitado mantendo telemetria técnica, eventos de negócio, contratos e especificações fora do LangSmith.
