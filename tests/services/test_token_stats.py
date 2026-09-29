"""Token IDF stats recomputation (PROJECT_PLAN.md Phase 3.2), against the
real Postgres instance. Safe to run: refresh_token_idf recomputes
sanctions_token_stats purely from sanctions_names (which this test does not
touch), so it is idempotent and does not lose data other tests depend on."""

from __future__ import annotations

from sqlalchemy import text

from backend.app.services.screening.token_stats import refresh_token_idf


def test_refresh_token_idf_returns_the_row_count_it_wrote(db_session):
    count = refresh_token_idf(db_session)
    db_session.commit()

    actual = db_session.execute(text("SELECT count(*) FROM sanctions_token_stats")).scalar_one()
    assert count == actual
    assert count > 0


def test_refresh_token_idf_produces_higher_idf_for_rarer_tokens(db_session):
    refresh_token_idf(db_session)
    db_session.commit()

    rows = db_session.execute(
        text(
            "SELECT token, document_frequency, idf FROM sanctions_token_stats "
            "ORDER BY document_frequency ASC LIMIT 1"
        )
    ).first()
    common = db_session.execute(
        text(
            "SELECT idf FROM sanctions_token_stats ORDER BY document_frequency DESC LIMIT 1"
        )
    ).scalar_one()

    assert rows is not None
    rare_idf = rows[2]
    assert rare_idf >= common
