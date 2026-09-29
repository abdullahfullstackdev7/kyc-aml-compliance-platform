from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.models.sanctions import SanctionsChange, SanctionsEntity, SanctionsListVersion
from backend.app.services.screening.normalize import normalize_name

router = APIRouter(prefix="/lists", tags=["lists"])


@router.get("/versions")
def list_versions(limit: int = 20, db: Session = Depends(get_db)) -> list[dict]:
    versions = (
        db.execute(
            select(SanctionsListVersion)
            .order_by(SanctionsListVersion.fetched_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": v.id,
            "source": v.source,
            "publish_date": v.publish_date,
            "record_count": v.record_count,
            "status": v.status,
            "fetched_at": v.fetched_at,
        }
        for v in versions
    ]


@router.get("/changes")
def list_changes(version: int, db: Session = Depends(get_db)) -> list[dict]:
    changes = (
        db.execute(select(SanctionsChange).where(SanctionsChange.version_id == version))
        .scalars()
        .all()
    )
    return [
        {
            "entity_uid": c.entity_uid,
            "change_type": c.change_type,
            "diff": c.diff,
            "created_at": c.created_at,
        }
        for c in changes
    ]


@router.get("/entities/{uid}")
def get_entity(uid: int, db: Session = Depends(get_db)) -> dict:
    entity = db.execute(
        select(SanctionsEntity).where(
            SanctionsEntity.uid == uid, SanctionsEntity.source == "ofac_sdn"
        )
    ).scalar_one_or_none()
    if entity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found")
    return {
        "uid": entity.uid,
        "sdn_type": entity.sdn_type,
        "primary_name": entity.primary_name,
        "programs": entity.programs,
        "is_active": entity.is_active,
        "remarks": entity.remarks,
    }


@router.get("/search")
def search_entities(q: str, limit: int = 20, db: Session = Depends(get_db)) -> list[dict]:
    normalized = normalize_name(q)
    from backend.app.services.screening.candidates import generate_candidates

    candidates = generate_candidates(
        db,
        tokens=normalized.tokens,
        normalized=normalized.normalized,
        phonetic=normalized.phonetic,
        embedding=None,
        limit=limit,
    )
    return [
        {
            "entity_uid": c.entity_uid,
            "primary_name": c.primary_name,
            "matched_name": c.full_name,
            "sdn_type": c.sdn_type,
        }
        for c in candidates[:limit]
    ]
