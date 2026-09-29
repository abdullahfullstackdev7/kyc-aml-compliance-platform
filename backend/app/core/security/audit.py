"""Immutable audit trail: hash-chained writes, append-only at the database
level (see migration 0004: an UPDATE/DELETE-blocking trigger and a narrowed
application database role).

See PROJECT_PLAN.md Phase 4.4. hash = SHA-256(prev_hash || canonical_json(record)).
Every state change, decision, login, export, config change and LLM call is
expected to call write_audit_event.

The chain is per-tenant, not one global sequence, and platform-level events
(tenant_id is None) form their own separate chain. This is not just a
modelling choice: audit_log has tenant-isolation RLS (migration 0002/0004),
so a request-scoped session only ever sees its own tenant's rows when
`app.tenant_id` is set. A single chain walked in id order would silently
compute the wrong prev_hash the first time two tenants interleave writes,
since each write only ever sees its own tenant's last row - found by running
the onboarding flow end to end across two tenants, not by inspection.
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.governance import AuditLog

GENESIS_HASH = "0" * 64


def _canonical_json(record: dict) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)


def _compute_hash(prev_hash: str, record: dict) -> str:
    payload = prev_hash + _canonical_json(record)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _last_hash(session: Session, tenant_id: int | None) -> str:
    query = select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)
    query = (
        query.where(AuditLog.tenant_id.is_(None))
        if tenant_id is None
        else query.where(AuditLog.tenant_id == tenant_id)
    )
    last = session.execute(query).scalar_one_or_none()
    return last or GENESIS_HASH


def write_audit_event(
    session: Session,
    *,
    tenant_id: int | None,
    actor_id: int | None,
    actor_role: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    request_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> AuditLog:
    prev_hash = _last_hash(session, tenant_id)
    record = {
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "request_id": request_id,
        "before": before,
        "after": after,
    }
    entry_hash = _compute_hash(prev_hash, record)

    entry = AuditLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        before=before,
        after=after,
        prev_hash=prev_hash,
        hash=entry_hash,
    )
    session.add(entry)
    session.flush()
    return entry


def _record_dict(entry: AuditLog) -> dict:
    return {
        "tenant_id": entry.tenant_id,
        "actor_id": entry.actor_id,
        "actor_role": entry.actor_role,
        "action": entry.action,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "request_id": entry.request_id,
        "before": entry.before,
        "after": entry.after,
    }


def verify_audit_chain(session: Session, tenant_id: int | None) -> tuple[bool, int | None]:
    """Walks one tenant's chain in id order, recomputing each hash. Returns
    (is_valid, first_broken_id) - first_broken_id is None if the chain is
    intact or empty. Pass the tenant id to check, or None for the platform
    (tenant_id IS NULL) chain; each tenant's chain is independent (see the
    module docstring), so there is no single "verify everything" call."""
    query = select(AuditLog).order_by(AuditLog.id.asc())
    query = query.where(AuditLog.tenant_id.is_(None)) if tenant_id is None else query.where(
        AuditLog.tenant_id == tenant_id
    )
    entries = session.execute(query).scalars().all()

    prev_hash = GENESIS_HASH
    for entry in entries:
        expected_hash = _compute_hash(prev_hash, _record_dict(entry))
        if entry.prev_hash != prev_hash or entry.hash != expected_hash:
            return False, entry.id
        prev_hash = entry.hash

    return True, None
