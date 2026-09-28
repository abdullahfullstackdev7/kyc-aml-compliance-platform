from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class ScreeningRun(Base):
    __tablename__ = "screening_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)  # onboarding|rescreen|adhoc
    list_version_id: Mapped[int | None] = mapped_column(ForeignKey("sanctions_list_versions.id"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class ScreeningHit(Base):
    __tablename__ = "screening_hits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    screening_run_id: Mapped[int] = mapped_column(
        ForeignKey("screening_runs.id", ondelete="CASCADE"), nullable=False
    )
    entity_uid: Mapped[int] = mapped_column(ForeignKey("sanctions_entities.id"), nullable=False)
    matched_name: Mapped[str] = mapped_column(String(255), nullable=False)
    composite_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    disposition: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
