# NFR-002 — Agent Governance

**Status:** Active  
**Data:** 2026-08-24

## Objetivo

Agentes devem acelerar a operação sem remover accountability humana, auditabilidade ou limites de custo e permissão.

## Requisitos

- Output de LLM é sugestão/artefato até atravessar o gate definido para a feature.
- Ação externa high-impact exige human gate explícito, salvo exceção aprovada em ADR.
- Cada agente de produção precisa de Agent Spec versionada em Git.
- Cada feature agentic crítica precisa de Eval Spec com dataset, métricas e threshold de aceite.
- Tool permissions seguem least privilege.
- Prompt, model policy e tool schema relevantes precisam ser versionados.
- Runs relevantes devem registrar modelo, tokens/custo, latência, ferramentas chamadas, resultado e erro, respeitando redaction.
- LangSmith é a ferramenta inicial de tracing/evals; não é fonte da verdade de negócio.
- Falha do provedor de IA deve degradar de forma explícita, nunca converter ausência de resposta em fato.
- Conteúdo gerado não pode cruzar fronteiras de tenant/contexto.
- Budget e limites de uso devem existir por feature antes de escala relevante.

## Gate de produção

Nenhum agente novo é considerado pronto somente porque executa o happy path. Produção exige Agent Spec, failure modes, evals mínimos, observabilidade e política de human oversight.
