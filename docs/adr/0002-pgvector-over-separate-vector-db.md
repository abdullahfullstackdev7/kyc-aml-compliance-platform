# ADR 0002: pgvector over a separate vector database

## Status

Accepted

## Context

Name matching uses multilingual sentence embeddings for semantic candidate
retrieval alongside token and trigram matching. A dedicated vector database
(for example Qdrant or Milvus) or Postgres with the `pgvector` extension were
both viable, free options.

## Decision

Store embeddings in Postgres using `pgvector`, with an HNSW index
(`vector_cosine_ops`, m=16, ef_construction=64) on `sanctions_names.embedding`.

## Rationale

- Token (GIN), trigram (`pg_trgm`) and vector retrieval all read from the same
  `sanctions_names` table in a single query plan, avoiding a cross-database
  join between a relational store and a separate vector store.
- One transactional store means the `sdn_loaded` asset can upsert entities,
  names and embeddings atomically; a separate vector database would need a
  two-phase write with its own consistency handling.
- Operational simplicity: one database to back up, secure with Row-Level
  Security, and run in Docker Compose, consistent with the free/open-source
  constraint in PROJECT_PLAN.md section 3.5.
- At the SDN list's scale (order of 40,000 names), HNSW in pgvector meets the
  Phase 3 performance targets (p95 under 300 ms) without a specialized engine.

## Consequences

- Embedding dimensionality is fixed at build time (384, matching
  `intfloat/multilingual-e5-small`); changing embedding models requires a
  migration to resize the `vector` column and re-encode all names.
- Vector index maintenance (HNSW build cost on bulk load) is Postgres's
  responsibility rather than a purpose-built vector engine's.
