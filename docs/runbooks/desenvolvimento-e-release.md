# Runbook — desenvolvimento e release

## Desenvolvimento

Copie `.env.example` para `.env` e execute `docker compose up --build`. A API aplica as migrações
automaticamente. O passo a passo completo, incluindo criação idempotente do administrador, portas,
logs e execução sem Docker, está no `README.md`. Nunca use credenciais reais no ambiente local.

## Release por artefato imutável

1. Execute a suíte completa e gere o OpenAPI.
   **E o corpus de conhecimento** (FDD 029): ele é derivado de `docs/` e `PRD.md`, vive commitado e
   é conferido no CI por `git diff --exit-code`, exatamente como o `openapi.yaml`. Editou um ADR,
   uma FDD ou um runbook? Rode `uv run python manage.py build_knowledge_corpus` e commite o
   `.jsonl`. No deploy, `manage.py ingest_knowledge` traz o artefato para o banco e embeda o que
   mudou — **não** roda no boot, porque boot que fala com a OpenAI é boot que não sobe quando ela
   cai.
2. Faça merge em `main`. O workflow `deploy-hml` constrói backend e frontend uma única vez, publica
   as imagens nos registries configurados e resolve seus digests imutáveis.
3. O mesmo workflow migra e implanta HML usando `repository@sha256:digest`, executa probes e smoke
   tests, confere o digest observado em todos os recursos e publica o artefato de evidência
   `hml-release-<sha>-<run>-<attempt>`.
4. Homologue o SHA em HML. Não crie a tag enquanto os checks de `main` e a evidência desse SHA não
   estiverem verdes.
5. Um mantenedor autorizado cria uma tag anotada estável `vX.Y.Z` apontando para esse SHA. A tag
   precisa obedecer à protection rule `v*`; versões de pré-lançamento não são aceitas.
6. O workflow `promote-prod` exige que o SHA pertença a `main`, localiza exatamente uma execução HML
   bem-sucedida, valida o digest do arquivo e o conteúdo da evidência, e então aguarda os gates do
   ambiente GitHub `production`.
7. Após aprovação, o workflow copia os manifests por digest ao registry de produção, sem reconstruir
   a aplicação. Migração, serviços e scheduler são implantados pelos mesmos digests homologados.
8. Probes, smoke tests e leitura dos recursos em execução confirmam os digests. O artefato
   `production-release-<tag>-<sha>-<run>-<attempt>` prova, por imagem, que HML e PROD são idênticos.

Falhas de evidência ausente, ambígua, expirada, referente a outro SHA/run ou com digest divergente
interrompem a promoção antes do deploy. O probe de integração continua sendo diagnóstico não
bloqueante; smoke e verificação de identidade são bloqueantes.

## Configuração administrativa

Antes da primeira promoção, configure a protection rule de tags `v*`, os revisores/autorizadores do
ambiente `production` e todas as variáveis `PROD_*` listadas em
`docs/implementation/immutable-artifact-promotion.md`. O workflow não contém identificadores ou
segredos de produção e falha se a configuração estiver incompleta.

A retenção dos artefatos de evidência segue a política do repositório GitHub. Ela deve cobrir a
janela de homologação e rollback; não reduza essa retenção sem decisão operacional registrada.

## Rollback

Selecione um artefato de evidência de uma versão conhecida como saudável e reimplante os refs
`repository@sha256:digest` registrados nele. Rollback nunca reconstrói código. Banco e documentos só
devem ser restaurados conforme o plano da migração e o runbook de backup; uma reversão de aplicação
não autoriza, por si só, restaurar dados.

## Produção

Subida em produção, variáveis obrigatórias, ordem de ativação do HSTS e rollback: `producao.md`.
O compose de produção é outro arquivo (`docker-compose.prod.yml`) — o daqui é de desenvolvimento e
roda `runserver`.
