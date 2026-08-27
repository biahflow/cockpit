# ADR 0001 — Django, React e PostgreSQL

**Status:** aceita

## Decisão

Usar Django/DRF como API, React/TypeScript como frontend e PostgreSQL como banco transacional. Docker Compose fornece ambiente consistente de homologação.

## Consequências

O contrato OpenAPI é a fronteira entre aplicações. Regras de negócio e autorização permanecem na API.

