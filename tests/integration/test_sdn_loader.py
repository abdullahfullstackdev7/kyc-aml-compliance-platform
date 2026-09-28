"""Integration test for the sanctions loader against a real Postgres database.

Requires the `postgres` service from docker-compose.yml to be running
(`make up` or `docker compose up -d postgres`) with migrations applied
(`make migrate`). Uses a dedicated source name so it never touches real
`ofac_sdn` data.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_settings
from backend.app.models.sanctions import (
    SanctionsChange,
    SanctionsEntity,
    SanctionsListVersion,
)
from backend.app.services.sanctions.loader import load_sdn_snapshot
from backend.app.services.sanctions.ofac_parser import SdnEntry

TEST_SOURCE = "test_fixture_source"


@pytest.fixture
def db_session():
    settings = get_settings()
    try:
        engine = create_engine(settings.sync_database_url())
        engine.connect().close()
    except Exception as exc:  # noqa: BLE001 - environment guard, any connection failure skips
        pytest.skip(f"Postgres not reachable for integration test: {exc}")

    Session = sessionmaker(bind=engine)
    session = Session()
    yield session

    session.rollback()
    session.execute(
        delete(SanctionsChange).where(
            SanctionsChange.entity_uid.in_(
                select(SanctionsEntity.uid).where(SanctionsEntity.source == TEST_SOURCE)
            )
        )
    )
    session.execute(delete(SanctionsEntity).where(SanctionsEntity.source == TEST_SOURCE))
    session.execute(delete(SanctionsListVersion).where(SanctionsListVersion.source == TEST_SOURCE))
    session.commit()
    session.close()


def _make_entry(uid: int, name: str) -> SdnEntry:
    return SdnEntry(
        uid=uid,
        first_name=None,
        last_name=name,
        title=None,
        sdn_type="Entity",
        remarks=None,
        programs=["TEST"],
    )


def _make_version(session, label: str) -> int:
    version = SanctionsListVersion(
        source=TEST_SOURCE, sha256=f"sha-{label}", status="ingested", record_count=0
    )
    session.add(version)
    session.flush()
    return version.id


def test_first_load_marks_all_entities_added(db_session):
    version_id = _make_version(db_session, "v1")
    entries = [_make_entry(90001, "ALPHA CORP"), _make_entry(90002, "BETA CORP")]
    name_rows = {
        90001: [
            {
                "name_type": "primary",
                "aka_type": None,
                "strength": "strong",
                "full_name": "ALPHA CORP",
                "normalized": "ALPHA SUFFIXCORP",
                "tokens": ["ALPHA", "SUFFIXCORP"],
                "phonetic": [],
                "embedding": None,
            }
        ],
        90002: [
            {
                "name_type": "primary",
                "aka_type": None,
                "strength": "strong",
                "full_name": "BETA CORP",
                "normalized": "BETA SUFFIXCORP",
                "tokens": ["BETA", "SUFFIXCORP"],
                "phonetic": [],
                "embedding": None,
            }
        ],
    }

    stats = load_sdn_snapshot(
        db_session,
        source=TEST_SOURCE,
        version_id=version_id,
        entries=entries,
        name_rows_by_uid=name_rows,
    )
    db_session.commit()

    assert stats.added == 2
    assert stats.removed == 0
    assert stats.total_active == 2


def test_second_load_detects_removed_and_added(db_session):
    v1 = _make_version(db_session, "v1")
    entries_v1 = [_make_entry(90001, "ALPHA CORP"), _make_entry(90002, "BETA CORP")]
    name_rows_v1 = {
        90001: [
            {
                "name_type": "primary",
                "aka_type": None,
                "strength": "strong",
                "full_name": "ALPHA CORP",
                "normalized": "ALPHA SUFFIXCORP",
                "tokens": ["ALPHA", "SUFFIXCORP"],
                "phonetic": [],
                "embedding": None,
            }
        ],
        90002: [
            {
                "name_type": "primary",
                "aka_type": None,
                "strength": "strong",
                "full_name": "BETA CORP",
                "normalized": "BETA SUFFIXCORP",
                "tokens": ["BETA", "SUFFIXCORP"],
                "phonetic": [],
                "embedding": None,
            }
        ],
    }
    load_sdn_snapshot(
        db_session,
        source=TEST_SOURCE,
        version_id=v1,
        entries=entries_v1,
        name_rows_by_uid=name_rows_v1,
    )
    db_session.commit()

    v2 = _make_version(db_session, "v2")
    entries_v2 = [_make_entry(90001, "ALPHA CORP"), _make_entry(90003, "GAMMA CORP")]
    name_rows_v2 = {
        90001: name_rows_v1[90001],
        90003: [
            {
                "name_type": "primary",
                "aka_type": None,
                "strength": "strong",
                "full_name": "GAMMA CORP",
                "normalized": "GAMMA SUFFIXCORP",
                "tokens": ["GAMMA", "SUFFIXCORP"],
                "phonetic": [],
                "embedding": None,
            }
        ],
    }
    stats = load_sdn_snapshot(
        db_session,
        source=TEST_SOURCE,
        version_id=v2,
        entries=entries_v2,
        name_rows_by_uid=name_rows_v2,
    )
    db_session.commit()

    assert stats.added == 1  # GAMMA CORP
    assert stats.removed == 1  # BETA CORP
    assert stats.unchanged == 1  # ALPHA CORP
    assert stats.total_active == 2

    beta = db_session.execute(
        select(SanctionsEntity).where(
            SanctionsEntity.source == TEST_SOURCE, SanctionsEntity.uid == 90002
        )
    ).scalar_one()
    assert beta.is_active is False
