"""Router failover tests with mocked providers, per PROJECT_PLAN.md Phase
10.1 ("LLM router failover (mocked providers)"). No real Groq/Gemini calls
or Redis are involved: quota and runtime_settings are monkeypatched so this
is a pure unit test of the failover state machine in router.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.app.services.llm import router
from backend.app.services.llm.provider import LLMResult, LLMTransientError


@pytest.fixture(autouse=True)
def _stub_quota_and_settings(monkeypatch):
    monkeypatch.setattr(router.quota, "has_headroom", lambda name: True)
    monkeypatch.setattr(router.quota, "circuit_open", lambda name: False)
    monkeypatch.setattr(router.quota, "record_failure", MagicMock())
    monkeypatch.setattr(router.quota, "record_success", MagicMock())
    monkeypatch.setattr(router.quota, "record_usage", MagicMock())
    monkeypatch.setattr(router.runtime_settings, "is_enabled", lambda: True)
    monkeypatch.setattr(router.runtime_settings, "get_primary_provider", lambda: "groq")
    monkeypatch.setattr(router.time, "sleep", lambda _seconds: None)


def _fake_provider(result=None, error=None, fail_times=0):
    provider = MagicMock()
    calls = {"count": 0}

    def generate_json(**_kwargs):
        calls["count"] += 1
        if calls["count"] <= fail_times:
            raise error or LLMTransientError("timeout")
        if error and fail_times == 0:
            raise error
        return result

    provider.generate_json.side_effect = generate_json
    provider.calls = calls
    return provider


def test_disabled_returns_fallback_without_calling_any_provider(monkeypatch):
    monkeypatch.setattr(router.runtime_settings, "is_enabled", lambda: False)
    get_provider = MagicMock()
    monkeypatch.setattr(router, "get_provider", get_provider)

    outcome = router.generate_json(
        purpose="case_summary", system_prompt="s", user_payload={}, max_tokens=100
    )

    assert outcome.status == "fallback"
    assert outcome.provider is None
    get_provider.assert_not_called()


def test_primary_success_records_usage_and_returns_ok(monkeypatch):
    result = LLMResult(data={"summary": "ok"}, prompt_tokens=10, completion_tokens=5, model="m")
    monkeypatch.setattr(router, "get_provider", lambda name: _fake_provider(result=result))

    outcome = router.generate_json(
        purpose="case_summary", system_prompt="s", user_payload={}, max_tokens=100
    )

    assert outcome.status == "ok"
    assert outcome.provider == "groq"
    assert outcome.result is result
    router.quota.record_usage.assert_called_once_with("groq", 15)
    router.quota.record_success.assert_called_once_with("groq")


def test_primary_failure_fails_over_to_secondary(monkeypatch):
    result = LLMResult(data={"summary": "ok"}, prompt_tokens=1, completion_tokens=1, model="m")

    def get_provider(name):
        if name == "groq":
            return _fake_provider(error=RuntimeError("groq is down"))
        return _fake_provider(result=result)

    monkeypatch.setattr(router, "get_provider", get_provider)

    outcome = router.generate_json(
        purpose="case_summary", system_prompt="s", user_payload={}, max_tokens=100
    )

    assert outcome.status == "ok"
    assert outcome.provider == "gemini"
    router.quota.record_failure.assert_called_once_with("groq")


def test_both_providers_failing_returns_template_fallback(monkeypatch):
    monkeypatch.setattr(
        router, "get_provider", lambda name: _fake_provider(error=RuntimeError("down"))
    )

    outcome = router.generate_json(
        purpose="case_summary", system_prompt="s", user_payload={}, max_tokens=100
    )

    assert outcome.status == "fallback"
    assert outcome.provider is None
    assert router.quota.record_failure.call_count == 2


def test_provider_without_headroom_is_skipped(monkeypatch):
    monkeypatch.setattr(router.quota, "has_headroom", lambda name: name != "groq")
    result = LLMResult(data={"summary": "ok"}, prompt_tokens=1, completion_tokens=1, model="m")
    get_provider = MagicMock(side_effect=lambda name: _fake_provider(result=result))
    monkeypatch.setattr(router, "get_provider", get_provider)

    outcome = router.generate_json(
        purpose="case_summary", system_prompt="s", user_payload={}, max_tokens=100
    )

    assert outcome.provider == "gemini"
    get_provider.assert_called_once_with("gemini")


def test_transient_error_is_retried_once_then_succeeds(monkeypatch):
    result = LLMResult(data={"summary": "ok"}, prompt_tokens=1, completion_tokens=1, model="m")
    provider = _fake_provider(result=result, fail_times=1)
    monkeypatch.setattr(router, "get_provider", lambda name: provider)

    outcome = router.generate_json(
        purpose="case_summary", system_prompt="s", user_payload={}, max_tokens=100
    )

    assert outcome.status == "ok"
    assert provider.calls["count"] == 2
