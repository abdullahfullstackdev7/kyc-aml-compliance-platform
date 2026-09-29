"""End-to-end test of POST /api/v1/screening/search against the real, loaded
OFAC SDN data. Requires the `postgres` service from docker-compose.yml to be
running with migrations applied and the sanctions ingestion pipeline having
run at least once (see dataset/README.md).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from backend.app.core.config import get_settings
from backend.app.models.sanctions import SanctionsEntity


@pytest.fixture(scope="module")
def client():
    settings = get_settings()
    try:
        engine = create_engine(settings.sync_database_url())
        with engine.connect() as conn:
            has_data = conn.execute(select(SanctionsEntity.id).limit(1)).first() is not None
        if not has_data:
            pytest.skip("sanctions_entities is empty; run the ingestion pipeline first")
    except Exception as exc:  # noqa: BLE001 - environment guard, any connection failure skips
        pytest.skip(f"Postgres not reachable for this test: {exc}")

    from backend.app.main import app

    return TestClient(app)


def test_search_returns_ranked_explained_hits(client):
    response = client.post("/api/v1/screening/search", json={"full_name": "Ayman Zawahiri"})
    assert response.status_code == 200

    data = response.json()
    assert data["candidate_count"] > 0
    assert len(data["hits"]) > 0

    scores = [hit["scores"]["composite_score"] for hit in data["hits"]]
    assert scores == sorted(scores, reverse=True)

    top_hit = data["hits"][0]
    assert "matched_name" in top_hit
    assert "primary_name" in top_hit
    assert set(top_hit["retrieval_methods"]) <= {"token", "trigram", "vector", "phonetic"}
    assert "adjustments" in top_hit["scores"]


def test_search_respects_top_n(client):
    response = client.post(
        "/api/v1/screening/search", json={"full_name": "Mohammed Ali", "top_n": 3}
    )
    assert response.status_code == 200
    assert len(response.json()["hits"]) <= 3


def test_search_with_secondary_attributes(client):
    response = client.post(
        "/api/v1/screening/search",
        json={"full_name": "Ayman Zawahiri", "date_of_birth": "1951-06-19"},
    )
    assert response.status_code == 200
    data = response.json()
    top_hit = data["hits"][0]
    assert top_hit["scores"]["composite_score"] >= 90


def test_search_rejects_empty_name(client):
    response = client.post("/api/v1/screening/search", json={"full_name": ""})
    assert response.status_code == 422


def test_health_live(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
