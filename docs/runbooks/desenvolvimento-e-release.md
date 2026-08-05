# Runbook — desenvolvimento e release

## Desenvolvimento

Copie `.env.example` para `.env`, execute `docker compose up --build` e aplique migrações pela API. Nunca use credenciais reais no ambiente local.

## Release

1. Execute a suite completa e gere o OpenAPI.
2. Confirme backup do banco antes de migrações.
3. Publique artefato versionado, execute smoke tests e acompanhe health checks.
4. Se houver falha, reverta a aplicação e restaure o banco somente conforme o plano de migração.

## Produção

Subida em produção, variáveis obrigatórias, ordem de ativação do HSTS e rollback: `producao.md`.
O compose de produção é outro arquivo (`docker-compose.prod.yml`) — o daqui é de desenvolvimento e
roda `runserver`.

