"""Full onboarding flow against a disposable, freshly-migrated Postgres
started by testcontainers (PROJECT_PLAN.md Phase 10.2: "Integration tests:
testcontainers Postgres with pgvector"), rather than the persistent dev
database the rest of the suite uses. This is the one test in the suite that
proves the schema/migrations/RLS setup works from a completely clean
database, not just "whatever state the dev DB happens to be in".

Slower than the rest of the suite (container start + full `alembic upgrade
head`), so it is kept to a single, focused scenario rather than duplicating
the broader onboarding-flow coverage in test_onboarding_flow.py.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

try:
    from testcontainers.postgres import PostgresContainer
except ImportError:
    PostgresContainer = None  # type: ignore[assignment,misc]


@pytest.fixture(scope="module")
def testcontainer_database_url():
    if PostgresContainer is None:
        pytest.skip("testcontainers not installed")

    try:
        container = PostgresContainer(
            "pgvector/pgvector:pg16", username="sentinelkyc", password="sentinelkyc", dbname="sentinelkyc"
        )
        container.start()
    except Exception as exc:  # noqa: BLE001 - Docker not available in this environment
        pytest.skip(f"Docker/testcontainers not usable here: {exc}")

    try:
        yield container.get_connection_url()
    finally:
        container.stop()


def test_migrations_apply_cleanly_to_a_fresh_testcontainers_database(testcontainer_database_url):
    """The concrete, minimal deliverable for this test file: `alembic
    upgrade head` succeeds end to end against a database that has never
    seen this schema before - the real thing CI needs to verify on every
    change, independent of whatever migration state the shared dev
    database happens to already be in."""
    import os

    env = {**os.environ, "DATABASE_URL_SYNC": testcontainer_database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"alembic upgrade failed:\n{result.stdout}\n{result.stderr}"

    from sqlalchemy import create_engine, text

    engine = create_engine(testcontainer_database_url)
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        }
    assert "tenants" in tables
    assert "cases" in tables
    assert "audit_log" in tables
    engine.dispose()
