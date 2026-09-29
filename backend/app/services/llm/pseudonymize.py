"""Builds the compact, pseudonymized payload sent to an LLM provider. See
PROJECT_PLAN.md Phase 6.3.2 (compact payload) and 6.4 (privacy): customer
name is kept only for name-match comparison, DOB is reduced to birth year,
address to country, ID numbers/contact details are dropped entirely, and
internal database IDs are replaced by a case-scoped alias. SDN data is
public and is sent as is (aside from the 160-char remarks truncation).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.cases import Case
from backend.app.models.onboarding import Application, Customer, Document, DocumentCheck
from backend.app.models.sanctions import SanctionsEntity
from backend.app.models.screening import ScreeningHit

MAX_HITS = 3
MAX_REMARKS_CHARS = 160


def _document_check_status(session: Session, application_id: int) -> str | None:
    results = (
        session.execute(
            select(DocumentCheck.result)
            .join(Document, Document.id == DocumentCheck.document_id)
            .where(Document.application_id == application_id)
        )
        .scalars()
        .all()
    )
    if not results:
        return None
    if "fail" in results:
        return "fail"
    if "warn" in results:
        return "warn"
    return "pass"


def _dob_year(dob_iso: str | None) -> int | None:
    if not dob_iso:
        return None
    try:
        return dt.date.fromisoformat(dob_iso).year
    except ValueError:
        return None


def build_case_payload(
    session: Session,
    case: Case,
    hits: list[ScreeningHit],
    customer: Customer,
    full_name: str,
    dob_iso: str | None,
) -> dict:
    application = session.execute(
        select(Application).where(Application.id == case.application_id)
    ).scalar_one_or_none()
    doc_status = (
        _document_check_status(session, application.id) if application is not None else None
    )

    top_hits = sorted(hits, key=lambda h: h.composite_score, reverse=True)[:MAX_HITS]
    entity_ids = [h.entity_uid for h in top_hits]
    remarks_by_id: dict[int, str | None] = {}
    if entity_ids:
        rows = session.execute(
            select(SanctionsEntity.id, SanctionsEntity.remarks).where(
                SanctionsEntity.id.in_(entity_ids)
            )
        ).all()
        remarks_by_id = {row[0]: row[1] for row in rows}

    return {
        "alias": f"case-{case.id}",
        "tier": case.tier,
        "name": full_name,
        "dob_year": _dob_year(dob_iso),
        "nationality": customer.nationality,
        "residence_country": customer.residence_country,
        "occupation": customer.occupation,
        "doc_status": doc_status,
        "hits": [
            {
                "name": h.matched_name,
                "score": round(float(h.composite_score)),
                "programs": (h.scores or {}).get("programs") or [],
                "sdn_type": (h.scores or {}).get("sdn_type"),
                "remarks": (remarks_by_id.get(h.entity_uid) or "")[:MAX_REMARKS_CHARS],
            }
            for h in top_hits
        ],
    }
