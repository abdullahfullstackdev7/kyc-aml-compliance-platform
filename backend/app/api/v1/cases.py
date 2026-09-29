from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_tenant_scoped_db
from backend.app.core.security.permissions import AuthorizationError, Principal, require_permission
from backend.app.models.cases import Case, CaseEvent, CaseNote
from backend.app.models.screening import ScreeningHit
from backend.app.schemas.cases import (
    AssignRequest,
    BulkClearRequest,
    CaseDetail,
    CaseSummary,
    DecisionRequest,
    DispositionRequest,
    HitResponse,
    NoteCreateRequest,
    RfiCreateRequest,
)
from backend.app.services.onboarding.case_service import (
    CaseServiceError,
    add_note,
    assign_case,
    bulk_clear_low_score_hits,
    decide_case,
    request_information,
    set_hit_disposition,
    sla_breached,
)

router = APIRouter(prefix="/cases", tags=["cases"])


def _get_case(db: Session, case_id: int) -> Case:
    case = db.execute(select(Case).where(Case.id == case_id)).scalar_one_or_none()
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    return case


@router.get("", response_model=list[CaseSummary])
def list_cases(
    tier: str | None = None,
    state: str | None = None,
    assignee_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    principal: Principal = Depends(require_permission("cases:read")),
    db: Session = Depends(get_tenant_scoped_db),
) -> list[CaseSummary]:
    query = select(Case)
    if tier:
        query = query.where(Case.tier == tier)
    if state:
        query = query.where(Case.state == state)
    if assignee_id:
        query = query.where(Case.assignee_id == assignee_id)
    query = query.order_by(Case.created_at.desc()).limit(limit).offset(offset)

    cases = db.execute(query).scalars().all()
    return [
        CaseSummary(
            id=c.id,
            tier=c.tier,
            state=c.state,
            assignee_id=c.assignee_id,
            sla_due_at=c.sla_due_at,
            sla_breached=sla_breached(c),
            created_at=c.created_at,
        )
        for c in cases
    ]


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(
    case_id: int,
    principal: Principal = Depends(require_permission("cases:read")),
    db: Session = Depends(get_tenant_scoped_db),
) -> CaseDetail:
    case = _get_case(db, case_id)
    hits = (
        db.execute(
            select(ScreeningHit).where(ScreeningHit.screening_run_id == case.screening_run_id)
        )
        .scalars()
        .all()
    )
    return CaseDetail(
        id=case.id,
        tenant_id=case.tenant_id,
        application_id=case.application_id,
        customer_id=case.customer_id,
        tier=case.tier,
        state=case.state,
        assignee_id=case.assignee_id,
        decision=case.decision,
        decided_by_id=case.decided_by_id,
        second_approver_id=case.second_approver_id,
        sla_due_at=case.sla_due_at,
        sla_breached=sla_breached(case),
        hits=[
            HitResponse(
                id=h.id,
                entity_uid=h.entity_uid,
                matched_name=h.matched_name,
                composite_score=float(h.composite_score),
                disposition=h.disposition,
                disposition_reason=h.disposition_reason,
                scores=h.scores,
            )
            for h in hits
        ],
    )


