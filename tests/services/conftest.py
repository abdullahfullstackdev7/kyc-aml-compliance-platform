"""Shared fixtures for service-layer tests that need read access to the
running Postgres instance (e.g. country_risk lookups). Skips gracefully if
Postgres is not reachable, consistent with tests/integration/test_sdn_loader.py.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_settings


@pytest.fixture
def db_session():
    settings = get_settings()
    try:
        engine = create_engine(settings.sync_database_url())
        engine.connect().close()
    except Exception as exc:  # noqa: BLE001 - environment guard, any connection failure skips
        pytest.skip(f"Postgres not reachable for this test: {exc}")

    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()
