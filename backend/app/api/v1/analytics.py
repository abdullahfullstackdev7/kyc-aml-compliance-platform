"""Operations/Compliance analytics (PROJECT_PLAN.md Phase 9.4), scoped to
data already flowing through the system - see queries.py for what's in and
out of scope for this build.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.deps import get_tenant_scoped_db
from backend.app.core.security.permissions import Principal, require_permission
from backend.app.services.analytics import queries

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/funnel")
def funnel(
    principal: Principal = Depends(require_permission("analytics:view_tenant")),
    db: Session = Depends(get_tenant_scoped_db),
) -> dict:
    return queries.applications_funnel(db)


@router.get("/routing")
def routing(
    principal: Principal = Depends(require_permission("analytics:view_tenant")),
    db: Session = Depends(get_tenant_scoped_db),
) -> list[dict]:
    return queries.routing_distribution(db)


@router.get("/screening-volume")
def screening_volume(
    days: int = 30,
    principal: Principal = Depends(require_permission("analytics:view_tenant")),
    db: Session = Depends(get_tenant_scoped_db),
) -> list[dict]:
    return queries.daily_screening_volume(db, days=days)


@router.get("/sla")
def sla(
    principal: Principal = Depends(require_permission("analytics:view_tenant")),
    db: Session = Depends(get_tenant_scoped_db),
) -> dict:
    return queries.sla_compliance(db)


@router.get("/llm-usage")
def llm_usage(
    principal: Principal = Depends(require_permission("analytics:view_tenant")),
    db: Session = Depends(get_tenant_scoped_db),
) -> dict:
    return queries.llm_usage(db)
