"""Validates the Phase 3.6 performance target: single screening p95 under
300 ms, against the real loaded OFAC SDN data. Excludes the one-time
embedding model load from the measured window (steady-state latency, matching
how the target is meant to be read: per-request cost once a worker is warm).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_settings
from backend.app.models.sanctions import SanctionsEntity
from backend.app.services.screening.embeddings import embed_text
from backend.app.services.screening.service import ScreeningQuery, screen_name

P95_TARGET_MS = 300

BENCHMARK_NAMES = [
    "Ayman Zawahri",
    "Mohammed Ali",
    "Banco Nacional",
    "Vladimir Putin",
    "John Smith",
    "Abdul Rahman",
    "Kim Jong Un",
    "Osama bin Laden",
    "Aero Caribbean",
    "Hassan Nasrallah",
    "Anglo Caribbean",
    "Ahmad Fuad Salim",
    "Maria Garcia",
    "Chen Wei",
    "Ali Hassan",
    "Mahmoud Abbas",
    "Ibrahim Khalil",
    "Yusuf Ahmed",
    "Sara Ahmadi",
    "Mohammad Rezaei",
    "Fatima Zahra",
    "Boutique La Maison",
    "Casa de Cuba",
    "Cecoex SA",
    "Anwar Sadat",
    "Saddam Hussein",
    "Muammar Gaddafi",
    "Bashar Assad",
    "Kim Il Sung",
    "Pol Pot",
]


@pytest.fixture(scope="module")
def session():
    settings = get_settings()
    try:
        engine = create_engine(settings.sync_database_url())
        with engine.connect() as conn:
            has_data = conn.execute(select(SanctionsEntity.id).limit(1)).first() is not None
        if not has_data:
            pytest.skip("sanctions_entities is empty; run the ingestion pipeline first")
    except Exception as exc:  # noqa: BLE001 - environment guard, any connection failure skips
        pytest.skip(f"Postgres not reachable for this test: {exc}")

    Session = sessionmaker(bind=engine)
    with Session() as s:
        yield s


def test_single_screening_p95_under_300ms(session):
    embed_text("warmup")  # load the embedding model once, outside the measured window

    durations = []
    for name in BENCHMARK_NAMES:
        result = screen_name(session, ScreeningQuery(full_name=name))
        durations.append(result.duration_ms)

    durations.sort()
    p95 = durations[int(len(durations) * 0.95)]

    assert p95 < P95_TARGET_MS, f"p95 latency {p95:.1f}ms exceeds the {P95_TARGET_MS}ms target"
