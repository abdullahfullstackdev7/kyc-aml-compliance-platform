"""Wires DOCS_VERIFIED -> screening -> risk -> routing -> case creation.
See PROJECT_PLAN.md Phase 5.3.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from backend.app.models.cases import Case
from backend.app.models.onboarding import Application, Customer, Document, DocumentCheck
from backend.app.models.screening import ScreeningHit, ScreeningRun
from backend.app.services.onboarding.state_machine import transition
from backend.app.services.screening.risk import CustomerRiskFactors, compute_customer_risk
from backend.app.services.screening.routing import RoutingInput, Tier, route_case
from backend.app.services.screening.service import ScreeningQuery, screen_name

TOP_HITS_STORED = 10

# Tier -> (application state, case state)
TIER_OUTCOMES: dict[Tier, tuple[str, str]] = {
    Tier.CLEAR: ("AUTO_APPROVED", "CLEARED"),
    Tier.REVIEW: ("PENDING_L1", "PENDING_L1"),
    Tier.HIGH_RISK: ("PENDING_L2", "PENDING_L2"),
    Tier.REJECT: ("SYSTEM_REJECTED", "REJECTED"),
}


def _document_check_status(session: Session, application_id: int) -> str | None:
    results = [
        r[0]
        for r in session.query(DocumentCheck.result)
        .join(Document, Document.id == DocumentCheck.document_id)
        .filter(Document.application_id == application_id)
        .all()
    ]
    if not results:
        return None
    if "fail" in results:
        return "fail"
    if "warn" in results:
        return "warn"
    return "pass"


def run_screening_and_route(
    session: Session, application: Application, customer: Customer, customer_full_name: str
) -> tuple[ScreeningRun, Case]:
    query = ScreeningQuery(
        full_name=customer_full_name,
        nationality=customer.nationality,
        entity_type="individual" if customer.customer_type == "individual" else "entity",
        top_n=TOP_HITS_STORED,
    )
    result = screen_name(session, query)

    run = ScreeningRun(
        tenant_id=application.tenant_id,
        customer_id=customer.id,
        trigger="onboarding",
        status="completed",
        completed_at=dt.datetime.now(dt.UTC),
        duration_ms=int(result.duration_ms),
    )
    session.add(run)
    session.flush()

    for hit in result.hits:
        session.add(
            ScreeningHit(
                tenant_id=application.tenant_id,
                screening_run_id=run.id,
                entity_uid=hit.entity_id,
                matched_name=hit.matched_name,
                composite_score=hit.breakdown.composite_score,
                scores={
                    "name_score": hit.breakdown.name_score,
                    "token_set_ratio": hit.breakdown.token_set_ratio,
                    "token_sort_ratio": hit.breakdown.token_sort_ratio,
                    "jaro_winkler": hit.breakdown.jaro_winkler,
                    "embedding_similarity": hit.breakdown.embedding_similarity,
                    "adjustments": hit.breakdown.adjustments,
                    "forced": hit.breakdown.forced,
                    "retrieval_methods": hit.retrieval_methods,
                    "primary_name": hit.primary_name,
                    "source": hit.source,
                    "sdn_type": hit.sdn_type,
                    "programs": hit.programs,
                },
            )
        )
    session.flush()

    top_score = result.hits[0].breakdown.composite_score if result.hits else None
    exact_id_match = bool(result.hits) and result.hits[0].breakdown.forced == "exact_id_match"
    has_corroboration = bool(result.hits) and bool(result.hits[0].breakdown.adjustments)
    document_status = _document_check_status(session, application.id)

    risk = compute_customer_risk(
        session,
        CustomerRiskFactors(
            customer_type=customer.customer_type,
            nationality=customer.nationality,
            residence_country=customer.residence_country,
            occupation=customer.occupation,
            expected_monthly_volume=customer.expected_monthly_volume,
            document_check_status=document_status,
        ),
    )

    routing = route_case(
        RoutingInput(
            top_score=top_score,
            customer_risk=risk.level,
            document_check_status=document_status,
            has_corroborating_attribute=has_corroboration,
            exact_id_match=exact_id_match,
        )
    )

    application_state, case_state = TIER_OUTCOMES[routing.tier]

    case = Case(
        tenant_id=application.tenant_id,
        application_id=application.id,
        customer_id=customer.id,
        screening_run_id=run.id,
        tier=routing.tier.value,
        state=case_state,
        sla_due_at=(
            dt.datetime.now(dt.UTC) + dt.timedelta(hours=routing.sla_hours)
            if routing.sla_hours
            else None
        ),
    )
    session.add(case)
    session.flush()

    transition(
        session,
        application,
        application_state,
        actor_id=None,
        actor_role="system",
        case_id=case.id,
        reason=f"screening routed to tier {routing.tier.value}",
    )

    return run, case