@router.post("/{case_id}/assign", response_model=CaseSummary)
def assign(
    case_id: int,
    body: AssignRequest,
    principal: Principal = Depends(require_permission("cases:work_review")),
    db: Session = Depends(get_tenant_scoped_db),
) -> CaseSummary:
    case = _get_case(db, case_id)
    try:
        assign_case(db, case, assignee_id=body.assignee_id, actor=principal)
    except (CaseServiceError, AuthorizationError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    return CaseSummary(
        id=case.id,
        tier=case.tier,
        state=case.state,
        assignee_id=case.assignee_id,
        sla_due_at=case.sla_due_at,
        sla_breached=sla_breached(case),
        created_at=case.created_at,
    )


@router.post("/{case_id}/hits/{hit_id}/disposition", response_model=HitResponse)
def disposition(
    case_id: int,
    hit_id: int,
    body: DispositionRequest,
    principal: Principal = Depends(require_permission("cases:clear")),
    db: Session = Depends(get_tenant_scoped_db),
) -> HitResponse:
    _get_case(db, case_id)
    hit = db.execute(select(ScreeningHit).where(ScreeningHit.id == hit_id)).scalar_one_or_none()
    if hit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hit not found")
    try:
        set_hit_disposition(
            db, hit, disposition=body.disposition, reason_code=body.reason_code, actor=principal
        )
    except (CaseServiceError, AuthorizationError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    return HitResponse(
        id=hit.id,
        entity_uid=hit.entity_uid,
        matched_name=hit.matched_name,
        composite_score=float(hit.composite_score),
        disposition=hit.disposition,
        disposition_reason=hit.disposition_reason,
        scores=hit.scores,
    )


@router.post("/{case_id}/hits/bulk-clear", response_model=list[HitResponse])
def bulk_clear(
    case_id: int,
    body: BulkClearRequest,
    principal: Principal = Depends(require_permission("cases:work_high_risk")),
    db: Session = Depends(get_tenant_scoped_db),
) -> list[HitResponse]:
    case = _get_case(db, case_id)
    hits = (
        db.execute(
            select(ScreeningHit).where(ScreeningHit.screening_run_id == case.screening_run_id)
        )
        .scalars()
        .all()
    )
    try:
        cleared = bulk_clear_low_score_hits(
            db, case, list(hits), threshold=body.threshold, actor=principal
        )
    except AuthorizationError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    db.commit()
    return [
        HitResponse(
            id=h.id,
            entity_uid=h.entity_uid,
            matched_name=h.matched_name,
            composite_score=float(h.composite_score),
            disposition=h.disposition,
            disposition_reason=h.disposition_reason,
            scores=h.scores,
        )
        for h in cleared
    ]


@router.post("/{case_id}/decision", response_model=CaseSummary)
def decision(
    case_id: int,
    body: DecisionRequest,
    idempotency_key: str | None = None,
    principal: Principal = Depends(require_permission("cases:decide")),
    db: Session = Depends(get_tenant_scoped_db),
) -> CaseSummary:
    case = _get_case(db, case_id)
    if idempotency_key and case.decision_idempotency_key == idempotency_key:
        return CaseSummary(
            id=case.id,
            tier=case.tier,
            state=case.state,
            assignee_id=case.assignee_id,
            sla_due_at=case.sla_due_at,
            sla_breached=sla_breached(case),
            created_at=case.created_at,
        )

    try:
        decide_case(
            db,
            case,
            decision=body.decision,
            actor=principal,
            is_second_approval=body.is_second_approval,
        )
    except (CaseServiceError, AuthorizationError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    if idempotency_key:
        case.decision_idempotency_key = idempotency_key
    db.commit()
    return CaseSummary(
        id=case.id,
        tier=case.tier,
        state=case.state,
        assignee_id=case.assignee_id,
        sla_due_at=case.sla_due_at,
        sla_breached=sla_breached(case),
        created_at=case.created_at,
    )


@router.post("/{case_id}/approve-second", response_model=CaseSummary)
def approve_second(
    case_id: int,
    principal: Principal = Depends(require_permission("cases:approve_second")),
    db: Session = Depends(get_tenant_scoped_db),
) -> CaseSummary:
    case = _get_case(db, case_id)
    try:
        decide_case(db, case, decision="reject", actor=principal, is_second_approval=True)
    except (CaseServiceError, AuthorizationError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.commit()
    return CaseSummary(
        id=case.id,
        tier=case.tier,
        state=case.state,
        assignee_id=case.assignee_id,
        sla_due_at=case.sla_due_at,
        sla_breached=sla_breached(case),
        created_at=case.created_at,
    )


@router.post("/{case_id}/rfi", status_code=status.HTTP_201_CREATED)
def rfi(
    case_id: int,
    body: RfiCreateRequest,
    principal: Principal = Depends(require_permission("cases:request_info")),
    db: Session = Depends(get_tenant_scoped_db),
) -> dict:
    case = _get_case(db, case_id)
    result = request_information(db, case, message=body.message, actor=principal)
    db.commit()
    return {"id": result.id, "status": result.status}


@router.post("/{case_id}/notes", status_code=status.HTTP_201_CREATED)
def add_case_note(
    case_id: int,
    body: NoteCreateRequest,
    principal: Principal = Depends(require_permission("cases:note")),
    db: Session = Depends(get_tenant_scoped_db),
) -> dict:
    case = _get_case(db, case_id)
    note = add_note(db, case, body=body.body, actor=principal)
    db.commit()
    return {"id": note.id}


@router.get("/{case_id}/summary")
def case_summary(
    case_id: int,
    principal: Principal = Depends(require_permission("cases:read")),
    db: Session = Depends(get_tenant_scoped_db),
) -> dict:
    """Lazy LLM case summary (Phase 6). Not yet wired to a provider; returns
    the deterministic template fallback the plan specifies for when no LLM
    provider is available, so the endpoint is usable ahead of Phase 6."""
    case = _get_case(db, case_id)
    hits = (
        db.execute(
            select(ScreeningHit).where(ScreeningHit.screening_run_id == case.screening_run_id)
        )
        .scalars()
        .all()
    )
    top = max(hits, key=lambda h: h.composite_score, default=None)
    summary = (
        f"Case {case.id}, tier {case.tier}. Top match: {top.matched_name} (score {top.composite_score})."
        if top
        else f"Case {case.id}, tier {case.tier}. No screening hits recorded."
    )
    return {
        "summary": summary,
        "confidence": "low",
        "source": "Automated summary (assistant unavailable)",
    }


@router.get("/{case_id}/export")
def export_case(
    case_id: int,
    principal: Principal = Depends(require_permission("cases:read")),
    db: Session = Depends(get_tenant_scoped_db),
) -> Response:
    from backend.app.services.onboarding.export import ExportUnavailableError, render_case_pdf

    case = _get_case(db, case_id)
    hits = (
        db.execute(
            select(ScreeningHit).where(ScreeningHit.screening_run_id == case.screening_run_id)
        )
        .scalars()
        .all()
    )
    notes = db.execute(select(CaseNote).where(CaseNote.case_id == case_id)).scalars().all()
    events = db.execute(select(CaseEvent).where(CaseEvent.case_id == case_id)).scalars().all()

    try:
        pdf_bytes = render_case_pdf(case, list(hits), list(notes), list(events))
    except ExportUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    return Response(content=pdf_bytes, media_type="application/pdf")
