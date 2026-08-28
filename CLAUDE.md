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

Core domain flow (`apps/core/models.py`): `Client` → `Contact`, `Opportunity` (on a
configurable `PipelineStage`) → converts into a `Project` → `Milestone`/`Task`
(both subclass the abstract `WorkItem`) plus `Document`. `User` extends
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
  (e.g. `resource = "client"`), plus per-object `has_object_permission`, which
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
- **Opportunity → Project conversion** is the central business action: the
  `convert-to-project` `@action` on `OpportunityViewSet`. It requires the opportunity
  be in the "won" stage, enforces sales/admin role, and uses a `OneToOneField`
  (`Project.opportunity`) + `transaction.atomic` + `IntegrityError` handling to
  guarantee a won opportunity converts exactly once without duplicating the client.
  It also carries `Opportunity.service` over to `Project.service` (payload wins).
- **Product tiers live on `Service`, and they are the FDE ladder.** A `Service` with a `tier`
  (`qualification_call`/`discovery_assessment`/`discovery_sprint`/`feasibility`/`prove`/`scale`/
  `transformation`) is one sellable step, seeded by migrations `0020` and `0050`; a blank `tier`
  is a loose catalog entry. The tier drives the kickoff template (`kickoff.KICKOFF_TEMPLATES`),
  the invoice schedule (`invoices.INVOICE_SCHEDULES`), the proposal prompt context
  (`ai.build_opportunity_context`) and the `by_tier` funnel in analytics — see FDD 015, ADR 0048.
  **Free is the step, not the zero price** (`frontend/src/tiers.ts`): only the Qualification Call
  is free; zero anywhere else means "price to be decided" — the Transformation Partnership is
  monthly recurring and the catalog still cannot represent recurrence.
- **Documents are single-linked.** A `Document` must reference exactly one of
  client/opportunity/project (enforced in `Document.clean()`); access is gated —
  never expose files to unauthorized users.
- **Journey artifacts have state.** `Artifact` (one model, `kind` =
  discovery/assessment/proposal/contract) holds the AI-generated text plus a state machine
  (`ARTIFACT_TRANSITIONS` in `models.py`), linked to exactly one of opportunity/project. The four
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
  proveniência única de `Processo.source_project`, permitindo o mesmo processo em dois Discoveries.
  **O dual-write é obrigatório enquanto durar esta fase**: `MeetingViewSet.estruturar` grava
  `Evidencia` **e** o par novo, porque `processos.custo_do_estado_atual` e `ProcessoDetailPage`
  ainda leem o legado — há regressão afirmando que promover um `Finding` não move o custo. Campos
  com nome canônico (`account`, `process`, `step`) apontam para os modelos legados; o renome físico
  é fase posterior, e `legacy_evidencia` é o escape de mapeamento do backfill (migração `0054`).
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
are the screens (Login, Dashboard, Clients, Commercial, Projects), `src/components/Layout.tsx`
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
