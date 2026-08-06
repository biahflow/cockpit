# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Portal Biahflow is an internal tool that carries a commercial opportunity from sale
through to project execution. Backend is Django + DRF (Python 3.12) serving a versioned
`/api/v1/` API; frontend is a React + Vite + TypeScript SPA styled with Tailwind v4.
The product spec, scope, and roadmap live in `PRD.md` and `roadmap.md`; most project
documentation is in Portuguese (pt-BR).

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

Before opening a PR, the expected gates are: backend `pytest` + `mypy`, and frontend
`test`, `build`, and `e2e` (see `README.md` / `docs/runbooks/`).

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
- **Product tiers live on `Service`.** A `Service` with a `tier`
  (`discovery_express`/`discovery_assessment`/`implantacao`) is one of the three product
  levels, seeded by migration `0020`; a blank `tier` is a loose catalog entry. The tier
  drives the kickoff template (`kickoff.KICKOFF_TEMPLATES`), the proposal prompt context
  (`ai.build_opportunity_context`) and the `by_tier` funnel in analytics — see FDD 015.
- **Documents are single-linked.** A `Document` must reference exactly one of
  client/opportunity/project (enforced in `Document.clean()`); access is gated —
  never expose files to unauthorized users.
- **Journey artifacts have state.** `Artifact` (one model, `kind` =
  discovery/assessment/proposal/contract) holds the AI-generated text plus a state machine
  (`ARTIFACT_TRANSITIONS` in `models.py`), linked to exactly one of opportunity/project. The four
  AI actions create it in `draft` via `_ai_run(..., artifact_kind=...)`; `Document` stays the file
  and the e-sign target. Analytics exposes `funnel.by_stage` — see FDD 016 / ADR 0008.
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
is the shell, `src/types.ts` holds shared types. There is a Biahflow/OikOS design system;
use the `biahflow-design` skill when building or restyling UI.

## Conventions (from AGENTS.md / CONTRIBUTING.md)

- Read `PRD.md`, the relevant FDD (`docs/fdd/`), and ADRs (`docs/adr/`) before changing
  behavior. Relevant features update their FDD; a durable technical decision needs an
  ADR; a cross-cutting or breaking change needs an RFC (`docs/rfcs/`).
- **Preserve the `/api/v1/` contract.** Any breaking change must be deliberate and
  documented. `backend/openapi.yaml` and drf-spectacular (`/api/docs/`) describe it.
- Fix defects test-first: add a regression test in `backend/tests/regression/` (or the
  nearest suite) before the fix.
- Do not disable quality checks to finish a task. Don't hard-delete operational/business
  data without an explicit requirement — prefer soft delete.
