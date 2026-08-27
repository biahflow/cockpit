# ADR 0042 — Trunk-based: `main` promove HML e tag da `main` promove produção

**Status:** aceita

## Contexto

O Pulse adota Pull Requests com Human Merge Gate, CI remoto obrigatório e branches de task curtas. Após merge, o repositório já possui um workflow `deploy-hml` disparado por `push` na `main` para mudanças de aplicação.

Precisamos explicitar a relação entre integração, homologação e produção sem criar branches de ambiente que possam divergir da `main`, e garantir que produção execute exatamente o mesmo artefato binário/container que foi homologado.

## Decisão

Adotar trunk-based development com **build once, promote many**:

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
BUILD ONCE
  ↓
immutable image digest
  ↓
automatic HML deployment of that digest
  ↓
HML validation
  ↓
READY_FOR_PRODUCTION
  ↓
release tag created from approved main commit
  ↓
PROMOTE SAME DIGEST
  ↓
PROD
```

### 1. `main` é o trunk canônico

- `main` é a única branch longa de integração.
- Não adotar `develop`, `hml`, `staging` ou `prod` como branches permanentes do fluxo normal.
- Tasks usam branches curtas e worktrees dedicados conforme EngineeringOS.
- Integração ocorre exclusivamente por Pull Request e Human Merge Gate.

### 2. Merge em `main` constrói uma vez e promove para HML

Mudança de aplicação mergeada em `main` dispara:

1. validação pós-merge da revisão real integrada;
2. build único das imagens de aplicação;
3. publicação em registry com identificação por SHA;
4. resolução e registro dos digests imutáveis publicados;
5. deploy automático para HML usando o artefato/digest produzido;
6. smoke/runtime/integration checks;
7. verificação de que HML executa o digest esperado.

HML é uma projeção da `main`, não uma fonte de verdade paralela.

Deve ser possível identificar tanto o SHA da `main` quanto os digests atualmente publicados em HML.

### 3. Produção é promovida por tag, sem rebuild

Produção somente deve ser disparada por uma release tag apontando para commit já alcançável pela história protegida da `main` e homologado com artefatos conhecidos.

Exemplo:

```text
main @ abc123
  ↓
backend digest sha256:AAA
frontend digest sha256:BBB
  ↓
HML validado com AAA/BBB
  ↓
tag v1.4.0 → abc123
  ↓
PROMOTE AAA/BBB
  ↓
PROD usa AAA/BBB
```

A pipeline de produção MUST verificar deterministicamente, antes do deploy:

- que o commit apontado pela tag pertence à história protegida da `main`;
- que existem digests registrados para o SHA;
- que HML validou exatamente esses digests;
- que os artefatos ainda existem e seus digests conferem;
- que o deploy de PROD utilizará/promoverá os mesmos digests;
- que nenhuma etapa de `docker build` ou equivalente será executada para aplicação em produção.

Se HML e PROD utilizarem registries/projetos diferentes, a promoção pode copiar ou retaggear o mesmo manifest/blob por digest. Isso não é rebuild.

A tag representa decisão explícita de release e não pode ser criada automaticamente pelo Builder como efeito colateral de uma Issue comum.

### 4. Invariante de identidade do artefato

A prova principal de release é:

```text
HML backend digest  == PROD backend digest
HML frontend digest == PROD frontend digest
```

Tags são referências humanas de release; digest é a identidade imutável usada para provar que o mesmo artefato percorreu os ambientes.

### 5. `PR merged` não significa produção

Estados conceituais:

```text
MERGED_TO_MAIN
POST_MERGE_CI_PENDING
POST_MERGE_CI_FAILED
POST_MERGE_CI_GREEN
ARTIFACT_BUILDING
ARTIFACT_READY
HML_DEPLOYING
HML_DEPLOY_FAILED
HML_READY
READY_FOR_PRODUCTION
PRODUCTION_PROMOTING
PRODUCTION_DEPLOYING
PRODUCTION_DEPLOY_FAILED
PRODUCTION_READY
```

Merge integra engenharia e inicia a promoção para HML. Produção continua sendo um lifecycle separado.

### 6. Rollback

Rollback preferencial é redeploy de um digest anteriormente conhecido e validado, sem reconstruir código-fonte.

### 7. Hotfixes

Hotfix também converge para o trunk:

```text
fix branch
→ PR / emergency human gate
→ main
→ build once
→ validação adequada ao risco
→ tag de release
→ promote same digest
→ PROD
```

Não manter correção somente em produção ou em branch paralela sem retorno para `main`.

## Consequências

### Positivas

- uma única linha canônica de código;
- elimina drift causado por rebuild diferente entre HML e PROD;
- promoção para produção é auditável por tag, SHA e digest;
- rollback pode reutilizar artefato conhecido;
- reduz variabilidade de toolchain/dependências entre ambientes;
- combina com branches curtas/worktrees e PRs pequenos.

### Trade-offs

- exige persistir/descobrir o digest produzido no deploy de HML;
- registries separados podem exigir cópia/promote de manifest;
- garbage collection/retention não pode apagar artefato ainda elegível para release/rollback;
- `main` precisa permanecer saudável e deployável;
- produção exige disciplina de release/tag e validação de HML.

## Evidência mínima de release

Quando aplicável, registrar:

- merge/main SHA;
- post-merge CI run;
- artifact repository/name;
- backend/frontend digest(s);
- HML deployment run;
- SHA/digest efetivamente executado em HML;
- smoke/runtime validation;
- release tag;
- PROD promotion/deployment run;
- SHA/digest efetivamente executado em PROD;
- aprovação/gate de release.

## Relação com EngineeringOS

A política genérica está em:

- `workflows/trunk-based-delivery.md`
- `workflows/ci-feedback-and-repair.md`
- `workflows/git-publishing-and-human-merge.md`
- `workflows/worktree-execution.md`

O Pulse mantém neste ADR somente a decisão específica de produto/ambiente.
