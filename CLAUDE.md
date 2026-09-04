# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Portal Biahflow is an internal tool that carries a commercial opportunity from sale
through to project execution. Backend is Django + DRF (Python 3.12) serving a versioned
`/api/v1/` API; frontend is a React + Vite + TypeScript SPA styled with Tailwind v4.
The product spec, scope, and roadmap live in `PRD.md` and `roadmap.md`; most project
documentation is in Portuguese (pt-BR). Read
[`docs/project-context.md`](docs/project-context.md) before planning
or changing work: it identifies the project's canonical sources, validation profiles, and human
approval gates. It complements the global Engineering OS and does not replace it.

The global layer is vendored and pinned at
[`docs/engineering-os/`](docs/engineering-os/PROVENANCE.md), tag `v0.1.0`. It is the **first**
source on conflict (ADR 0045), and the precedence is asymmetric: this repository may *add*
constraint and may never weaken a global guardrail or remove a human gate. The mirror is a
faithful copy and is not edited here — a change to a global rule is a pull request against the
origin, and reaches this repository as a reviewed pin bump.

## Commands

Backend (run from `backend/`, tooling is [uv](https://docs.astral.sh/uv/)):

```bash
uv sync                                        # install deps
uv run pytest                                  # full suite; enforces --cov-fail-under=90 on apps.core
uv run pytest apps/core/tests/test_api.py      # single file
uv run pytest -k test_convert                  # single test by name
uv run mypy apps config                        # type check (tests/ are excluded from mypy)
uv run ruff check .                            # lint (E,F,I,B,UP; line-length 100)
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

Frontend (run from `frontend/`):

```bash
npm install
npm test            # vitest + coverage
npm run test:watch  # vitest watch
npm run lint        # eslint
npm run build       # tsc -b && vite build
npm run e2e         # playwright
npm run dev
```

Full stack: `docker compose up --build`, then create the first admin with
`docker compose exec api uv run python manage.py createsuperuser`.
Docker host ports use a high range to avoid collisions: web SPA `19173`, API
`19000` (→ container `8000`), Mailpit `19025`. The container-internal network is
unchanged (the Vite dev server proxies `/api` to `http://api:8000`), so only the host
mappings differ. Running locally without Docker uses the defaults (API `8000`,
web `5173`). The README table is the source of truth for host URLs.

Before opening a PR, select the applicable validation profiles from
[`docs/project-context.md`](docs/project-context.md). The executable
source of truth for the complete CI suite is [`.github/workflows/quality.yml`](.github/workflows/quality.yml).

## Architecture

**The entire domain is one Django app: `backend/apps/core`.** Models, serializers,
views (viewsets), permissions, and URLs all live there. There is no service layer —
business rules live in model `clean()`/`save()` methods and in viewset actions.

Core domain flow (`apps/core/models.py`): `Account` → `Contact`, `Lead` → `Qualification` →
`CommercialOpportunity` (on a configurable `PipelineStage`) → converts into a `Project` →
`Milestone`/`Task` (both subclass the abstract `WorkItem`) plus `Document`. `User` extends
`AbstractUser` with a `role` (admin/sales/delivery). `Invitation` drives email-based
onboarding.

Key cross-cutting patterns to preserve:

- **Soft delete.** Most business models extend `TimestampedModel` and are archived via
  `archive()` (sets `archived_at`), never hard-deleted. `ArchiveModelViewSet`
  (`views.py`) filters `archived_at__isnull=True` in `get_queryset` and overrides
  `perform_destroy` to archive. New business resources should follow this. It also exposes
  `?archived=1` and a `POST /unarchive/` action — that action resolves the object from the **raw**
  queryset, since `get_object()` would filter out exactly what is being restored. Archiving does
  **not** cascade: if a parent's children are listed anywhere on their own, override
  `perform_destroy` to refuse with `ArchiveConflict` (409) or archive them in the same transaction,
  or you leave orphans pointing at a hidden row. UI copy says "Arquivar"; reserve "Excluir" for the
  two resources that really hard-delete (pipeline stage, journey phase). See FDD 025.
- **Authorization is two-layered.** `RolePermission` (`permissions.py`) enforces a
  coarse role policy keyed off each viewset's `resource` string attribute
  (e.g. `resource = "account"`), plus per-object `has_object_permission`, which
  **denies by default** so a new resource starts closed. When adding a viewset, set
  `resource` and update `RolePermission`.
- **Project scope is the delivery boundary.** Delivery users see only the projects they
  belong to (`ProjectMember`). The single source of the rule is
  `Project.objects.visible_to(user)` / `project_scope_q(user, path)` in `models.py` —
  never re-express it. Anything that hangs off a project uses `ProjectScopedMixin`
  (`views.py`), which covers read **and** write: without the write guard, creating a task
  in someone else's project would self-grant access. Aggregators that bypass querysets
  (`/clients/overview/`, `/risk/`, `/health/`, `/dashboard/`, `agents.build_delivery_context`)
  are narrowed by hand and each has its own test. See RFC 0003, ADR 0010, FDD 018.
- **Mixins on viewsets must not have docstrings.** drf-spectacular uses the class docstring
  as each endpoint's `description`, so a mixin at the top of the MRO leaks its own text into
  dozens of unrelated routes in `openapi.yaml`. Use a comment above the class instead.
- **`Account → Engagement → Project` is the spine, and the Engagement is mandatory.** An
  `Engagement` (ADR 0050, FDD 046) is the transformation mandate a client contracted: it groups
  several sales and several projects that are the *same* work. `Project.engagement` is NOT NULL —
  a one-off sale is **not** a special case, it gets a single-scope Engagement that
  `convert-to-project` creates on its own. `Project.client` was removed in Phase 6; the canonical
  account is `engagement.account`, and the `/api/v1/` still emits `client` as a read-only alias
  derived from `engagement.account_id`. The Engagement is **not** an access
  boundary — Delivery scope is still `ProjectMember`, and engagement visibility *derives* from
  `Project.objects.visible_to(user)`, never the reverse. Sales writes it; Delivery only reads.
  The mandate also records `commercial_model` (`paid`/`design_partner`, default `paid`): a
  design partner receives Discovery free of charge in exchange for serving as case and proving
  ground, and it does **not** go through a sale — nothing in the schema ever required one.
- **A organização é `Account`, e "Cliente" é o rótulo de um dos estados dela.** O nome canônico
  vale desde antes de a conta comprar (`language-map` §4), e `Account.lifecycle_status` tem três
  valores: `prospect` (não fechou), `active` (é cliente) e `inactive` (**já foi** cliente e hoje
  não tem trabalho em andamento). Só `prospect → active` é automático — o signal
  `_promote_account_on_won`; entrar em `inactive` é escolha de quem edita a conta, porque "não tem
  trabalho em andamento" não é fato observável no banco. **`inactive` não é arquivamento**: a
  conta continua na listagem e no agregado, e só o `archived_at` a esconde
  (`test_inativo_nao_e_arquivado.py`). Na `/api/v1/` a chave `status` continua saindo e sendo
  aceita, com o mesmo valor de `lifecycle_status`. A superfície (menu "Contas", as cinco pastilhas
  de filtro, as três pílulas, os textos de vazio) é governada pelo DAP
  `docs/design/dap-lifecycle-status-r1/`, decisões **A1 · B1 · C1**, e os mapas de rótulo e de
  variante moram em `frontend/src/components/AccountLifecycle.tsx` — um lugar só, no molde de
  `StatusDot` (ADR 0026). A rota da SPA é `/contas`; `/clientes*` redireciona e morre na
  `/api/v2/`. A r2 (decisão **A1**, aprovada em 03/09/2026) estendeu "Conta" ao detalhe da conta,
  aos formulários do Comercial e do Financeiro e ao alvo de vínculo de Documentos; "Cliente" segue
  sendo só o rótulo do estado e o eixo de pendência (`Fornecedor`/`Cliente`).
- **Opportunity → Project conversion** is the central business action: the
  `convert-to-project` `@action` on `CommercialOpportunityViewSet`. It requires the sale be in the
  "won" stage, enforces sales/admin role, and carries `CommercialOpportunity.service` over to
  `Project.service` (payload wins).
  **"Converts exactly once" is no longer a database guarantee — it moved into the action** (ADR
  0050). `Project.opportunity` was a `OneToOneField` and became
  `Project.originating_commercial_opportunity`, a 1-N FK, because a recurring sale (Transformation
  Partnership) legitimately originates several projects. The old constraint forbade two things and
  only one still deserved forbidding: a *second project from the same sale* is now allowed and is
  created via `POST /projects/`; a *double-click duplicating a project* is not. So the action
  keeps the 409 with an explicit guard (any **live** project with that origin) plus
  `select_for_update()` on the opportunity inside the transaction — the lock is what the
  `IntegrityError` used to provide for free, and without it two concurrent requests both create.
  The surviving `except IntegrityError` carries **no** uniqueness anymore; it only turns a
  residual integrity failure into a rolled-back 409 instead of a half-written 500. A guarantee
  that leaves the schema only holds while it is tested:
  `backend/tests/regression/test_conversion_is_single_use.py`. Consequence: an opportunity whose
  only project is archived now reconverts (201) instead of 409 — the archived row no longer
  occupies a slot, which closes the last dead end of FDD 025.
  `CommercialOpportunitySerializer.project`/`project_archived` keep their old shape (one id or null, never a
  list): the oldest live project, or the oldest archived one when no live project remains.
- **Product tiers live on `Service`, and they are the FDE ladder.** A `Service` with a `tier`
  (`qualification_call`/`discovery_sprint`/`feasibility`/`prove`/`scale`/`transformation`) is one
  sellable step, seeded by migrations `0020` and `0050`; a blank `tier` is a loose catalog entry.
  They are **six** since ADR 0053: `discovery_assessment` left the enum (migration `0064`, guarded
  — it refuses to delete a row that any `CommercialOpportunity`, `Project`, `Invoice` or blueprint
  still points at, and refuses to overwrite a row someone edited on screen), because the **Design
  Partner** now covers free entry into a new vertical and a step nobody sells is a funnel column
  that never fills. The same migration prices the Discovery Sprint at R$ 3.000 — but only over the
  still-seeded row, since editing a price on screen is the normal path. The tier drives the kickoff
  template (`kickoff.KICKOFF_TEMPLATES`), the invoice schedule (`invoices.INVOICE_SCHEDULES`), the
  proposal prompt context (`ai.build_opportunity_context`) and the `by_tier` funnel in analytics —
  see FDD 015, ADR 0048, ADR 0053. **Free is the step, not the zero price**
  (`frontend/src/tiers.ts`): only the Qualification Call is free; zero anywhere else means "price
  to be decided" — the Transformation Partnership is monthly recurring and the catalog still cannot
  represent recurrence. The Design Partner is **not** a field: what is granted lives in the
  opportunity's `estimated_value` as a discount, because a zeroed opportunity disappears from the
  funnel and value granted is a number someone looks at.
- **Cada gate tem seu vocabulário, e um campo só carrega os dois.** A Feasibility responde *"a
  tecnologia consegue fazer a tarefa?"* → `GO`·`CONDITIONAL GO`·`REDESIGN`·`NO-GO`; o PROVE responde
  *"funcionou em produção controlada?"* → `SCALE`·`ITERATE`·`STOP` (ADR 0053, emenda na FDD 033).
  `ProjectPhase.gate_decision` continua **um** campo com as sete choices
  (`ProjectPhase.DECISOES_DO_GATE`) — duas colunas seriam duas definições do mesmo fato. Quem
  estreita é `models.decisoes_do_gate`, **derivando de `JourneyPhase.canonical_stage`** e não de um
  campo novo: quem diz que o gate do PROVE é SCALE/ITERATE/STOP é a metodologia, e `canonical_stage`
  já é "qual fase FDE é esta". Fase de gate **sem** classificação recebe as quatro — é o
  comportamento de toda fase semeada. As três saídas novas não inventam efeito: caem nos mesmos três
  (`CONCLUEM_E_AVANCAM`/`REABREM_A_ANTERIOR`/`REGISTRAM_E_PARAM`), e é por efeito que `journey.py` e
  a tela ramificam — `STOP` é o `cancelled` do `NO-GO` e `ITERATE` o `replanned` do `REDESIGN` em
  `situation`. **A validação da decisão mora em `journey.apply_gate`, não na view**: o vocabulário
  depende da fase ativa, e só ali ela é conhecida — 400 via `exceptions.InvalidInput` (o pedido é
  que está errado), nunca `StateConflict`, que é 409. O esquema publica as sete e o servidor
  estreita. Na tela, `frontend/src/journey.ts` é o **único** mapa (`GATE_DECISION_LABEL`,
  `GATE_EFFECT`, `gateDecisions`), lido pelo detalhe do projeto e pela tela de Jornada; os rótulos
  não se traduzem.
- **A qualificação vem antes da venda, e é entidade.** `POST /leads/{id}/convert/` criava, no mesmo
  clique, uma `Account` **e** uma `CommercialOpportunity` no degrau gratuito — uma conversa de trinta minutos
  entrava no funil como venda registrada e podia virar `Project`. Desde a ADR 0049 ele registra uma
  `Qualification` (autor, data, cinco eixos, `outcome` ∈ `qualified`·`nurture`·`disqualified`) e
  **não cria oportunidade**; a venda nasce num ato explícito,
  `POST /qualifications/{id}/open-opportunity/`, que recusa origem não-qualificada. Um lead tem
  **várias** avaliações de propósito — o `nurture` de hoje vira `qualified` em seis meses, e
  sobrescrever a primeira apagaria o histórico que a entidade existe para guardar; por isso
  `nurture` **não arquiva o lead**, que é o único jeito de ele voltar ao radar. A IA é insumo:
  `ai_suggested_outcome`/`ai_score_snapshot` guardam a sugestão e nada os copia para `outcome`. As
  duas invariantes vivem no **modelo** e não só na view (`CommercialOpportunity.clean()`, `Project.clean()`),
  porque shell, admin e migração não passam por rota. Ver FDD 044.
- **`Service.category` separa a porta do degrau.** `acquisition` é oferta de aquisição — hoje só a
  Qualification Call —, e ela nunca gera `CommercialOpportunity` nem `Project`; `commercial` é degrau
  vendável e é o default. A distinção é por **categoria, não por preço**: o Design Partner recebe
  Discovery, gate e PROVE sem cobrar (ADR 0053) e aqueles continuam degraus vendáveis. Restam
  **cinco** degraus vendáveis na escada da FDD 015, depois que a ADR 0053 tirou o
  `discovery_assessment`.
- **A cadeia do PRIORITIZE tem entidade, e a avaliação é imutável.** `PainPoint` (a dor, ancorada
  na **conta** como `Process`/`Evidence`/`Finding`) → `ImprovementOpportunity` (o agrupamento) →
  `PriorityAssessment` (o Opportunity Score) → `SolutionHypothesis` (as apostas concorrentes). Ver
  FDD 048 e ADR 0054. **`ImprovementOpportunity` não referencia `PipelineStage` em campo nenhum** —
  ela não é venda, e é por isso que o `language-map` §5 bane `Opportunity` sem qualificador; há
  teste sobre o `_meta` do modelo afirmando isso. Repriorizar **cria versão nova**: o viewset da
  avaliação não expõe `PUT`/`PATCH` (405, não 400), `version` sai do `save()` sob
  `select_for_update` da oportunidade (o motivo do `convert-to-project`), e os pesos são
  **copiados** de `priority.FORMULAS` para a linha — referenciar o catálogo faria uma edição de
  peso amanhã reescrever o score de ontem. **`rank` não é campo**: sai de
  `priority.ranking_da_conta`, um lugar só, porque um rank gravado que precisa concordar com a
  ordenação por score é uma segunda definição do mesmo fato. Sem avaliação, `score`/`rank`/
  `assessment_version` vêm `null` — nunca zero, pela regra do `nao_apurado`. `PainPoint` em
  `confirmed` exige achado vivo, e a invariante tem **três** metades: criação e `PATCH` no
  serializer (o M2M não existe no `clean()`), mais o 409 de `FindingViewSet.perform_destroy` ao
  arquivar o último achado — sem essa terceira ela vaza pelo `DELETE`.
- **Documents are single-linked.** A `Document` must reference exactly one of
  `account`/`commercial_opportunity`/project (enforced in `Document.clean()`); access is gated —
  never expose files to unauthorized users.
- **Journey artifacts have state.** `Artifact` (one model, `kind` =
  discovery/assessment/proposal/contract) holds the AI-generated text plus a state machine
  (`ARTIFACT_TRANSITIONS` in `models.py`), linked to exactly one of `commercial_opportunity`/project. The four
  AI actions create it in `draft` via `_ai_run(..., artifact_kind=...)`; `Document` stays the file
  and the e-sign target. Analytics exposes `funnel.by_stage` — see FDD 016 / ADR 0008.
- **Evidência e achado são duas coisas, e o `Discovery` diz de quando.** `Evidencia` (FDD 039)
  guardava três coisas numa linha só — forma da fonte, afirmação interpretada e rótulo
  epistemológico —, então a hipótese e o trecho que a sustenta eram o mesmo registro. Desde a
  FDD 045 (ADR 0049) o par é `Evidence` (o bruto: `raw_excerpt` **ou** `reference`, mais o
  `content_hash` que carimba o trecho) e `Finding` (a afirmação, com `epistemic_status` ∈
  `fact`/`hypothesis`/`unknown` e M2M para as evidências). **`fact` exige revisor humano e ao menos
  uma `Evidence` viva**: a metade do revisor está no `clean()`, a do M2M só cabe no serializer, e
  arquivar a última evidência viva de um fato é 409. `Discovery`/`DiscoverySession`/
  `ProcessObservation` dão tempo e autoria ao levantamento — é a `ProcessObservation` que desfaz a
  proveniência única de `Process.source_project`, permitindo o mesmo processo em dois Discoveries.
  **O dual-write acabou na Fase 6 (ADR 0052, issue #70), e a `Evidencia` legada foi removida**:
  `MeetingViewSet.estruturar` grava só o par do split, `process.custo_do_estado_atual` lê o
  `Finding(fact)` vivo do processo (não mais `Evidencia(rotulo=fato)`), e `ProcessDetailPage` lista
  e promove pelo split. A consequência é a que o split existe para produzir: promover um `Finding` a
  fato — ato que exige revisor e evidência viva — passa a mover a sustentação, porque agora é o mesmo
  registro que a tela promove e que o custo consulta (regressão em
  `test_o_fato_do_split_sustenta_o_custo.py`). Como `Evidence`/`Finding` são ancorados na **conta**
  (`process` é `SET_NULL`, não filho como a `Evidencia` `CASCADE` era), **arquivar o processo não
  arquiva os achados** — eles seguem listáveis pela conta. `legacy_evidencia` e o comando
  `reconciliar_evidence_finding` saíram junto; a reconciliação (`manage.py reconciliar_evidence_finding`,
  "todo legado tem par") é o gate de pré-deploy que a migração `0068` registra, não código que
  sobrevive ao corte.
- **O snapshot do portal fala canônico, e quem carimba a projeção é quem muda o estado.**
  `portal.build_snapshot` é projeção de leitura do One, e o One **nunca renomeia** (`language-map`
  §3): por isso ele leva `account` (de `engagement.account`), `engagement`, e
  `canonical_stage`/`requires_gate`/`gate_decision` em
  cada fase. `gate_decision` era lido de uma **propriedade** de `ProjectPhase`, para o nome legado
  não se espalhar; desde a #67 é o nome do próprio campo, e a chave emitida nunca mudou — que era
  o ponto do alias. `client` fica como alias até a `/api/v2/`; `situation` e `waiting_party` **não**
  atravessam — são classificação interna de delivery. O carimbo `observed_at`/`projection_version`
  é escrito em `portal.emit` (`F()+1`, **antes** da guarda de flag), nunca no `build_snapshot`:
  a rota é um `GET`, e incrementar na leitura produziria versões fora de ordem — o sinal exato que
  o comparador do outro lado usa para descartar o obsoleto. Duas leituras seguidas devolvendo a
  mesma versão é o caso comum, não sintoma. Desde a FDD 050 ele leva também a cadeia de medição:
  `kpis[]` com `baseline`/`outcome`/`monitoring` **aninhados dentro do indicador** — porque é o KPI
  que fixa unidade e método, e aninhar torna o pareamento invariante por construção — e
  `value_ledger[]` lido **por mandato**, só `approved` e só com `attribution_method`; `outcome` sem
  baseline do mesmo KPI **não sai**, `null` e `{"value": null}` são lacunas diferentes e nenhuma é
  zero, e `roi` mais os quatro campos legados de `digital_employees` continuam onde estão. Desde a
  FDD 051 ele leva também o **Discovery como dado** — `processes[]`, `findings[]`, `pain_points[]` e
  `improvement_opportunities[]`, os quatro de escopo **conta** (o mesmo bloco sai em todo projeto
  dela, e o One deduplica por id) —, e ali a regra é outra: **nada atravessa sem a marca de
  publicável** (`published_at`/`published_by`, ADR 0060), que é o ato de revisão humana da regra 1
  da §3 e por isso tem autor, é action e exige sustentação publicada embaixo. São **cinco** modelos
  marcados e **não há exceção**: o AS-IS entrou junto, porque "o AS-IS *validado*" da §3 era um
  qualificador tão sem lastro no schema quanto "revisada e publicável" — e `ProcessStep.erro`/
  `.retrabalho` são a caracterização da casa sobre onde o time do cliente erra. `ProcessStep` não
  tem marca própria (anda com o pai), e o `Process` é **âncora**: publicar `Finding`/`PainPoint`
  exige o mapa citado publicado e vivo, despublicá-lo ou arquivá-lo é 409 enquanto algo publicado
  o citar, e **mover a âncora por baixo de um registro publicado é 400** — senão `process_id`
  aponta para fora de `processes[]`. São **cinco** portas, e a quinta é a única que não passa
  perto de `published_at`: quem responde às três perguntas é `publication.py`, num lugar só.
  **Publicar deixou de ser só chamada de API na FDD 052**: a superfície é `/contas/:id/publicacao`
  (selo de leitura na `ProcessDetailPage`, porta no detalhe da conta), e a regra que não pode se
  perder ali é a ADR 0063 — o estado sai nos cinco serializers como `publication_state`, **com a
  frase junto**, e a frase de recusa é a de `publication.py`; um mapa chave→rótulo em TypeScript
  seria a segunda definição da copy que o 400 e o 409 já usam. Nunca
  cruzam `raw_excerpt`, `content_hash`, os nove insumos do custo, `rationale`/`weights`/`formula_key`,
  `assumptions`, e **nem `rank`** — ele ordena as oportunidades **não publicadas** junto, e
  recalculá-lo entre as publicadas seria a segunda definição que a ADR 0054 recusou; quem responde é
  `score`. Ver FDD 047, FDD 050, FDD 051, ADR 0051, ADR 0060 e as emendas de 28/08 e 01/09 na
  ADR 0003.
- **A medição saiu do ativo de solução, e "antes" e "depois" são o mesmo KPI em dois momentos.**
  `kpi_baseline` e `kpi_current` eram colunas de `DigitalEmployee`; desde a ADR 0055 (FDD 049) o
  indicador é `KPI` — do **projeto**, com `prove_experiment` opcional porque o KPI migrado não
  nasceu de experimento nenhum e inventar um seria histórico fabricado — e cada leitura é uma
  `Measurement` (`baseline`/`outcome`/`monitoring`). **`value` nulo é "não medido", nunca zero**, e
  a `Measurement` **não** tem `unit`: a ausência é a garantia de que o par comparado usa o mesmo
  KPI, a mesma unidade e o mesmo método (`language-map` §6.11) — acrescentá-la deixaria duas
  leituras divergirem em silêncio. `DigitalEmployee.kpi` **referencia**, não possui. As duas chaves
  continuam **saindo** na `/api/v1/`, derivadas (`prove.baseline_de`/`outcome_mais_recente_de`, um
  lugar só, lido também por `cases._metric`), e a **escrita** por elas parou — quebra deliberada
  aprovada pela decisão C1 do DAP `docs/design/dap-prove-e-valor-r1/`, registrada em
  `docs/ontology/aliases.md` §2d, com regressão afirmando a leitura.
- **O PROVE não começa sem KPI, critério de sucesso e Baseline — ou lacuna aprovada, assinada.**
  A invariante mora na action `POST /prove-experiments/{id}/start/` e **não** num `PATCH` de
  `status`, pela razão exata de `journey.apply_gate`: o que vale depende do estado corrente, e só
  ali ele é conhecido — 400 via `InvalidInput` listando **o que** falta, 409 via `StateConflict`
  para o que já começou. `gap_waiver` sem `gap_waiver_by` é 400: lacuna aprovada é ato com autor,
  como o trio de consentimento do `Case`. Quem diz o que falta é `prove.o_que_falta_para_iniciar`,
  função pura no molde de `priority.py`, que devolve **chaves e nunca frases** — os rótulos são da
  superfície — e é publicada em `missing_to_start` para a tela desenhar as pastilhas a partir dela.
  `FeasibilityAssessment` e `ProveExperiment` **reusam** `ProjectPhase.GateDecision` e
  `ProjectPhase.ProveDecision` (ADR 0053); redefinir as saídas seria a segunda definição do mesmo
  vocabulário. `ValueLedgerEntry` aponta para um `Measurement(kind=outcome)` com `PROTECT`, exige
  `attribution_method` não-vazio e carimba `approved_at` como o `published_at` do `Case` — são as
  invariantes §6.11 e §6.12, testáveis pela primeira vez. Ela pende de `Engagement` e **fica fora
  de `PROJECT_OF`** (o `project` é opcional, e o mandato não é fronteira de acesso): a visibilidade
  deriva de `Project.objects.visible_to`, como a do próprio `Engagement`.
- **A superfície da Fase 5 é governada pelo DAP `docs/design/dap-prove-e-valor-r1/`**, r1, decisões
  **A1 · B1 · C1 · D1 · E1** — mudar exige revisão nova do pacote, não julgamento na hora. Os dois
  painéis (**Technical Feasibility** e **PROVE**) ficam em `ProjectDetailPage`, logo abaixo da
  Jornada, e existem **só onde a fase canônica existe**: um projeto de Discovery Sprint não mostra
  painel de PROVE. A linha do KPI é `Baseline → Outcome · variação`, com o histórico num
  `<details>`, e **a lacuna é `—`, nunca `0`** — inclusive quando a baseline é zero, de onde não se
  calcula variação. As três pastilhas `Pronto`/`Falta` saem de `missing_to_start`, e **a tela nunca
  reexpressa a invariante**: recalculá-la habilitaria o botão de um `POST` que o servidor nega, sem
  nada ficar vermelho. A decisão de gate aparece **como decisão, ao lado do resultado**
  (`language-map` §6.3), com o `GATE_DECISION_LABEL`/`gateVariant` que a Jornada já usa — nunca um
  mapa novo. O formulário do Time Digital **perdeu** "Antes (base)" e "Depois (atual)" (C1) e o
  painel passou a só ler o KPI referenciado. O Value Ledger é a tela `/contas/:id/valor`, simétrica
  a `/contas/:id/priorizacao`, **fora do menu lateral** e lida **por mandato** (uma chamada por
  `Engagement`; sem filtro, a rota traria o consolidado entre contas que o DAP reservou). Ficam
  reservados no pacote: gráfico de série do KPI, `Case` derivado de Outcomes e ledger consolidado.
- **Os renomes da ontologia estão em curso, e "renome" são três coisas com prazos distintos**
  (ADR 0052, issue #67). O nome da **classe** — e de tudo que a nomeia: serializer, viewset,
  `resource`, campo FK, tipo TS — mudou na #67, uma fatia por PR. O nome da **tabela** ficou para
  a Fase 6: na #67 cada renome carregava `Meta.db_table` fixado no nome legado, e a migração era
  `AlterModelTable` **antes** de `RenameModel`, nessa ordem, para as duas serem no-op no banco
  (`alter_db_table` abre com `if old_db_table == new_db_table: return`). A **Fase 6 pagou as
  tabelas** (migração `0069`): os pins saíram do `Meta`, e `AlterModelTable(table=None)` renomeou
  cada uma em lugar (`core_client`→`core_account`, etc.), preservando linha e pk. A **rota** e a
  **chave de payload** ficam para a
  `/api/v2/`: a chave legada continua saindo no `GET` (campo com `source=`, `read_only`) e sendo
  aceita no `POST`/`PATCH` (`AliasDeEntradaMixin`, um mecanismo para todas), e **a canônica vence
  quando as duas vêm no mesmo corpo**. Todo alias de escrita precisa de regressão, porque a SPA
  escreve o nome canônico: sem ela a linha do serializer não tem chamador aqui dentro, e a próxima
  varredura atrás do nome antigo a remove achando que paga dívida — quebrando a `/api/v1/` sem
  nada ficar vermelho. **A #67 fechou**, com os quatro renomes pagos: `GateOutcome`→`GateDecision`,
  `Opportunity`→`CommercialOpportunity`, `Client`→`Account` (fatia 2, migração `0062`, com os dez
  campos FK virando `account` e `Client.status` virando `Account.lifecycle_status`) e
  `Processo`/`ProcessoEtapa`→`Process`/`ProcessStep` (fatia 4, migração `0063`, com
  `ProcessStep.processo` e `Evidencia.processo`/`etapa` virando `process`/`step`, e o módulo
  `processos.py` virando `process.py`). `Evidencia` **não** foi renomeada: ela era a metade legada do
  split, e a **Fase 6 (issue #70, migração `0068`) a removeu** com o dual-write, em vez de renomeá-la
  — trocar o nome sem dividir preservaria o defeito de linguagem que a divisão corrige. As
  **tabelas** dos quatro renomes saíram na Fase 6 (migração `0069`, renome em lugar).
  `Project.client` (migração `0070`), `ai_opportunity`→`ai_potential` (migração `0071`) e
  `client_consent`→`account_consent` (migração `0072`) também saíram na Fase 6; sobram as rotas
  e chaves de payload (`/api/v2/`, que agora pode nascer). O que a guarda ainda tolera está em
  `docs/ontology/legacy-allowlist.txt` (teto **23**), e o prazo de cada alias, em
  `docs/ontology/aliases.md` (§2b as seis pks, §2c campo vs. chave).
- **O `Engagement` tem superfície, e ela mora no detalhe da conta.** A seção "Engagements" de
  `AccountDetailPage` (entre "Saúde da relação" e "Satisfação") é governada pelo DAP
  `docs/design/dap-engagement-r1/`, r1, decisões **A1** (título em inglês, copy em volta em pt-BR)
  e **B1** (as duas pílulas de `commercial_model` sempre visíveis) — mudar a superfície exige
  revisão nova do pacote, não julgamento na hora. `projects_count` é **recortado por
  `project_scope_q`**, não é o total do mandato: dois usuários veem números diferentes para a mesma
  linha, e é o mesmo comportamento de `/clients/overview/`. Ver a emenda de 28/08 na FDD 046.
- **Pipeline invariants.** DB constraints enforce at most one "won" and one "lost"
  `PipelineStage`, and at most one active `Service` per product `tier`. DRF derives the
  serializer validation from these constraints — don't hand-roll a duplicate check.

**Auth model:** session cookies + CSRF (not tokens). DRF uses
`SessionAuthentication` and defaults to `IsAuthenticated`. The frontend (`src/api.ts`)
fetches a CSRF token from `/api/v1/auth/csrf/` before any mutating request, sends
`credentials: "include"`, and manages the session via `src/auth.tsx` (`AuthProvider`).
`config/settings.py` reads `DATABASE_URL` (Postgres) and falls back to SQLite when
unset; email goes through SMTP (Mailpit in dev).

**Frontend structure:** thin SPA — `src/api.ts` is the single API client, `src/pages/*`
are the screens (Login, Dashboard, Accounts, Commercial, Projects), `src/components/Layout.tsx`
is the shell, `src/types.ts` holds shared types.

**O design system é compartilhado com o portal do cliente, e a skill que o descreve é
`portal-design`** (ADR 0024, revista pela ADR 0025). A regra que carrega tudo: **a forma é a mesma
nos dois portais; o que identifica é só o matiz** — roxo `#6e56cf` é o portal do cliente, clay
`#bd4a30` é este. Nunca use um no outro.

A paleta é **branco, preto e laranja**: `ink` (texto, títulos, botão primário), `canvas` (fundo
quase-branco), a escala `brand-50…900` (o clay, usado com parcimônia) e `danger` (vermelho de
verdade, separado do acento desde a ADR 0024), mais `line` e `muted`. Dois tokens da escala
existem por medição e não por completude: `brand-200` é **o único acento que sobrevive a fundo
escuro** (`brand-500` cru sobre `ink` dá 3,82:1 e reprova), e **não há `brand-300`** porque o
único consumidor dele lá é um componente que este produto não tem. `accent` e `accent-50`
continuam valendo como **apelidos** em `@theme inline`, para os 13 arquivos que ainda os usam
inline — em código novo escreva `brand-*`. Eram quatro: `accent-200` e `accent-700` saíram por
nunca terem tido um consumidor, que é a mesma dívida de uma classe sem chamador.

O shell é o do portal do cliente: **barra lateral clara**, fixa, com o menu rolando por dentro
(`.sidebar`, `.brand-row`, `.nav-label`, `.nav-scroll`), e topbar com `.breadcrumb`
derivado do mesmo array `links` que desenha o menu. `.nav-item` tem **uma pele só** desde a ADR
0025 — a barra clara fez a `.nav-item--light` da gaveta mobile deixar de ter o que modificar. A
única superfície escura do produto é o painel do login (`.auth-brand`), e o gradiente dele vai de
`brand-900` ao `ink` **porque a direção do portal do cliente reprova aqui** (o eyebrow em
`brand-200` dá 2,28:1 sobre `brand-600`).

**O produto se apresenta como `Pulse` no shell; Biahflow é a casa** (ADR 0043, DAP GH-26 r1). A
marca é o asset canônico (`src/assets/brand/pulse-mark.svg`) consumido pelo componente
`PulseBrand` — **nunca SVG colado inline**, que é o que `assets/brand/README.md` proíbe. Sidebar,
gaveta mobile e raiz do `.breadcrumb` dizem Pulse; Biahflow fica no subtítulo do sidebar
("Operação Biahflow"), no eyebrow e no rodapé do login e na copy de acesso. Superfície escura usa
`pulse-mark-inverse.svg` (`tone="dark"`): o clay sobre `brand-900` dá **2,45:1** e o mark some, e o
axe não pegaria — o mark é decorativo e `color-contrast` mede texto. `.brand-mark` (o glifo `B` em
CSS, com a única sombra colorida do produto) saiu junto, por perder o último consumidor.

O shell **consome** as fundações r2 desde a ADR 0043, em vez de só declará-las: raio de controle
(8px) em `.nav-item`, `.icon-button`, `.user-button`, `.metric-icon` e `field`; raio de cartão
(12px) em `.panel`, `.popover`, `.metric-card` e no cartão do login; papéis tipográficos
(`--text-title`/`-body`/`-label`/`-meta`, com as classes `.type-*`) no lugar de pixel cravado. Duas
exceções ficam declaradas: `.icon-button` mantém `size-10` por WCAG 2.5.8 (`e2e/responsive.spec.ts`
mede) e `.filter-chip` segue `rounded-full`, reservado no DAP para quando Leads e Clientes entrarem
em escopo.

Tudo em `src/index.css`, junto de uma `@layer components` com `.panel`/`.panel--flush`/`.row`,
`.eyebrow`, `.page-head`, `.metric-card` (+ `--dark`), `.metric-icon` (+ `--danger`, `--dark`),
`.user-button`, `.btn` (+ `--secondary`, `--secondary-danger`, `--danger`, `--icon`,
`--icon-danger`), `.form-label`, `.form-grid`, `.toolbar`, `.state` (`--0..3`
e `--off`, o **neutro**: "Desligada" e "Arquivado" não são aviso), `.filter-chip`, `.empty-state`,
`.alert--error`/`--ok`, `.back-link`, `.nav-item`, `.popover*` e `.avatar`.

**Toda classe daqui tem consumidor, e isso é uma invariante, não uma observação.** `.btn--ghost` e
`.card-grid` saíram por nunca terem tido nenhum; `.brand-mark` saiu por ter perdido o seu quando o
mark canônico entrou (ADR 0043) — nascer sem chamador e ficar sem chamador são a mesma dívida, e
ela vale igual para prop de componente. `.btn--danger` ficou porque tinha um que ninguém tinha
notado (o `ConfirmDialog`). Os dois botões de perigo dizem coisas diferentes e não se substituem:
`--danger` é vermelho sólido e só aparece na confirmação, quando a ação já foi pedida;
`--secondary-danger` é neutro em repouso e vermelho no hover, e é o `Arquivar` que divide a faixa
com o `Editar`.

**Use a primitiva; não reescreva o literal.** Isso é cobrado por `src/test/primitivas.test.ts`
(ADR 0026), guarda que varre `pages/` e `components/` e reprova o literal que já tem primitiva —
ela existe porque um card escrito à mão renderiza *quase* igual a um `.panel` e a divergência não
deixa nada vermelho, que foi como o produto chegou a 1.331 utilitários inline e adoção zero. A
allowlist dela nasceu **vazia** e a meta é que continue; exceção legítima entra com o motivo
escrito. Mapa de estado devolve **variante** (`"state--1"`), nunca a cor (`"bg-emerald-50 …"`) —
uma segunda definição de "concluído" diverge da primeira em silêncio.

A skill `biahflow-design` descreve o **OikOS** (`pine`/`clay`/`paper`) e
nunca casou com este produto; não a siga aqui. O anterior está em `docs/design/paleta-anterior.md`
e na tag `design/antes-do-redesenho`; o que foi portado de lá, em
`docs/design/referencia-portal-do-cliente.md`.

Toda mudança de cor passa por `e2e/a11y.spec.ts` — 24 telas × 3 larguras, contraste AA incluído.
**Quando o axe e o tom discordam, cede o tom.** Vale inclusive contra a fonte: copiar a forma
copia junto os defeitos de contraste dela, e foi assim que o `slate-400` do `.nav-label` do portal
do cliente reprovou 19 telas de uma vez ao chegar aqui.

## Conventions (from AGENTS.md / CONTRIBUTING.md)

- Read `PRD.md`, the relevant FDD (`docs/fdd/`), and ADRs (`docs/adr/`) before changing
  behavior. Relevant features update their FDD; a durable technical decision needs an
  ADR; a cross-cutting or breaking change needs an RFC (`docs/rfcs/`).
- **Read [`docs/ontology/language-map.md`](docs/ontology/language-map.md) before naming anything
  new** — model, field, route, component, prop. It is normative: one concept, one name, four
  surfaces. §5 lists the banned terms and §6 the invariants; the aliases still alive and the phase
  each one dies in are in [`docs/ontology/aliases.md`](docs/ontology/aliases.md). The rule is
  enforced, not just written: `backend/tests/test_vocabulario.py` (ADR 0049) fails on a **new**
  declaration outside the canonical vocabulary, and the legacy debt it tolerates is listed line by
  line in `docs/ontology/legacy-allowlist.txt` — a file that only shrinks. Precedence: the Notion
  page wins on **meaning**, this mirror wins on the **label inside the repo**, and `CLAUDE.md` /
  `AGENTS.md` may point at it but never weaken it. The mirror is a faithful copy and is not edited
  here.
- **Preserve the `/api/v1/` contract.** Any breaking change must be deliberate and
  documented. `backend/openapi.yaml` and drf-spectacular (`/api/docs/`) describe it.
- Fix defects test-first: add a regression test in `backend/tests/regression/` (or the
  nearest suite) before the fix.
- Do not disable quality checks to finish a task. Don't hard-delete operational/business
  data without an explicit requirement — prefer soft delete.
