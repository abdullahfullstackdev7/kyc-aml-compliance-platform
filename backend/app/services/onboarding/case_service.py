"""Case management: queue assignment, hit disposition, decisions (with the
four-eyes and assignment ABAC rules from Phase 4), RFI, bulk clear.
See PROJECT_PLAN.md Phase 5.4.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.security.audit import write_audit_event
from backend.app.core.security.permissions import (
    AuthorizationError,
    Principal,
    check_case_assignment,
    check_four_eyes,
    check_same_tenant,
)
from backend.app.models.cases import Case, CaseEvent, CaseNote, RfiRequest
from backend.app.models.identity import Role, User, UserRole
from backend.app.models.screening import ScreeningHit

VALID_REASON_CODES = {
    "confirmed_no_match",
    "confirmed_transliteration_variant",
    "confirmed_different_dob",
    "confirmed_true_match",
    "insufficient_evidence",
}


class CaseServiceError(Exception):
    pass


def _log_event(
    session: Session, case: Case, event_type: str, actor_id: int | None, payload: dict
) -> None:
    session.add(
        CaseEvent(
            tenant_id=case.tenant_id,
            case_id=case.id,
            event_type=event_type,
            actor_id=actor_id,
            payload=payload,
        )
    )


def assign_case(session: Session, case: Case, *, assignee_id: int | None, actor: Principal) -> Case:
    """Explicit assignment (pull or admin push). `assignee_id=None` picks the
    least-loaded analyst holding a role appropriate to the case's tier via a
    simple round-robin (fewest currently-open cases wins)."""
    check_same_tenant(actor, case.tenant_id)

    if assignee_id is None:
        role_code = "senior_reviewer" if case.tier == "high_risk" else "compliance_analyst"
        assignee_id = _least_loaded_analyst(session, case.tenant_id, role_code)
        if assignee_id is None:
            raise CaseServiceError(f"No available {role_code} to assign in this tenant")

    case.assignee_id = assignee_id
    _log_event(session, case, "assigned", actor.user_id, {"assignee_id": assignee_id})
    write_audit_event(
        session,
        tenant_id=case.tenant_id,
        actor_id=actor.user_id,
        actor_role=None,
        action="case_assign",
        resource_type="case",
        resource_id=str(case.id),
        after={"assignee_id": assignee_id},
    )
    session.flush()
    return case


def _least_loaded_analyst(session: Session, tenant_id: int, role_code: str) -> int | None:
    open_states = ("PENDING_L1", "PENDING_L2")
    load_subquery = (
        select(Case.assignee_id, func.count(Case.id).label("open_count"))
        .where(Case.tenant_id == tenant_id, Case.state.in_(open_states))
        .group_by(Case.assignee_id)
        .subquery()
    )
    candidates = session.execute(
        select(User.id, func.coalesce(load_subquery.c.open_count, 0))
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .outerjoin(load_subquery, load_subquery.c.assignee_id == User.id)
        .where(User.tenant_id == tenant_id, Role.code == role_code, User.status == "active")
        .order_by(func.coalesce(load_subquery.c.open_count, 0).asc())
        .limit(1)
    ).first()
    return candidates[0] if candidates else None


def set_hit_disposition(
    session: Session,
    hit: ScreeningHit,
    *,
    disposition: str,
    reason_code: str,
    actor: Principal,
) -> ScreeningHit:
    if reason_code not in VALID_REASON_CODES:
        raise CaseServiceError(f"Unknown reason code: {reason_code}")
    check_same_tenant(actor, hit.tenant_id)

    hit.disposition = disposition
    hit.disposition_reason = reason_code
    hit.disposition_by_id = actor.user_id
    hit.disposition_at = dt.datetime.now(dt.UTC)

    write_audit_event(
        session,
        tenant_id=hit.tenant_id,
        actor_id=actor.user_id,
        actor_role=None,
        action="hit_disposition",
        resource_type="screening_hit",
        resource_id=str(hit.id),
        after={"disposition": disposition, "reason_code": reason_code},
    )
    session.flush()
    return hit


def bulk_clear_low_score_hits(
    session: Session, case: Case, hits: list[ScreeningHit], *, threshold: float, actor: Principal
) -> list[ScreeningHit]:
    """L2-only, per PROJECT_PLAN.md Phase 5.4."""
    if "senior_reviewer" not in actor.roles and "platform_admin" not in actor.roles:
        raise AuthorizationError("Only a senior reviewer may bulk-clear hits")
    check_same_tenant(actor, case.tenant_id)

    cleared = []
    for hit in hits:
        if float(hit.composite_score) < threshold and hit.disposition == "pending":
            hit.disposition = "false_positive"
            hit.disposition_reason = "insufficient_evidence"
            hit.disposition_by_id = actor.user_id
            hit.disposition_at = dt.datetime.now(dt.UTC)
            cleared.append(hit)

    _log_event(
        session,
        case,
        "bulk_clear",
        actor.user_id,
        {"threshold": threshold, "cleared_hit_ids": [h.id for h in cleared]},
    )
    session.flush()
    return cleared


def decide_case(
    session: Session,
    case: Case,
    *,
    decision: str,
    actor: Principal,
    is_second_approval: bool = False,
) -> Case:
    """decision in {"approve", "reject", "clear"}. High-risk rejects require
    a distinct second approver (four-eyes); everything else is single-approval."""
    check_same_tenant(actor, case.tenant_id)
    # The case-assignment ("only the assigned analyst decides") rule governs
    # who may make the *first* decision on a case; a four-eyes second
    # approval is, by construction, made by someone other than whoever is
    # assigned, so that check does not apply to this step.
    if not is_second_approval:
        check_case_assignment(actor, case.assignee_id, is_reassigning=False)

    if case.tier == "high_risk" and decision == "reject":
        if not is_second_approval:
            case.decision = decision
            case.decided_by_id = actor.user_id
            _log_event(session, case, "first_approval", actor.user_id, {"decision": decision})
            session.flush()
            return case

        if case.decided_by_id is None:
            raise CaseServiceError("A first approval is required before a second approval")
        check_four_eyes(case.decided_by_id, actor.user_id)
        case.second_approver_id = actor.user_id
        case.state = "REJECTED"
        _log_event(session, case, "second_approval", actor.user_id, {"decision": decision})
    else:
        case.decision = decision
        case.decided_by_id = actor.user_id
        case.state = {"approve": "APPROVED", "reject": "REJECTED", "clear": "CLEARED"}[decision]
        _log_event(session, case, "decided", actor.user_id, {"decision": decision})

    write_audit_event(
        session,
        tenant_id=case.tenant_id,
        actor_id=actor.user_id,
        actor_role=None,
        action="case_decision",
        resource_type="case",
        resource_id=str(case.id),
        after={"decision": decision, "state": case.state},
    )
    session.flush()
    return case


def request_information(
    session: Session, case: Case, *, message: str, actor: Principal
) -> RfiRequest:
    check_same_tenant(actor, case.tenant_id)
    rfi = RfiRequest(
        tenant_id=case.tenant_id, case_id=case.id, requested_by_id=actor.user_id, message=message
    )
    session.add(rfi)
    case.state = "RFI_REQUESTED"
    _log_event(session, case, "rfi_requested", actor.user_id, {"message": message})
    session.flush()
    return rfi


def add_note(session: Session, case: Case, *, body: str, actor: Principal) -> CaseNote:
    check_same_tenant(actor, case.tenant_id)
    note = CaseNote(tenant_id=case.tenant_id, case_id=case.id, author_id=actor.user_id, body=body)
    session.add(note)
    _log_event(session, case, "note_added", actor.user_id, {})
    session.flush()
    return note


def sla_breached(case: Case) -> bool:
    open_states = {"PENDING_L1", "PENDING_L2", "ESCALATED"}
    if case.state not in open_states or case.sla_due_at is None:
        return False
    return dt.datetime.now(dt.UTC) > case.sla_due_at
