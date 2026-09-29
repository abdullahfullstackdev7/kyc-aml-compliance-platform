"""Cache -> router -> template-fallback orchestration in llm/service.py,
against the real Postgres instance (llm_cache/llm_calls need real tables),
with router.generate_json monkeypatched so no network call is made."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import delete, select

from backend.app.models.governance import LlmCache, LlmCall
from backend.app.services.llm import cache as cache_module
from backend.app.services.llm import prompts, router as router_module
from backend.app.services.llm import service
from backend.app.services.llm.provider import LLMResult
from backend.app.services.llm.router import RouterResult

FAKE_CASE = SimpleNamespace(tenant_id=None, id=None)


def _cleanup(db_session, payload):
    key = cache_module.cache_key("case_summary", prompts.CASE_SUMMARY_VERSION, payload)
    db_session.execute(delete(LlmCache).where(LlmCache.cache_key == key))
    db_session.execute(delete(LlmCall).where(LlmCall.purpose == "case_summary"))
    db_session.commit()


def test_cache_hit_skips_the_router(db_session, monkeypatch):
    payload = {"alias": "case-cache-hit", "tier": "review", "hits": []}
    _cleanup(db_session, payload)

    key = cache_module.cache_key("case_summary", prompts.CASE_SUMMARY_VERSION, payload)
    cache_module.store_cached(
        db_session,
        key=key,
        purpose="case_summary",
        prompt_version=prompts.CASE_SUMMARY_VERSION,
        response={"summary": "cached", "key_factors": [], "suggested_action": "clear", "confidence": "low"},
    )
    db_session.commit()

    def _fail_if_called(**_kwargs):
        raise AssertionError("router should not be called on a cache hit")

    monkeypatch.setattr(router_module, "generate_json", _fail_if_called)

    result = service.generate_case_summary(db_session, FAKE_CASE, payload)
    db_session.commit()

    assert result["summary"] == "cached"
    call = db_session.execute(
        select(LlmCall).where(LlmCall.purpose == "case_summary")
    ).scalar_one()
    assert call.status == "cached"

    _cleanup(db_session, payload)


def test_router_success_is_cached_and_logged(db_session, monkeypatch):
    payload = {"alias": "case-router-ok", "tier": "high_risk", "hits": []}
    _cleanup(db_session, payload)

    llm_result = LLMResult(
        data={"summary": "from provider", "key_factors": ["f1"], "suggested_action": "escalate", "confidence": "high"},
        prompt_tokens=20,
        completion_tokens=10,
        model="test-model",
    )
    monkeypatch.setattr(
        service.router,
        "generate_json",
        lambda **_kwargs: RouterResult(result=llm_result, provider="groq", status="ok", latency_ms=5),
    )

    result = service.generate_case_summary(db_session, FAKE_CASE, payload)
    db_session.commit()

    assert result["summary"] == "from provider"
    call = db_session.execute(
        select(LlmCall).where(LlmCall.purpose == "case_summary")
    ).scalar_one()
    assert call.status == "success"
    assert call.provider == "groq"
    assert call.prompt_tokens == 20

    key = cache_module.cache_key("case_summary", prompts.CASE_SUMMARY_VERSION, payload)
    assert cache_module.get_cached(db_session, key) is not None

    _cleanup(db_session, payload)


def test_router_fallback_uses_template_and_is_not_cached(db_session, monkeypatch):
    payload = {"alias": "case-fallback", "tier": "clear", "hits": [{"name": "Jane Doe", "score": 88}]}
    _cleanup(db_session, payload)

    monkeypatch.setattr(
        service.router,
        "generate_json",
        lambda **_kwargs: RouterResult(result=None, provider=None, status="fallback", latency_ms=1),
    )

    result = service.generate_case_summary(db_session, FAKE_CASE, payload)
    db_session.commit()

    assert "Jane Doe" in result["summary"]
    assert result["source"] == "Automated summary (assistant unavailable)"

    call = db_session.execute(
        select(LlmCall).where(LlmCall.purpose == "case_summary")
    ).scalar_one()
    assert call.status == "fallback"

    key = cache_module.cache_key("case_summary", prompts.CASE_SUMMARY_VERSION, payload)
    assert cache_module.get_cached(db_session, key) is None

    _cleanup(db_session, payload)


def test_decision_rationale_draft_includes_proposed_decision_in_payload(db_session, monkeypatch):
    payload = {"alias": "case-rationale", "tier": "review", "hits": []}
    db_session.execute(delete(LlmCall).where(LlmCall.purpose == "decision_rationale_draft"))
    db_session.commit()

    captured = {}

    def fake_generate_json(**kwargs):
        captured.update(kwargs)
        return RouterResult(result=None, provider=None, status="fallback", latency_ms=1)

    monkeypatch.setattr(service.router, "generate_json", fake_generate_json)

    service.generate_decision_rationale_draft(db_session, FAKE_CASE, payload, "approve")
    db_session.commit()

    assert captured["user_payload"]["proposed_decision"] == "approve"
    assert captured["purpose"] == "decision_rationale_draft"

    key = cache_module.cache_key(
        "decision_rationale_draft",
        prompts.DECISION_RATIONALE_VERSION,
        {**payload, "proposed_decision": "approve"},
    )
    db_session.execute(delete(LlmCache).where(LlmCache.cache_key == key))
    db_session.execute(delete(LlmCall).where(LlmCall.purpose == "decision_rationale_draft"))
    db_session.commit()
