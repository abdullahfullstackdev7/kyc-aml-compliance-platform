"""Enable required Postgres extensions and create the sanctions domain schema.

Revision ID: 0001
Revises:
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS fuzzystrmatch")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "sanctions_list_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("publish_date", sa.DateTime(timezone=True)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("record_count", sa.Integer()),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("etag", sa.String(255)),
        sa.Column("last_modified", sa.String(255)),
        sa.Column("status", sa.String(16), nullable=False, server_default="ingested"),
        sa.Column("file_path", sa.String(512)),
    )
    op.create_index(
        "ix_sanctions_list_versions_source_fetched",
        "sanctions_list_versions",
        ["source", "fetched_at"],
    )

    op.create_table(
        "sanctions_entities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uid", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default="ofac_sdn"),
        sa.Column("sdn_type", sa.String(32)),
        sa.Column("primary_name", sa.Text(), nullable=False),
        sa.Column("programs", ARRAY(sa.Text())),
        sa.Column("remarks", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "first_seen_version_id", sa.Integer(), sa.ForeignKey("sanctions_list_versions.id")
        ),
        sa.Column(
            "last_seen_version_id", sa.Integer(), sa.ForeignKey("sanctions_list_versions.id")
        ),
        sa.Column("raw", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source", "uid", name="uq_sanctions_entities_source_uid"),
    )
    op.create_index("ix_sanctions_entities_is_active", "sanctions_entities", ["is_active"])

    op.create_table(
        "sanctions_names",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "entity_uid",
            sa.Integer(),
            sa.ForeignKey("sanctions_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name_type", sa.String(16), nullable=False),
        sa.Column("aka_type", sa.String(16)),
        sa.Column("strength", sa.String(8), nullable=False, server_default="strong"),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("normalized", sa.Text(), nullable=False),
        sa.Column("tokens", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("phonetic", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
    )
    op.create_index(
        "ix_sanctions_names_tokens", "sanctions_names", ["tokens"], postgresql_using="gin"
    )
    op.execute(
        "CREATE INDEX ix_sanctions_names_normalized_trgm ON sanctions_names "
        "USING gin (normalized gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_sanctions_names_embedding_hnsw ON sanctions_names "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )

    op.create_table(
        "sanctions_identifiers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "entity_uid",
            sa.Integer(),
            sa.ForeignKey("sanctions_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("id_type", sa.String(255), nullable=False),
        sa.Column("id_number", sa.Text(), nullable=False),
        sa.Column("id_country", sa.String(128)),
        sa.Column("issue_date", sa.Date()),
        sa.Column("expiry_date", sa.Date()),
    )
    op.create_index("ix_sanctions_identifiers_id_number", "sanctions_identifiers", ["id_number"])

    op.create_table(
        "sanctions_dobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "entity_uid",
            sa.Integer(),
            sa.ForeignKey("sanctions_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date_of_birth", sa.Date()),
        sa.Column("year_only", sa.Integer()),
        sa.Column("dob_text", sa.String(128)),
    )

    op.create_table(
        "sanctions_nationalities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "entity_uid",
            sa.Integer(),
            sa.ForeignKey("sanctions_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("country", sa.String(128), nullable=False),
    )

    op.create_table(
        "sanctions_addresses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "entity_uid",
            sa.Integer(),
            sa.ForeignKey("sanctions_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("address1", sa.String(255)),
        sa.Column("address2", sa.String(255)),
        sa.Column("city", sa.String(128)),
        sa.Column("state_province", sa.String(128)),
        sa.Column("postal_code", sa.String(32)),
        sa.Column("country", sa.String(128)),
        sa.Column("raw", sa.Text()),
    )

    op.create_table(
        "sanctions_changes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "version_id",
            sa.Integer(),
            sa.ForeignKey("sanctions_list_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_uid", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("change_type", sa.String(16), nullable=False),
        sa.Column("diff", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_sanctions_changes_version_type",
        "sanctions_changes",
        ["version_id", "change_type"],
    )


def downgrade() -> None:
    op.drop_table("sanctions_changes")
    op.drop_table("sanctions_addresses")
    op.drop_table("sanctions_nationalities")
    op.drop_table("sanctions_dobs")
    op.drop_table("sanctions_identifiers")
    op.drop_index("ix_sanctions_names_embedding_hnsw", table_name="sanctions_names")
    op.drop_index("ix_sanctions_names_normalized_trgm", table_name="sanctions_names")
    op.drop_index("ix_sanctions_names_tokens", table_name="sanctions_names")
    op.drop_table("sanctions_names")
    op.drop_index("ix_sanctions_entities_is_active", table_name="sanctions_entities")
    op.drop_table("sanctions_entities")
    op.drop_index("ix_sanctions_list_versions_source_fetched", table_name="sanctions_list_versions")
    op.drop_table("sanctions_list_versions")
