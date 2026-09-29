# SentinelKYC

SentinelKYC is a multi-tenant KYC/AML customer onboarding and sanctions
screening platform. See `PROJECT_PLAN.md` for the full product specification
and phase-by-phase build plan.

## Current status

This repository currently implements **Phase 1: Sanctions Data ETL Pipeline**,
**Phase 2: Database Schema and Data Layer**, **Phase 3: Screening Engine**,
**Phase 4: Authentication, Authorization and Data Security**, and
**Phase 5: Onboarding Workflow, Document Verification and Case Management**,
plus the minimum Phase 0 foundations needed to run them.

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

Not yet implemented (see PROJECT_PLAN.md for scope): LLM-assisted case
summaries (Phase 6), the public website and compliance console
(Phases 7-8), and the analytics dashboards (Phase 9).

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/) for dependency management
- Docker and Docker Compose

## Quick start

```
make setup     # uv sync --extra dev
make up        # start Postgres (and, once built, Dagster) via Docker Compose
make migrate   # apply Alembic migrations
make seed      # run the sanctions ingestion pipeline
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
