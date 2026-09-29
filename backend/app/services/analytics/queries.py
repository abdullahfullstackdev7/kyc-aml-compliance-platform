"""Pre-aggregated operational analytics queries (see PROJECT_PLAN.md Phase
9.4-9.5: "analytics endpoints return pre-aggregated series, never raw
rows"). Scoped to the Operations/Compliance dashboard only - the Revenue
dashboard (9.3) needs 24 months of synthetic subscription/invoice history
that doesn't exist yet and is out of scope for this build.

Every query runs through a tenant-scoped session (RLS via `app.tenant_id`,
see api/deps.py), so results are naturally tenant-isolated without an
explicit tenant_id filter here.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.cases import Case
from backend.app.models.governance import AuditLog, LlmCall
from backend.app.models.screening import ScreeningRun
from backend.app.services.onboarding.state_machine import TERMINAL_STATES

_OPEN_SLA_STATES = ("PENDING_L1", "PENDING_L2", "ESCALATED")


def applications_funnel(session: Session) -> dict[str, int]:
    """Counts applications that ever reached each milestone state, read from
    the audit trail (every transition is guaranteed to be recorded there -
    see the Phase 5 exit criterion) rather than current state, since an RFI
    can send an application back to SUBMITTED after DOCS_VERIFIED."""

    def count_reached(states: tuple[str, ...]) -> int:
        query = (
            select(func.count(func.distinct(AuditLog.resource_id)))
            .where(AuditLog.resource_type == "application")
            .where(AuditLog.after["state"].astext.in_(states))
        )
        return session.execute(query).scalar_one()

    return {
        "submitted": count_reached(("SUBMITTED",)),
        "docs_verified": count_reached(("DOCS_VERIFIED",)),
        "screened": count_reached(("SCREENING",)),
        "decided": count_reached(tuple(TERMINAL_STATES)),
    }


def routing_distribution(session: Session) -> list[dict]:
    """Case counts by tier - a simple stand-in for the full Sankey in 9.4,
    which is out of scope for this lean build."""
    rows = session.execute(select(Case.tier, func.count(Case.id)).group_by(Case.tier)).all()
    return [{"tier": tier, "count": count} for tier, count in rows]


def daily_screening_volume(session: Session, days: int = 30) -> list[dict]:
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    day = func.date_trunc("day", ScreeningRun.started_at)
    rows = session.execute(
        select(day.label("day"), func.count(ScreeningRun.id))
        .where(ScreeningRun.started_at >= since)
        .group_by(day)
        .order_by(day)
    ).all()
    return [{"date": d.date().isoformat(), "count": count} for d, count in rows]


def sla_compliance(session: Session) -> dict[str, int]:
    """Mirrors case_service.sla_breached()'s rule exactly: only open cases
    (PENDING_L1/PENDING_L2/ESCALATED) with a past-due sla_due_at count as
    breached; decided cases are neither breached nor at-risk."""
    now = dt.datetime.now(dt.UTC)
    open_cases = select(Case).where(Case.state.in_(_OPEN_SLA_STATES))
    rows = session.execute(open_cases).scalars().all()
    breached = sum(1 for c in rows if c.sla_due_at is not None and c.sla_due_at < now)
    on_track = len(rows) - breached
    return {"breached": breached, "on_track": on_track}


def llm_usage(session: Session) -> dict:
    rows = session.execute(
        select(
            LlmCall.provider,
            LlmCall.status,
            func.count(LlmCall.id),
            func.coalesce(func.sum(LlmCall.prompt_tokens + LlmCall.completion_tokens), 0),
        ).group_by(LlmCall.provider, LlmCall.status)
    ).all()

    total_calls = sum(count for _, _, count, _ in rows)
    cached_calls = sum(count for provider, _, count, _ in rows if provider == "cache")

    return {
        "by_provider_status": [
            {"provider": provider, "status": status, "calls": count, "tokens": tokens}
            for provider, status, count, tokens in rows
        ],
        "cache_hit_rate": round(cached_calls / total_calls, 4) if total_calls else 0.0,
        "total_calls": total_calls,
    }
