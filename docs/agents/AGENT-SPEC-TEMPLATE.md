# Agent Spec Template

## Identidade

- **Nome:**
- **Domínio:**
- **Owner humano:**
- **Versão:**
- **Status:** draft | active | deprecated

## Propósito

Descreva o resultado de negócio que o agente deve produzir e o que explicitamente não é responsabilidade dele.

## Entradas

- dados obrigatórios;
- contexto opcional;
- fontes autorizadas;
- eventos que podem iniciar a execução.

## Saídas

- artefatos produzidos;
- eventos emitidos;
- estados que podem ser propostos;
- evidências obrigatórias.

## Tools e permissões

Para cada tool, registrar:

- nome;
- operação permitida;
- leitura ou escrita;
- escopo de dados;
- efeitos colaterais possíveis;
- necessidade de Human Gate.

## Ações proibidas

Liste explicitamente ações que o agente nunca pode executar, mesmo quando solicitadas pelo modelo.

## Human Gates

Defina:

- ações que exigem aprovação prévia;
- ações que exigem revisão posterior;
- quem pode aprovar;
- evidência mínima para aprovação.

## Memória e estado

- estado efêmero;
- estado persistente;
- janela de contexto;
- política de retenção;
- dados proibidos em memória.

## Falhas e fallback

- timeout;
- indisponibilidade de modelo/tool;
- ausência de evidência;
- resposta inválida;
- política de retry;
- quando escalar para humano.

## Observabilidade

Obrigatório correlacionar, quando disponíveis:

- `trace_id`;
- `correlation_id`;
- `event_id`;
- `agent_run_id`;
- `project_id`.

LangSmith é a ferramenta especializada inicial para tracing/evals de agentes. OpenTelemetry permanece a telemetria canônica de plataforma.

## Métricas

Defina ao menos:

- taxa de sucesso;
- taxa de escalonamento humano;
- latência;
- tokens/custo;
- qualidade da saída;
- falhas por tool;
- regressões por versão de prompt/modelo.

## Evals

Referencie o Eval Spec correspondente e os thresholds mínimos para promoção a produção.

## Segurança e privacidade

- classificação dos dados;
- minimização;
- regras de redaction;
- isolamento de tenant;
- prompt injection / tool abuse;
- secrets nunca entram no prompt.

## Critérios de aceite

Defina resultados verificáveis, inclusive casos negativos e condições que devem produzir escalonamento em vez de resposta automática.
