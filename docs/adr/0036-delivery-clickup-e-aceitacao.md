# ADR 0036 — ClickUp como SoR de Delivery e aceitação separada do merge

**Status:** Superseded by ADR 0040  
**Data:** 2026-08-24

## Contexto histórico

Esta ADR registrou uma etapa intermediária da arquitetura em que ClickUp seria o sistema da verdade de Delivery e GitHub seria a fonte da verdade da execução de engenharia.

A decisão de separar merge técnico de aceite de negócio permanece válida, mas o ownership de Delivery foi simplificado posteriormente.

## Decisão superseded

O desenho anterior era:

`ClickUp Task → GitHub Issue → Build → PR → CI/Review → Merge → CLIENT_REVIEW`

ClickUp manteria backlog, prioridade, responsável, datas e status de Delivery.

## Regra preservada

Um `pull_request.merged` **não** equivale automaticamente a `DONE` quando há necessidade de aceite de negócio.

A regra preservada é:

`PR merged → READY_FOR_ACCEPTANCE → CLIENT_REVIEW → ACCEPTED → DONE`

A aceitação deve registrar evidência suficiente para auditoria, incluindo ator, timestamp, versão/entrega e identificadores de correlação quando aplicável.

## Substituição

A ADR 0040 substitui a escolha de ClickUp e define o core operacional como:

`Pulse ↔ GitHub API/Webhooks ↔ One`

GitHub Issues passam a ser o Source of Truth do trabalho de engenharia; Pulse mantém o estado operacional de negócio; One registra a experiência e o aceite do cliente.
