# FDD 007 — Discovery e Assessment por IA sobre a transcrição da reunião

## Jornada

Etapas **Discovery** e **Assessment** da jornada de consultoria assistida por IA
(RFC 0002; motor do ADR 0006). No detalhe do projeto, cada reunião com transcrição ganha
dois botões: **Discovery** (extrai situação atual, dores, objetivos, stakeholders,
restrições e perguntas em aberto) e **Assessment** (diagnóstico + recomendações
priorizadas). Ambas as saídas são **rascunho para revisão humana** e podem ser avaliadas
via os endpoints de feedback/métricas já existentes.

## Regras

- Reusa o motor de IA (`_ai_run`): depende de `AI_ENABLED`; desligado → 503. Respeita o
  limite diário de uso de IA (429). Cada resposta é auditada em `AiInteraction`
  (features `meeting_discovery` / `meeting_assessment`), ligada ao projeto da reunião.
- O contexto passado ao modelo contém **apenas** os dados desta reunião (projeto, título,
  data, situação e a transcrição, truncada por limite de caracteres) — anti-vazamento;
  nada é executado sozinho.
- Reunião **sem transcrição** → 400; os botões só aparecem quando há transcrição.
- Acesso segue o RBAC do recurso `meeting` (não altera `permissions.py`).

## Aceite

Numa reunião com transcrição, o usuário aciona **Discovery** ou **Assessment** e recebe o
texto para revisão, com o id da interação registrado. A saída pode ser avaliada com 👍/👎.

## Regressão crítica

Reunião sem transcrição retorna 400; IA desligada retorna 503; limite diário retorna 429; e
**fornecedor fora do ar retorna 502** (rodada 2 da FDD 024) — nada é gravado quando a chamada não
completa, então não sobra artefato pela metade nem interação sem resposta. A interação é registrada
com a feature correta e vinculada ao projeto da reunião.
