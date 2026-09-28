# ADR 0001: Dagster over Airflow for sanctions ETL orchestration

## Status

Accepted

## Context

The platform needs a scheduled, versioned pipeline to ingest the OFAC SDN list,
detect deltas, and trigger downstream rescreening. Candidates considered were
Apache Airflow and Dagster, both free and open source.

## Decision

Use Dagster with software-defined assets.

## Rationale

- Software-defined assets map directly onto the pipeline's actual data products
  (raw XML, parsed entries, normalized names, embeddings, loaded rows, deltas),
  making lineage and staleness visible without extra bookkeeping.
- Built-in asset checks provide the row-count tolerance, null-name and
  unique-uid guards required by Phase 1 without a separate testing harness.
- Local development does not require a scheduler process; assets can be
  materialized directly from the CLI or Python API, which keeps the developer
  loop fast.
- Airflow's DAG-of-tasks model would require bolting on separate versioning and
  lineage tracking to get the same asset-centric guarantees.

## Consequences

- The team standardizes on Dagster's resource and IO manager patterns for all
  future pipelines (customer rescreening, analytics refresh).
- Operators need to learn Dagster's asset-check and sensor APIs, which differ
  from Airflow's operator model.
