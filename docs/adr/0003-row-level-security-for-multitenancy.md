# ADR 0003: PostgreSQL Row-Level Security for multi-tenancy

## Status

Accepted

## Context

SentinelKYC is multi-tenant: each financial institution's customers,
applications, cases and audit history must be strictly isolated from every
other tenant. The isolation could be enforced entirely in the application
layer (every query manually filtered by `tenant_id`) or pushed down into the
database with Row-Level Security (RLS).

## Decision

Every tenant-owned table carries a `tenant_id` column. RLS is enabled and
forced on each of these tables, with a policy keyed on
`current_setting('app.tenant_id')`:

```sql
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON customers
  USING (tenant_id = current_setting('app.tenant_id', true)::integer)
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::integer);
```

The API sets `app.tenant_id` once per request (Phase 4), from the
authenticated user's tenant claim, before running any query for that request.

## Rationale

- Application-layer filtering is one missed `WHERE tenant_id = :tenant_id`
  clause away from a cross-tenant data leak, and that mistake is invisible in
  code review because the query still looks correct. RLS makes the isolation
  a database invariant instead of a per-query discipline.
- `FORCE ROW LEVEL SECURITY` matters specifically because the application's
  database role should not be a superuser or table owner in production;
  without `FORCE`, a role that owns the tables bypasses RLS entirely. This
  was confirmed directly: the default `pgvector/pgvector:pg16` Docker role is
  a superuser and RLS silently does not apply to it, regardless of `FORCE`.
  The repository-layer test in `tests/integration/test_schema_migrations.py`
  therefore creates a dedicated `NOSUPERUSER NOBYPASSRLS` role to prove
  isolation actually holds for a realistic application role.
- Tables with a nullable `tenant_id` (platform-level users, risk config
  defaults, audit log entries not tied to a tenant) use a policy that also
  allows `tenant_id IS NULL`, so platform-scoped rows remain visible without a
  separate code path.
- Sanctions data (`sanctions_entities`, `sanctions_names`, etc.) is
  deliberately excluded: it is not tenant-owned, it is shared reference data
  ingested once and screened against by every tenant.

## Consequences

- Every request-handling code path must set `app.tenant_id` before querying;
  forgetting to do so makes all tenant-owned rows invisible (fails closed,
  not open) rather than leaking data, which is the safer failure mode.
- Bulk/background jobs that operate across tenants (the sanctions ingestion
  pipeline, analytics refresh) must run as a role that either sets
  `app.tenant_id` per tenant in a loop or uses a role with `BYPASSRLS`
  reserved for that specific, audited purpose.
- Migrations that add new tenant-owned tables must remember to add the RLS
  policy; there is no automatic enforcement of this convention yet.
