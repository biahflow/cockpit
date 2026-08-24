# ADR 0042 — Trunk-based: `main` promove HML e tag da `main` promove produção

## Status

Accepted

## Contexto

O Pulse adota Pull Requests com Human Merge Gate, CI remoto obrigatório e branches de task curtas. Após merge, o repositório já possui um workflow `deploy-hml` disparado por `push` na `main` para mudanças de aplicação.

Precisamos explicitar a relação entre integração, homologação e produção sem criar branches de ambiente que possam divergir da `main`.

## Decisão

Adotar trunk-based development com:

```text
short-lived task branch / worktree
  ↓
PR + required CI green
  ↓
HUMAN MERGE GATE
  ↓
main
  ↓
post-merge quality
  ↓
automatic HML deployment
  ↓
HML validation
  ↓
READY_FOR_PRODUCTION
  ↓
release tag created from approved main commit
  ↓
PROD
```

### 1. `main` é o trunk canônico

- `main` é a única branch longa de integração.
- Não adotar `develop`, `hml`, `staging` ou `prod` como branches permanentes do fluxo normal.
- Tasks usam branches curtas e worktrees dedicados conforme EngineeringOS.
- Integração ocorre exclusivamente por Pull Request e Human Merge Gate.

### 2. Merge em `main` promove para HML

Mudança de aplicação mergeada em `main` dispara:

1. validação pós-merge da revisão real integrada;
2. deploy automático para HML;
3. smoke/runtime/integration checks definidos pela pipeline.

HML é uma projeção da `main`, não uma fonte de verdade paralela.

Deve ser possível identificar o SHA da `main` atualmente publicado em HML.

### 3. Produção é promovida por tag imutável

Produção somente deve ser disparada por uma release tag apontando para commit já alcançável pela história protegida da `main`.

Exemplo:

```text
main @ abc123
  ↓
HML abc123 validado
  ↓
tag v1.4.0 → abc123
  ↓
PROD abc123
```

A pipeline de produção MUST verificar deterministicamente que o commit apontado pela tag pertence à história da `main` antes de qualquer deploy.

A tag representa decisão explícita de release e não pode ser criada automaticamente pelo Builder como efeito colateral de uma Issue comum.

### 4. `PR merged` não significa produção

Estados conceituais:

```text
MERGED_TO_MAIN
POST_MERGE_CI_PENDING
POST_MERGE_CI_FAILED
POST_MERGE_CI_GREEN
HML_DEPLOYING
HML_DEPLOY_FAILED
HML_READY
READY_FOR_PRODUCTION
PRODUCTION_DEPLOYING
PRODUCTION_DEPLOY_FAILED
PRODUCTION_READY
```

Merge integra engenharia e inicia a promoção para HML. Produção continua sendo um lifecycle separado.

### 5. Artefato imutável

Estado desejado de hardening:

```text
build once
→ verify
→ deploy HML
→ promote same immutable artifact
→ PROD
```

Enquanto a pipeline ainda rebuildar a partir do mesmo SHA/tag, a origem e os inputs de build devem permanecer imutáveis e auditáveis. Promover exatamente o mesmo artefato verificado em HML é a evolução preferida.

### 6. Hotfixes

Hotfix também converge para o trunk:

```text
fix branch
→ PR / emergency human gate
→ main
→ validação adequada ao risco
→ tag de release
→ PROD
```

Não manter correção somente em produção ou em branch paralela sem retorno para `main`.

## Consequências

### Positivas

- uma única linha canônica de código;
- reduz drift entre HML, PROD e `main`;
- promoção para produção é auditável por tag/SHA;
- simplifica rollback e rastreabilidade;
- combina com branches curtas/worktrees e PRs pequenos;
- elimina necessidade de merge entre branches de ambiente.

### Trade-offs

- `main` precisa permanecer saudável e deployável;
- mudanças incompletas podem exigir feature flags;
- falha pós-merge fica visível na `main` e deve ser tratada rapidamente;
- produção exige disciplina de release/tag e validação de HML.

## Evidência mínima de release

Quando aplicável, registrar:

- merge/main SHA;
- post-merge CI run;
- HML deployment run;
- SHA/revisão em HML;
- smoke/runtime validation;
- release tag;
- PROD deployment run;
- SHA/revisão em PROD;
- aprovação/gate de release.

## Relação com EngineeringOS

A política genérica está em:

- `workflows/trunk-based-delivery.md`
- `workflows/ci-feedback-and-repair.md`
- `workflows/git-publishing-and-human-merge.md`
- `workflows/worktree-execution.md`

O Pulse mantém neste ADR somente a decisão específica de produto/ambiente.
