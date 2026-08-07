# Runbook — desenvolvimento e release

## Desenvolvimento

Copie `.env.example` para `.env`, execute `docker compose up --build` e aplique migrações pela API. Nunca use credenciais reais no ambiente local.

## Release

1. Execute a suite completa e gere o OpenAPI.
   **E o corpus de conhecimento** (FDD 029): ele é derivado de `docs/` e `PRD.md`, vive commitado e
   é conferido no CI por `git diff --exit-code`, exatamente como o `openapi.yaml`. Editou um ADR,
   uma FDD ou um runbook? Rode `uv run python manage.py build_knowledge_corpus` e commite o
   `.jsonl`. No deploy, `manage.py ingest_knowledge` traz o artefato para o banco e embeda o que
   mudou — **não** roda no boot, porque boot que fala com a OpenAI é boot que não sobe quando ela
   cai.
2. Confirme backup do banco antes de migrações.
3. Publique artefato versionado, execute smoke tests e acompanhe health checks.
4. Se houver falha, reverta a aplicação e restaure o banco somente conforme o plano de migração.

## Produção

Subida em produção, variáveis obrigatórias, ordem de ativação do HSTS e rollback: `producao.md`.
O compose de produção é outro arquivo (`docker-compose.prod.yml`) — o daqui é de desenvolvimento e
roda `runserver`.

