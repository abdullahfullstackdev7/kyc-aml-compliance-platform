"""llm_cache round trip against the real Postgres instance."""

from __future__ import annotations

from sqlalchemy import delete

from backend.app.models.governance import LlmCache
from backend.app.services.llm import cache


def test_cache_key_is_deterministic_regardless_of_dict_key_order():
    a = cache.cache_key("case_summary", "v1", {"alias": "x", "tier": "review"})
    b = cache.cache_key("case_summary", "v1", {"tier": "review", "alias": "x"})
    assert a == b


def test_cache_key_differs_by_purpose_and_version():
    payload = {"alias": "x"}
    assert cache.cache_key("case_summary", "v1", payload) != cache.cache_key(
        "decision_rationale_draft", "v1", payload
    )
    assert cache.cache_key("case_summary", "v1", payload) != cache.cache_key(
        "case_summary", "v2", payload
    )


def test_get_cached_returns_none_when_absent(db_session):
    assert cache.get_cached(db_session, "nonexistent-key-xyz") is None


def test_store_and_get_cached_round_trip(db_session):
    key = cache.cache_key("case_summary", "v1", {"alias": "round-trip-test"})
    db_session.execute(delete(LlmCache).where(LlmCache.cache_key == key))
    db_session.commit()

    cache.store_cached(
        db_session,
        key=key,
        purpose="case_summary",
        prompt_version="v1",
        response={"summary": "stored"},
    )
    db_session.commit()

    assert cache.get_cached(db_session, key) == {"summary": "stored"}

    db_session.execute(delete(LlmCache).where(LlmCache.cache_key == key))
    db_session.commit()


def test_store_cached_is_idempotent_for_the_same_key(db_session):
    key = cache.cache_key("case_summary", "v1", {"alias": "idempotent-test"})
    db_session.execute(delete(LlmCache).where(LlmCache.cache_key == key))
    db_session.commit()

    cache.store_cached(
        db_session, key=key, purpose="case_summary", prompt_version="v1", response={"summary": "first"}
    )
    cache.store_cached(
        db_session, key=key, purpose="case_summary", prompt_version="v1", response={"summary": "second"}
    )
    db_session.commit()

    assert cache.get_cached(db_session, key) == {"summary": "first"}

    db_session.execute(delete(LlmCache).where(LlmCache.cache_key == key))
    db_session.commit()
