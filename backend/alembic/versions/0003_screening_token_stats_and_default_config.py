"""Add sanctions token IDF statistics and seed default risk config / country risk.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_THRESHOLDS = {
    "clear_max": 72,
    "review_max": 89,
    "high_risk_min": 90,
}

DEFAULT_WEIGHTS = {
    "token_set": 0.35,
    "token_sort": 0.25,
    "jaro_winkler": 0.25,
    "embedding": 0.15,
    "dob_exact_bonus": 10,
    "dob_year_bonus": 5,
    "dob_conflict_penalty": -25,
    "nationality_match_bonus": 5,
    "nationality_conflict_penalty": -10,
    "entity_type_mismatch_penalty": -30,
    "weak_aka_cap": 80,
    "rare_token_missing_penalty": 8,
    "rare_token_missing_cap": 25,
    "rare_idf_threshold": 2.0,
}

# Illustrative starter set only; not a live sync with the FATF plenary outcomes.
# Refresh from fatf-gafi.org before relying on this for production decisioning
# (see PROJECT_PLAN.md section 5.1, fatf_jurisdictions.csv).
COUNTRY_RISK_SEED = [
    (
        "Iran",
        "high",
        "Historically FATF-listed high-risk jurisdiction subject to a call for action.",
    ),
    (
        "North Korea",
        "high",
        "Historically FATF-listed high-risk jurisdiction subject to a call for action.",
    ),
    (
        "Myanmar",
        "high",
        "Historically FATF-listed high-risk jurisdiction subject to a call for action.",
    ),
    ("Syria", "high", "Comprehensive sanctions program jurisdiction."),
    ("Cuba", "high", "Comprehensive sanctions program jurisdiction."),
    ("Afghanistan", "medium", "Historically under FATF increased monitoring."),
    ("Yemen", "medium", "Historically under FATF increased monitoring."),
    ("South Sudan", "medium", "Historically under FATF increased monitoring."),
    ("Panama", "medium", "Historically flagged for AML/CFT deficiencies."),
    ("United Arab Emirates", "medium", "Historically under FATF increased monitoring."),
    ("United States", "low", "FATF member; standard due diligence applies."),
    ("United Kingdom", "low", "FATF member; standard due diligence applies."),
    ("Canada", "low", "FATF member; standard due diligence applies."),
    ("Germany", "low", "FATF member; standard due diligence applies."),
    ("Japan", "low", "FATF member; standard due diligence applies."),
]


def upgrade() -> None:
    op.create_table(
        "sanctions_token_stats",
        sa.Column("token", sa.Text(), primary_key=True),
        sa.Column("document_frequency", sa.Integer(), nullable=False),
        sa.Column("idf", sa.Float(), nullable=False),
    )

    risk_config = sa.table(
        "risk_config",
        sa.column("tenant_id", sa.Integer()),
        sa.column("version", sa.Integer()),
        sa.column("thresholds", JSONB()),
        sa.column("weights", JSONB()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        risk_config,
        [
            {
                "tenant_id": None,
                "version": 1,
                "thresholds": DEFAULT_THRESHOLDS,
                "weights": DEFAULT_WEIGHTS,
                "is_active": True,
            }
        ],
    )

    country_risk = sa.table(
        "country_risk",
        sa.column("country", sa.String()),
        sa.column("risk_level", sa.String()),
        sa.column("rationale", sa.Text()),
    )
    op.bulk_insert(
        country_risk,
        [
            {"country": country, "risk_level": level, "rationale": rationale}
            for country, level, rationale in COUNTRY_RISK_SEED
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM country_risk")
    op.execute("DELETE FROM risk_config")
    op.drop_table("sanctions_token_stats")
