# Eval Spec Template

## Escopo

- **Sistema/agente:**
- **Owner:**
- **Versão:**
- **Dataset:**
- **Ambiente:** offline | staging | production shadow

## Objetivo

Defina o comportamento que precisa ser demonstravelmente bom antes de promover uma mudança de prompt, modelo, ferramenta ou fluxo.

## Casos de avaliação

Cada caso deve conter:

- entrada;
- contexto permitido;
- resultado esperado ou critérios de julgamento;
- evidências necessárias;
- severidade da falha.

## Dimensões

Selecione as aplicáveis:

- groundedness;
- factualidade;
- completude;
- relevância;
- segurança;
- aderência a política;
- uso correto de tools;
- decisão de escalar para humano;
- latência;
- custo;
- estabilidade entre execuções.

## Avaliadores

Declare explicitamente qual mecanismo julga cada dimensão:

- regra determinística;
- teste de contrato;
- comparação exata;
- LLM-as-judge;
- revisão humana.

Nenhum judge baseado em LLM deve ser tratado como evidência absoluta para requisito crítico sem calibração ou amostragem humana.

## Thresholds

Exemplo:

```text
groundedness >= 0.95
required_fields = 1.00
unsupported_claims = 0 em casos críticos
tool_policy_violations = 0
p95_latency <= limite definido
cost_per_run <= budget definido
```

## Regression Gate

Uma mudança não pode ser promovida quando:

- piora uma métrica crítica além da tolerância;
- introduz violação de segurança/política;
- perde evidência obrigatória;
- aumenta custo/latência além do budget sem decisão registrada.

## LangSmith

LangSmith é o backend inicial de experiments, traces, datasets e evals. O Git versiona este contrato de qualidade; LangSmith registra os resultados das execuções.

## Evidência de promoção

Registrar:

- commit/PR;
- prompt version;
- modelo;
- dataset version;
- experiment/run;
- resultado agregado;
- falhas conhecidas;
- aprovação humana quando necessária.
