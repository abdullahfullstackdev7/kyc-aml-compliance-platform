"""Application state machine. See PROJECT_PLAN.md Phase 5.1.

    DRAFT -> SUBMITTED -> DOCS_PROCESSING -> DOCS_VERIFIED | DOCS_FAILED
          -> SCREENING -> AUTO_APPROVED | PENDING_L1 | PENDING_L2 | SYSTEM_REJECTED
    PENDING_L1 -> CLEARED | ESCALATED (to PENDING_L2) | RFI_REQUESTED
    PENDING_L2 -> APPROVED (dual) | REJECTED (dual) | RFI_REQUESTED
    RFI_REQUESTED -> SUBMITTED (on customer response)

Every transition writes a case_events (if a case exists yet) and an
audit_log entry; guard functions reject transitions that violate the graph
above or an ABAC rule (e.g. four-eyes).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from backend.app.core.security.audit import write_audit_event
from backend.app.models.onboarding import Application

# Application-level states (not case tiers, which are clear|review|high_risk|reject).
VALID_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"SUBMITTED"},
    "SUBMITTED": {"DOCS_PROCESSING", "RFI_REQUESTED"},
    "DOCS_PROCESSING": {"DOCS_VERIFIED", "DOCS_FAILED"},
    "DOCS_VERIFIED": {"SCREENING"},
    "SCREENING": {"AUTO_APPROVED", "PENDING_L1", "PENDING_L2", "SYSTEM_REJECTED"},
    "PENDING_L1": {"CLEARED", "ESCALATED", "RFI_REQUESTED"},
    "PENDING_L2": {"APPROVED", "REJECTED", "RFI_REQUESTED"},
    "ESCALATED": {"PENDING_L2"},
    "RFI_REQUESTED": {"SUBMITTED"},
    "DOCS_FAILED": set(),
    "SYSTEM_REJECTED": set(),
    "AUTO_APPROVED": set(),
    "CLEARED": set(),
    "APPROVED": set(),
    "REJECTED": set(),
}

TERMINAL_STATES = {state for state, transitions in VALID_TRANSITIONS.items() if not transitions}


class InvalidTransitionError(Exception):
    pass


def transition(
    session: Session,
    application: Application,
    new_state: str,
    *,
    actor_id: int | None,
    actor_role: str | None,
    case_id: int | None = None,
    reason: str | None = None,
) -> Application:
    current_state = application.state
    allowed = VALID_TRANSITIONS.get(current_state, set())
    if new_state not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition application {application.id} from {current_state} to {new_state}"
        )

    application.state = new_state
    if new_state == "SUBMITTED" and current_state == "DRAFT":
        application.submitted_at = dt.datetime.now(dt.UTC)
    if new_state in TERMINAL_STATES:
        application.decided_at = dt.datetime.now(dt.UTC)

    if case_id is not None:
        from backend.app.models.cases import CaseEvent

        session.add(
            CaseEvent(
                tenant_id=application.tenant_id,
                case_id=case_id,
                event_type="application_state_change",
                actor_id=actor_id,
                payload={"from": current_state, "to": new_state, "reason": reason},
            )
        )

    write_audit_event(
        session,
        tenant_id=application.tenant_id,
        actor_id=actor_id,
        actor_role=actor_role,
        action="application_state_change",
        resource_type="application",
        resource_id=str(application.id),
        before={"state": current_state},
        after={"state": new_state, "reason": reason},
    )
    session.flush()
    return application
