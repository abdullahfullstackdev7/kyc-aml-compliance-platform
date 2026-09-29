"""Redis-backed quota headroom, circuit breaker and runtime settings,
against the real Redis instance used by this dev environment. Each test
uses a unique-ish provider-name-adjacent Redis key namespace by clearing
its own keys before and after, since quota buckets are time-windowed."""

from __future__ import annotations

import redis
import pytest

from backend.app.core.config import get_settings
from backend.app.services.llm import quota, runtime_settings


@pytest.fixture
def redis_client():
    client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        client.ping()
    except Exception as exc:  # noqa: BLE001 - environment guard
        pytest.skip(f"Redis not reachable: {exc}")
    yield client


@pytest.fixture(autouse=True)
def _clear_quota_keys(redis_client):
    def _clear():
        for pattern in ("llm:quota:test-provider:*", "llm:cb:test-provider:*", "llm:settings:*"):
            for key in redis_client.scan_iter(pattern):
                redis_client.delete(key)

    _clear()
    yield
    _clear()


def test_has_headroom_true_when_no_usage_recorded(redis_client):
    assert quota.has_headroom("test-provider") is True


def test_record_usage_is_reflected_in_headroom_snapshot(redis_client):
    quota.record_usage("test-provider", total_tokens=500)
    snapshot = quota.quota_headroom("test-provider")
    assert snapshot["rpm_used"] == 1
    assert snapshot["tpm_used"] == 500


def test_circuit_opens_after_configured_failure_count(redis_client):
    settings = get_settings()
    assert quota.circuit_open("test-provider") is False
    for _ in range(settings.llm_circuit_breaker_failures):
        quota.record_failure("test-provider")
    assert quota.circuit_open("test-provider") is True


def test_record_success_clears_failure_count(redis_client):
    quota.record_failure("test-provider")
    quota.record_success("test-provider")
    # one more failure alone should not open the breaker if the counter reset
    quota.record_failure("test-provider")
    assert quota.circuit_open("test-provider") is False


def test_runtime_settings_default_to_config_until_overridden(redis_client):
    settings = get_settings()
    assert runtime_settings.get_primary_provider() == settings.llm_primary
    assert runtime_settings.is_enabled() == settings.llm_enabled

    runtime_settings.set_primary_provider("gemini")
    runtime_settings.set_enabled(False)
    assert runtime_settings.get_primary_provider() == "gemini"
    assert runtime_settings.is_enabled() is False


def test_set_primary_provider_rejects_unknown_provider(redis_client):
    with pytest.raises(ValueError):
        runtime_settings.set_primary_provider("not-a-real-provider")
