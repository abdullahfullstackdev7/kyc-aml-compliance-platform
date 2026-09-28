# SentinelKYC

SentinelKYC is a multi-tenant KYC/AML customer onboarding and sanctions
screening platform. See `PROJECT_PLAN.md` for the full product specification
and phase-by-phase build plan.

## Current status

This repository currently implements **Phase 1: Sanctions Data ETL Pipeline**,
plus the minimum Phase 0 foundations needed to run it (monorepo layout,
dependency management, Docker Compose for Postgres, Alembic migrations).

Implemented:

- A Dagster software-defined asset pipeline that ingests the real U.S.
  Treasury OFAC Specially Designated Nationals (SDN) list: conditional fetch,
  streaming XML parse, name normalization, multilingual embedding, and an
  upsert into Postgres with full change tracking.
- The sanctions domain database schema (`sanctions_entities`, `sanctions_names`
  with `pgvector` embeddings, `sanctions_identifiers`, `sanctions_dobs`,
  `sanctions_nationalities`, `sanctions_addresses`, `sanctions_list_versions`,
  `sanctions_changes`), with GIN token, trigram and HNSW vector indexes.
- Asset checks (unique `uid`, no null primary names, row-count tolerance
  versus the previous version) and a freshness sensor.

Not yet implemented (see PROJECT_PLAN.md for scope): the screening/matching
engine (Phase 3), authentication and authorization (Phase 4), the onboarding
workflow and case management (Phase 5), LLM-assisted case summaries (Phase 6),
the public website and compliance console (Phases 7-8), and the analytics
dashboards (Phase 9).

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

## Dataset

See `dataset/README.md` for how the OFAC SDN list is fetched, refreshed and
attributed.

## Repository layout

```
backend/app/          # domain models, config, and services shared by the API and pipelines
  models/sanctions.py  # SQLAlchemy models for the sanctions domain
  services/sanctions/  # OFAC XML parsing, DOB parsing, fetching, loading, rescreen hook
  services/screening/  # name normalization shared by list ingestion and future matching
backend/alembic/       # database migrations
pipelines/              # Dagster code location (sanctions ingestion assets, schedules, sensors)
dataset/                 # data sources, scripts, and attribution
docs/adr/                # architecture decision records
infra/                    # Docker and Dagster infrastructure config
```

## Disclaimer

This is a demonstration environment. All customer, client and financial
records referenced in later phases are synthetic. Sanctions data is sourced
from the U.S. Department of the Treasury. This project is not legal advice.
