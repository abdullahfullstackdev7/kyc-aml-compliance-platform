"""Phase 5: link a customer record to the portal user account that owns it,
so "customer" role JWTs can be scoped to their own application only.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")))
    op.create_index("ix_customers_user_id", "customers", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_customers_user_id", table_name="customers")
    op.drop_column("customers", "user_id")
