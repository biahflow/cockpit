# Contexto do projeto — Engineering OS

## Propósito e escopo

O Portal Biahflow é um portal interno que conduz oportunidades comerciais até a execução de
projetos. Este documento concentra o contexto operacional necessário para usar a Engineering OS
neste repositório; ele **referencia** as fontes canônicas, sem duplicar requisitos, decisões ou
procedimentos.

## Fontes de verdade

| Responsabilidade | Fonte canônica | Uso |
| --- | --- | --- |
| Produto, escopo e critérios de sucesso | [`PRD.md`](../PRD.md) | Entender o produto atual e seus limites. |
| Inventário e estado de features/work items | [`roadmap.md`](../roadmap.md) | Localizar ID, estado e FDD de cada item relevante. A localização na raiz é uma exceção documentada do projeto. |
| Especificação de features | [`docs/fdd/`](fdd/) | Ler a FDD relevante antes de mudar comportamento. |
| Decisões arquiteturais | [`docs/adr/`](adr/) | Preservar decisões duráveis e seus limites. |
| Mudanças transversais ou incompatíveis | [`docs/rfcs/`](rfcs/) | Consultar RFCs antes de alterar contratos amplos. |
| Arquitetura e operação | [`docs/architecture.md`](architecture.md) e [`docs/runbooks/`](runbooks/) | Entender topologia, limites e procedimentos operacionais. |
| Validação executável | [`.github/workflows/quality.yml`](../.github/workflows/quality.yml) | Fonte canônica dos gates automatizados de CI. |

`CHANGELOG.md` é histórico de releases; não é fonte de estado de feature. Quando duas fontes
operacionais divergirem, registre `SOURCE_OF_TRUTH_CONFLICT` e peça decisão humana antes de
alterar a informação conflitante.

## Ciclo de feature e trabalho

1. O `roadmap.md` identifica a feature/work item, seu estado e a FDD correspondente.
2. A FDD define jornada, regras, aceite, regressões e escopo excluído.
3. ADR é exigida para decisão técnica durável; RFC é exigida para mudança transversal ou
   incompatível.
4. O planejamento lê PRD, FDD, ADRs, RFCs e o código/testes necessários, sem inventar requisitos.
5. Mudanças aprovadas preservam `/api/v1/`, atualizam a documentação aplicável e executam os
   perfis de validação pertinentes.

## Perfis de validação

Os comandos e a ordem executável pertencem ao workflow de qualidade. Os perfis atualmente
disponíveis são:

| Perfil | Evidência canônica |
| --- | --- |
| Compose | Configuração dos composes de desenvolvimento e produção. |
| Backup/recovery | `.github/scripts/backup-drill.sh`. |
| Backend lint, tipos, segurança, checks e migrações | `ruff`, `mypy`, `pip-audit`, `manage.py check` e `makemigrations --check`. |
| Backend testes e contrato | `pytest`, OpenAPI validado e diffs de `openapi.yaml`. |
| Corpus de conhecimento | `build_knowledge_corpus` e diff de `apps/core/knowledge_corpus.jsonl`. |
| Segurança de produção | `collectstatic` e `check --deploy --tag security` em ambiente simulado. |
| PostgreSQL/pgvector | Testes marcados `pgvector` contra Postgres. |
| Frontend | `npm audit`, lint, testes, build e E2E Playwright. |

Selecione apenas os perfis aplicáveis à mudança, sem desativar verificações. A CI completa é
requerida antes de promoção de ambiente.

## Gates humanos

Aplicam-se os guardrails globais de Git, banco e produção, além destes gates do projeto:

- mudança de produção, segredo, IAM, deploy, rollback ou infraestrutura destrutiva exige aprovação
  humana explícita;
- migração destrutiva, mudança arquitetural durável, exceção de segurança e mudança incompatível de
  API exigem aprovação humana e a documentação correspondente;
- agentes não aprovam o próprio trabalho nem abrem/mesclam PRs sem autorização;
- artefatos de origem ou intenção desconhecida são preservados como
  `PREEXISTING_USER_ARTIFACT`.

## Adaptadores

[`AGENTS.md`](../AGENTS.md) é o adaptador para Codex e [`CLAUDE.md`](../CLAUDE.md) é o
adaptador para Claude Code. Ambos devem apontar para este contexto e não podem enfraquecer as
regras globais da Engineering OS.

## Artefatos derivados

Alterações em ADRs, FDDs, RFCs, runbooks, `PRD.md`, `docs/architecture.md`,
`docs/operacao.md` ou `docs/captacao-de-leads.md` exigem regenerar
`backend/apps/core/knowledge_corpus.jsonl` com `cd backend && uv run python manage.py
build_knowledge_corpus` e versionar o resultado junto. O manifesto do corpus é explícito; outros
documentos só passam a integrá-lo mediante mudança deliberada nesse manifesto.
