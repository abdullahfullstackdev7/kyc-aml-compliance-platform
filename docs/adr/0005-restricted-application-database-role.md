# ADR 0005: The running application never connects as the migration role

## Status

Accepted

## Context

Every earlier phase ran the API, the Dagster pipelines and Alembic migrations
against the same Postgres role (`sentinelkyc`, the Docker image's default
superuser). Phase 2 enabled and forced Row-Level Security on every
tenant-owned table, but RLS has no effect on a superuser or on any role with
`BYPASSRLS`, regardless of `FORCE ROW LEVEL SECURITY` (documented in ADR
0003, discovered directly: the RLS test in `test_schema_migrations.py` had to
create a dedicated non-superuser role to observe isolation actually holding).
Phase 4 also requires `audit_log` to be genuinely append-only, which is
meaningless if the connection writing to it can grant itself UPDATE/DELETE.

## Decision

Migration 0004 creates a second Postgres role, `sentinelkyc_app`
(`NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`), and grants it ordinary
CRUD on the application's tables but only `SELECT, INSERT` on `audit_log`.
`backend/app/api/deps.py` connects the running API to `app_sync_database_url()`
(this role), never `sync_database_url()` (the migration-owner role Alembic
and the Dagster pipelines still use).

## Rationale

- This is the only configuration under which the RLS policies from Phase 2
  and the append-only trigger from Phase 4.4 actually constrain anything.
  Running the app as a role that can bypass both would make every prior
  isolation guarantee decorative.
- Keeping migrations on the superuser role and the app on the restricted role
  mirrors how this separation works in production: schema changes are an
  operator action, not something the running service can do to itself.

## Consequences: three bugs this surfaced, in order

Switching the app's connection was not a one-line change; it broke three
things, each fixed in this phase rather than deferred:

1. **Login itself was unreachable.** `users`, `refresh_tokens`,
   `mfa_factors` and `login_events` all carry a nullable `tenant_id` under
   the same RLS policy as every other tenant-owned table
   (`tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id')`).
   But nothing sets `app.tenant_id` before login succeeds, since determining
   which tenant a login belongs to is the whole point of the lookup. Fixed
   by having the login, MFA-verify and password-reset-request endpoints call
   `set_tenant_context(db, tenant_id)` using the tenant the client explicitly
   named in the request, before querying `users`. This does not weaken
   isolation: choosing which tenant's account to attempt is not a privilege,
   since the attempt still has to clear password and MFA checks against
   whatever row RLS exposes for that tenant.
2. **Refresh token rotation was unreachable the same way**, but with no
   client-supplied tenant to bootstrap from: `/auth/refresh` and
   `/auth/logout` take only the opaque token. Looking up a row by an
   unguessable, hashed, random 32-byte token is itself the authorization
   proof, the same reasoning as (1) one level further removed. Rather than
   editing the already-pushed Phase 2 migration, migration 0004 explicitly
   disables RLS on `refresh_tokens` alone, with the reasoning recorded
   in the migration itself.
3. **Password reset confirmation had the same gap**, one step later: the
   reset token only carried the user's id, not their tenant, so
   `consume_reset_token` could not look the user up under the restricted
   role either. Fixed by putting `tid` in the signed reset token payload
   (it was already known when the token was issued) and having
   `consume_reset_token` set tenant context from it before the lookup.

All three were caught by actually running the login flow through the real
HTTP API against the real restricted role, not by inspection; the first
attempt returned "unknown_user" for a user that demonstrably existed.
