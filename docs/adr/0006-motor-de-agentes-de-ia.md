# ADR 0006 — Motor de agentes de IA (especializados, RBAC, auditoria e avaliação)

**Status:** aceito

## Contexto

A Versão 4 e a jornada assistida (RFC 0002) pedem agentes de IA por área/etapa. Precisamos de uma
base comum, sem multiplicar código, reusando `ai.py` e mantendo revisão humana e anti-vazamento.

## Decisão

Um módulo `apps/core/agents.py` com um registro `AGENTS`: cada `Agent` tem `key`, `label`, papéis
permitidos (RBAC), `system` prompt e um `build_context` que **só lê os dados da sua área**
(ferramentas limitadas). O endpoint `POST /api/v1/agents/<key>/` valida flag/limite (reusa
`_ai_run`) e RBAC, monta o contexto e chama `ai.complete`; a resposta é sempre para revisão humana.
Toda interação é auditada em `AiInteraction` (agora com `rating`), e há **avaliação contínua**:
`POST /ai/feedback/` (👍/👎 do dono) e `GET /ai/metrics/` (admin: uso e % positivo). Primeiras
instâncias: `comercial`, `entrega`, `financeiro`.

## Consequências

Novos agentes (por etapa da jornada) são configuração sobre o mesmo motor. Uso é interno e gated por
papel; nada comercial vai ao portal do cliente. Depende de `AI_ENABLED`; desligado, os endpoints
retornam 503. Evoluir para memória/conversa multi-turno ou ferramentas de ação fica para decisão
futura (hoje é Q&A de turno único, sem executar ações).
