"""Token document-frequency and IDF statistics, recomputed at ingest.

IDF = ln(N / df), where N is the total number of sanctions names and df is how
many of them contain the token. Rare tokens (surnames, transliterated given
names) score high; common tokens (residual honorifics, single letters, "AL")
approach zero and contribute little to candidate ranking or scoring. See
PROJECT_PLAN.md Phase 3.2 ("rare tokens weighted by IDF computed at ingest").
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def refresh_token_idf(session: Session) -> int:
    """Recompute sanctions_token_stats from the current sanctions_names table.

    Returns the number of distinct tokens stored.
    """
    session.execute(text("TRUNCATE TABLE sanctions_token_stats"))
    session.execute(
        text(
            """
            WITH total AS (
                SELECT count(*)::float AS n FROM sanctions_names
            ),
            freq AS (
                SELECT unnest(tokens) AS token, count(*) AS df
                FROM sanctions_names
                GROUP BY unnest(tokens)
            )
            INSERT INTO sanctions_token_stats (token, document_frequency, idf)
            SELECT freq.token, freq.df, ln(total.n / freq.df)
            FROM freq, total
            WHERE freq.token IS NOT NULL AND freq.token != ''
            """
        )
    )
    count: int = session.execute(text("SELECT count(*) FROM sanctions_token_stats")).scalar_one()
    return count
