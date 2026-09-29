"""Phase 5: disposition tracking on screening_hits, and an idempotency-key
column on cases for decision endpoints.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("screening_hits", sa.Column("disposition_reason", sa.Text()))
    op.add_column(
        "screening_hits", sa.Column("disposition_by_id", sa.Integer(), sa.ForeignKey("users.id"))
    )
    op.add_column("screening_hits", sa.Column("disposition_at", sa.DateTime(timezone=True)))

    op.add_column("cases", sa.Column("decision_idempotency_key", sa.String(128)))
    op.create_index(
        "ix_cases_decision_idempotency_key", "cases", ["decision_idempotency_key"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_cases_decision_idempotency_key", table_name="cases")
    op.drop_column("cases", "decision_idempotency_key")

    op.drop_column("screening_hits", "disposition_at")
    op.drop_column("screening_hits", "disposition_by_id")
    op.drop_column("screening_hits", "disposition_reason")
