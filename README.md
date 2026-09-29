# SentinelKYC

SentinelKYC is a multi-tenant KYC/AML customer onboarding and sanctions
screening platform. See `PROJECT_PLAN.md` for the full product specification
and phase-by-phase build plan.

## Current status

This repository currently implements **Phase 1: Sanctions Data ETL Pipeline**,
**Phase 2: Database Schema and Data Layer**, **Phase 3: Screening Engine**,
**Phase 4: Authentication, Authorization and Data Security**,
**Phase 5: Onboarding Workflow, Document Verification and Case Management**,
**Phase 6: LLM Integration Layer with Minimum Token Usage**, a scoped build
of **Phase 7: Public Corporate Website**, a scoped build of **Phase 8:
Compliance Console and Applicant Portal**, and a scoped build of **Phase 9:
Revenue and Analytics Dashboard**, plus the minimum Phase 0 foundations
needed to run them.

Phase 9 (`backend/app/services/analytics/`, `frontend/src/pages/console/
Analytics.tsx`): an Operations/Compliance analytics view only - the Revenue
dashboard (PROJECT_PLAN.md 9.3) needs 24 months of fabricated subscription
and invoice history that doesn't exist in this build, so it was scoped out
in favor of metrics computed from data the system already produces. Five
pre-aggregated endpoints under `/api/v1/analytics/*`
(`funnel`/`routing`/`screening-volume`/`sla`/`llm-usage`, gated by the
existing `analytics:view_tenant` permission) back five ECharts widgets on a
new `/app/analytics` console page: an applications funnel read from the
audit trail (submitted -> docs verified -> screened -> decided, since an
RFI can send an application back to SUBMITTED so *current* state alone
would undercount), daily screening volume, case-tier routing distribution
(a bar chart standing in for the full Sankey in 9.4), SLA compliance
(mirrors `case_service.sla_breached()`'s exact rule), and LLM usage by
provider/outcome with a cache-hit-rate figure (Phase 6's `llm_calls` table).
ECharts is imported via its tree-shakeable core (not the full bundle) and
the whole Analytics page is route-level code-split, so the ~530 kB chart
library is only downloaded by someone who opens that page. All five
endpoints were smoke-tested against the real Postgres-backed API. Out of
scope for this build: the Revenue dashboard entirely (9.3), the Sankey/
choropleth/cohort-heatmap/box-plot chart types, and global filters/date-
range comparison (9.2).

Phase 8 (`frontend/src/pages/console/`, `lib/api.ts`, `lib/auth.tsx`): the
console shell (sidebar/topbar layout, protected routes) and the reviewer's
core workflow, wired to the real backend rather than mock data - the
existing `/login` page now calls `POST /api/v1/auth/login` for real
(including the MFA step), a Review Queue lists and filters
`GET /api/v1/cases` by tier with pagination, and a Case Detail page covers
assignment, per-hit disposition, the decision panel (with a "Draft
rationale" button hitting the Phase 6 LLM endpoint), RFI, notes, PDF export,
and a lazily-loaded case summary card. No TanStack Query/Table - a lean,
hand-rolled fetch client instead. `CORSMiddleware` was added to the FastAPI
app (`backend/app/main.py`) so the Vite dev server can call the API; the
full login-with-MFA-through-case-list flow was smoke-tested against the
real Postgres-backed API rather than left unverified. Out of scope for this
build (see PROJECT_PLAN.md 8.1-8.5): Administration, Sanctions Lists,
Rescreening, ad-hoc/CSV Screening and Audit Log console pages, the
document viewer with OCR overlay and side-by-side hit comparison, bulk
hit-clearing UI, and the applicant self-service portal wizard (`/onboard`).

Phase 7 (`frontend/`, React 18 + Vite + TypeScript + Tailwind + shadcn/ui-
style primitives + React Router + Framer Motion): the design system
(palette, type scale, `Button`/`Card`/`Badge`/`Accordion` primitives, light/
dark theming) and global layout (sticky header with mega-menu-lite nav,
footer, cookie consent banner) from PROJECT_PLAN.md 7.1-7.2, plus a working
subset of the page catalog in 7.3 chosen to demonstrate the design system
end to end rather than the full ~15-page catalog: Home (hero, trust bar,
live-stats band, pillars, workflow diagram, security section, testimonials,
CTA), Solutions (all four solution areas plus an FAQ accordion), Trust
Center, the split-panel Login flow with an MFA step, Contact, and legal/
404/forgot-password stubs so no nav link 404s. Out of scope for this build
(see PROJECT_PLAN.md 7.3-7.5 for the full spec): the Platform/Industries/
Resources/Company page groups, the 6 long-form Insights articles, the
downloaded-and-converted Unsplash/Pexels imagery pipeline (placeholder
gradient panels stand in for photography/screenshots), and Lighthouse/
Playwright visual regression tooling. `npm run build` and `npx tsc -b`
both pass cleanly.

Phase 6 additions (`backend/app/services/llm/`): the LLM never screens,
approves or rejects - it is only called lazily, to draft a case summary the
first time a reviewer opens a Review/High Risk case, or a decision rationale
when a reviewer clicks "Draft rationale". A provider router
(`router.py`) tries the configured primary (Groq `openai/gpt-oss-20b` or
Gemini Flash), respects a Redis-backed per-provider quota
(`quota.py`) and a 5-failure/60s circuit breaker, retries a transient
failure once, fails over to the other provider on 429/5xx/timeout, and falls
back to a deterministic template summary if both are unavailable - the
workflow never blocks on an LLM. Requests are pseudonymized before sending
(`pseudonymize.py`: DOB reduced to year, address to country, ID/contact
details dropped, internal IDs replaced by a case-scoped alias, top 3 hits
only); a response cache (`cache.py`, keyed by `sha256(purpose, prompt_version,
payload)`) means identical payloads never call a provider twice; every call
is logged to `llm_calls` regardless of outcome. Endpoints: `GET
/api/v1/cases/{id}/summary`, `POST /api/v1/cases/{id}/decision-rationale-
draft`, and `GET/POST /api/v1/llm/quota` and `/api/v1/llm/settings` for a
platform admin to view live quota headroom and switch the primary provider
or disable LLM features entirely.

Phase 5 additions: an applicant-facing state machine
(`backend/app/services/onboarding/state_machine.py`) with guarded
transitions, every one of which writes a `case_events` row and an audit
event; a synchronous document verification pipeline (MIME/size, blur and
glare via OpenCV, Haar-cascade face presence, Tesseract OCR, ICAO 9303 MRZ
parsing and checksum validation, and cross-referencing the MRZ against the
applicant's stated name/DOB/nationality); automatic screening and risk-tiered
routing into a case on `DOCS_VERIFIED`; case management (queue assignment,
SLA tracking, hit disposition, bulk-clear, four-eyes decisions, RFIs, notes,
PDF export); continuous rescreening when the sanctions list changes; and
REST endpoints under `/api/v1/portal/*`, `/api/v1/cases/*` and
`/api/v1/lists/*`. Fixing this phase's onboarding flow also surfaced and
fixed a real bug in Phase 4's audit chain: `audit_log`'s per-tenant Row-Level
Security silently broke the assumption that the hash chain was one global
sequence, so the chain is now verified and linked per tenant (see
`backend/app/core/security/audit.py`).

Phase 4 additions: Argon2id password hashing with a policy check against a
bundled common-password list; RS256 JWT access tokens; opaque refresh tokens
with rotation and reuse detection (a reused token revokes its whole family);
mandatory TOTP MFA for staff roles with hashed recovery codes; account
lockout with exponential backoff; RBAC seeded from the roles/permissions
tables plus ABAC helpers (same-tenant, four-eyes, case-assignment); AES-256-
GCM envelope encryption with per-tenant, versioned data keys; HMAC blind
indexes for exact lookups on encrypted columns; an append-only, hash-chained
audit log (a database trigger blocks UPDATE/DELETE even for a superuser);
strict security headers; PII-masking structured logging; Redis-backed rate
limiting; and a dedicated, non-superuser, RLS-respecting database role that
the running API connects as instead of the migration owner. Auth endpoints
are live under `/api/v1/auth/*`. See `docs/adr/0005-restricted-application-
database-role.md` for three real bugs this last change surfaced and fixed.

Implemented:

- A Dagster software-defined asset pipeline that ingests the real U.S.
  Treasury OFAC Specially Designated Nationals (SDN) list: conditional fetch,
  streaming XML parse, name normalization, multilingual embedding, and an
  upsert into Postgres with full change tracking.
- The sanctions domain database schema (`sanctions_entities`, `sanctions_names`
  with `pgvector` embeddings, `sanctions_identifiers`, `sanctions_dobs`,
  `sanctions_nationalities`, `sanctions_addresses`, `sanctions_list_versions`,
  `sanctions_changes`), with GIN token, trigram and HNSW vector indexes, plus
  a partial index on active entities.
- Asset checks (unique `uid`, no null primary names, row-count tolerance
  versus the previous version) and a freshness sensor.
- The full application schema across six domains: tenancy and billing
  (`tenants`, `plans`, `subscriptions`, `invoices`, `invoice_lines`,
  `usage_events`), identity and access (`users`, `roles`, `permissions`,
  `role_permissions`, `user_roles`, `refresh_tokens`, `mfa_factors`,
  `login_events`), onboarding (`customers` with encrypted-PII columns and a
  blind index, `applications`, `documents`, `document_checks`), screening
  (`screening_runs`, `screening_hits`), case management (`cases`,
  `case_events`, `case_notes`, `rfi_requests`), and governance (`risk_config`,
  `country_risk`, `audit_log`, `llm_calls`, `llm_cache`).
- Multi-tenancy: every tenant-owned table carries `tenant_id` and has
  PostgreSQL Row-Level Security enabled and forced, keyed on
  `current_setting('app.tenant_id')`.
- The screening engine: candidate blocking via three retrievers (GIN token
  overlap ranked by IDF, `pg_trgm` trigram similarity, HNSW vector nearest
  neighbor) plus a phonetic filter for short names; composite scoring
  (rapidfuzz token_set/token_sort/Jaro-Winkler blended with embedding cosine
  similarity, rare-token and secondary-attribute adjustments, a weak-AKA
  score cap); an independent customer risk score (country, occupation,
  transaction volume, entity opacity, document check outcome); and
  risk-tiered routing (Clear / Review / High Risk / Reject) with SLA and
  dual-approval rules. Exposed at `POST /api/v1/screening/search`.
- An evaluation harness (`backend/app/services/screening/evaluate.py`)
  measuring recall, precision, F1 and false positive rate per score
  threshold against a labelled ground truth set, with a precision-recall
  curve and a hybrid-vs-baseline comparison; see `docs/evaluation/report.md`.

Not yet implemented (see PROJECT_PLAN.md for scope): the rest of the public
website's page catalog and imagery pipeline (remainder of Phase 7), the
rest of the compliance console and the applicant portal wizard UI
(remainder of Phase 8), and the Revenue dashboard plus the richer Phase 9.4
chart types and global filters (remainder of Phase 9). Phase 10 (Testing
and Quality Assurance) and Phase 11 (Observability, Deployment and
Documentation) have not been started.

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/) for dependency management
- Node.js 20+ and npm (for `frontend/`)
- Docker and Docker Compose

## Quick start

```
make setup     # uv sync --extra dev; npm install in frontend/
make up        # start Postgres (and, once built, Dagster) via Docker Compose
make migrate   # apply Alembic migrations
make seed      # run the sanctions ingestion pipeline
make frontend-dev  # start the Vite dev server at localhost:5173
```

To explore the pipeline interactively:

```
uv run dagster dev -w pipelines/workspace.yaml
```

This opens the Dagster UI with asset lineage, run history and check results
for the `sanctions_ingestion` asset group.

To run the API:

```
uv run uvicorn backend.app.main:app --reload
```

Then `POST /api/v1/screening/search` with `{"full_name": "..."}` (optionally
`date_of_birth`, `nationality`, `id_number`, `entity_type`, `top_n`) returns
ranked, explained hits against the loaded sanctions list.

To regenerate the screening evaluation report:

```
uv run python dataset/scripts/generate_ground_truth.py
uv run python -m backend.app.services.screening.evaluate
```

This writes `docs/evaluation/report.md` and `docs/evaluation/pr_curve.png`.

## Environment variables

See `.env.example` for the full reference. Copy it to `.env` and adjust the
database credentials and `DAGSTER_HOME` for your machine; `DAGSTER_HOME` must
be an absolute path.

## Testing

```
make test        # unit tests (no external services required)
make e2e          # integration tests against a running Postgres instance
```

The integration test in `tests/integration/test_sdn_loader.py` requires the
`postgres` service from `docker-compose.yml` to be running with migrations
applied; it uses an isolated source name and cleans up after itself.

`tests/integration/test_schema_migrations.py` spins up its own disposable
Postgres container via testcontainers (Docker required, no running service
needed), applies every migration from scratch, exercises the core
tenant-user-customer-application-case relationships, and verifies Row-Level
Security actually isolates tenants under a non-superuser role.

## Dataset

See `dataset/README.md` for how the OFAC SDN list is fetched, refreshed and
attributed.

## Repository layout

```
backend/app/           # domain models, config, services and API shared by the app and pipelines
  models/sanctions.py   # sanctions list domain (Phase 1)
  models/tenancy.py     # tenants, plans, subscriptions, invoices, usage events
  models/identity.py    # users, roles, permissions, refresh tokens, MFA, login events
  models/onboarding.py  # customers (encrypted PII columns), applications, documents
  models/screening.py   # screening runs and hits
  models/cases.py       # case management: cases, events, notes, RFIs
  models/governance.py  # risk config, country risk, audit log, LLM usage and cache
  services/sanctions/   # OFAC XML parsing, DOB parsing, fetching, loading, rescreen hook
  services/screening/   # normalize, candidates, scoring, risk, routing, evaluate
  api/v1/                # FastAPI routers (screening search)
  main.py                 # FastAPI application entry point
backend/alembic/        # database migrations
pipelines/               # Dagster code location (sanctions ingestion assets, schedules, sensors)
dataset/                  # data sources, scripts, and attribution
docs/adr/                 # architecture decision records
docs/evaluation/           # screening evaluation report and precision-recall curve
infra/                     # Docker and Dagster infrastructure config
```

## Disclaimer

This is a demonstration environment. All customer, client and financial
records referenced in later phases are synthetic. Sanctions data is sourced
from the U.S. Department of the Treasury. This project is not legal advice.
