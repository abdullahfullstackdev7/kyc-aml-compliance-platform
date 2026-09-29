"""Continuous rescreening: when the sanctions list changes, rescreen only
the customers whose existing screening hits touch a changed entity, or who
share a token with a newly added/modified entity's normalized names.
See PROJECT_PLAN.md Phase 5.5 and Phase 1's delta_rescreen asset.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.cases import Case
from backend.app.models.onboarding import Customer
from backend.app.models.screening import ScreeningHit, ScreeningRun
from backend.app.services.screening.service import ScreeningQuery, screen_name


def find_affected_customers(session: Session, changed_entity_uids: list[int]) -> list[int]:
    """Customers whose most recent screening run has a hit against any of
    the changed entities. A customer never screened against those specific
    entities before is unaffected by this delta (they will still be covered
    the next time they are screened against the full list)."""
    if not changed_entity_uids:
        return []

    from backend.app.models.sanctions import SanctionsEntity

    rows = session.execute(
        select(ScreeningRun.customer_id)
        .join(ScreeningHit, ScreeningHit.screening_run_id == ScreeningRun.id)
        .join(SanctionsEntity, SanctionsEntity.uid == ScreeningHit.entity_uid)
        .where(SanctionsEntity.id.in_(changed_entity_uids), ScreeningRun.customer_id.isnot(None))
        .distinct()
    ).all()
    return [r[0] for r in rows if r[0] is not None]


def rescreen_customer(session: Session, customer: Customer, full_name: str) -> ScreeningRun:
    """Runs a fresh screening pass for one customer and, if the new top hit
    crosses into review/high-risk territory, reopens or creates a case."""
    from backend.app.services.screening.risk import RiskLevel
    from backend.app.services.screening.routing import RoutingInput, Tier, route_case

    result = screen_name(session, ScreeningQuery(full_name=full_name, top_n=10))

    run = ScreeningRun(
        tenant_id=customer.tenant_id,
        customer_id=customer.id,
        trigger="rescreen",
        status="completed",
        completed_at=dt.datetime.now(dt.UTC),
        duration_ms=int(result.duration_ms),
    )
    session.add(run)
    session.flush()

    for hit in result.hits:
        session.add(
            ScreeningHit(
                tenant_id=customer.tenant_id,
                screening_run_id=run.id,
                entity_uid=hit.entity_id,
                matched_name=hit.matched_name,
                composite_score=hit.breakdown.composite_score,
                scores={"adjustments": hit.breakdown.adjustments, "forced": hit.breakdown.forced},
            )
        )

    top_score = result.hits[0].breakdown.composite_score if result.hits else None
    # Rescreening does not have a fresh customer risk assessment to hand; a
    # rescreen is triggered purely by a name-match change on the sanctions
    # side, so this uses a neutral Medium baseline rather than re-deriving
    # risk from data that has not changed since onboarding.
    routing = route_case(
        RoutingInput(
            top_score=top_score, customer_risk=RiskLevel.MEDIUM, document_check_status="pass"
        )
    )

    if routing.tier in (Tier.REVIEW, Tier.HIGH_RISK):
        existing_open_case = session.execute(
            select(Case).where(
                Case.customer_id == customer.id, Case.state.in_(("PENDING_L1", "PENDING_L2"))
            )
        ).scalar_one_or_none()
        if existing_open_case is None:
            latest_application = session.execute(
                select(Case.application_id).where(Case.customer_id == customer.id).limit(1)
            ).scalar_one_or_none()
            if latest_application is not None:
                session.add(
                    Case(
                        tenant_id=customer.tenant_id,
                        application_id=latest_application,
                        customer_id=customer.id,
                        screening_run_id=run.id,
                        tier=routing.tier.value,
                        state="PENDING_L1" if routing.tier == Tier.REVIEW else "PENDING_L2",
                        sla_due_at=dt.datetime.now(dt.UTC)
                        + dt.timedelta(hours=routing.sla_hours or 24),
                    )
                )

    session.flush()
    return run


def enqueue_customer_rescreen(changed_entity_uids: list[int]) -> int:
    """Called from the Dagster delta_rescreen asset (Phase 1) after a
    sanctions list ingest. Opens its own session since it runs from a
    pipeline context, not a request."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.app.core.config import get_settings
    from backend.app.core.security.encryption import decrypt_pii

    engine = create_engine(get_settings().sync_database_url())
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    affected = 0
    with Session() as session:
        customer_ids = find_affected_customers(session, changed_entity_uids)
        customers = (
            session.execute(select(Customer).where(Customer.id.in_(customer_ids))).scalars().all()
        )
        for customer in customers:
            try:
                full_name = decrypt_pii(session, customer.tenant_id, customer.full_name_encrypted)
            except Exception:  # noqa: BLE001, S112 - skip undecryptable customers rather than aborting the batch
                continue
            rescreen_customer(session, customer, full_name)
            affected += 1
        session.commit()

    return affected
