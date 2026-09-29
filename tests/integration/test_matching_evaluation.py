"""Matching evaluation CI gate (PROJECT_PLAN.md Phase 10.1.4): "harness from
Phase 3.7 runs in CI on a fixed seed; build fails if recall drops below 98
percent." Runs the real hybrid screening pipeline against the fixed-seed
synthetic ground truth set (dataset/scripts/generate_ground_truth.py
--seed 42, the script's default) at the clear/review boundary threshold
(72, the score at or below which the system would not alert at all), since
that is the floor where a missed true match is a missed match, not a lower
tier assignment.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_settings
from backend.app.services.screening.evaluate import compute_metrics, load_ground_truth, run_hybrid_queries

GROUND_TRUTH_PATH = Path("dataset/synthetic/ground_truth_matches.csv")
RECALL_FLOOR = 0.98
ALERT_THRESHOLD = 72  # DEFAULT_THRESHOLDS["clear_max"] in routing.py


@pytest.fixture
def db_session():
    settings = get_settings()
    try:
        engine = create_engine(settings.sync_database_url())
        engine.connect().close()
    except Exception as exc:  # noqa: BLE001 - environment guard
        pytest.skip(f"Postgres not reachable: {exc}")
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


def test_recall_at_alert_threshold_meets_the_98_percent_floor(db_session):
    if not GROUND_TRUTH_PATH.exists():
        pytest.skip(
            f"{GROUND_TRUTH_PATH} not present - run "
            "`uv run python dataset/scripts/generate_ground_truth.py --seed 42` first "
            "(CI runs this before the test suite; see .github/workflows/ci.yml)"
        )

    rows = load_ground_truth(GROUND_TRUTH_PATH)
    true_match_rows = [r for r in rows if r.label == "true_match"]
    if not true_match_rows:
        pytest.skip("ground truth set has no true_match rows to measure recall against")

    results = run_hybrid_queries(db_session, rows)
    metrics = compute_metrics(results, [ALERT_THRESHOLD])[0]

    assert metrics.recall >= RECALL_FLOOR, (
        f"Recall at threshold {ALERT_THRESHOLD} dropped to {metrics.recall:.3f} "
        f"(floor is {RECALL_FLOOR}); {metrics.false_negatives} of "
        f"{len(true_match_rows)} true matches were missed or misassigned"
    )
