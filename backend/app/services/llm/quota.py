"""Per-provider quota headroom and circuit breaker, backed by Redis so
limits are shared across worker processes (same pattern as
backend/app/core/rate_limit.py and password_reset.py's use of Redis).
See PROJECT_PLAN.md Phase 6.2.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import redis

from backend.app.core.config import get_settings

CB_FAILURE_TTL_SECONDS = 60


@dataclass
class ProviderLimits:
    rpm: int
    rpd: int
    tpm: int


def redis_client() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url, decode_responses=True)


_redis_client = redis_client  # backward-compatible alias for in-module use


def _limits(provider: str) -> ProviderLimits:
    settings = get_settings()
    if provider == "groq":
        return ProviderLimits(rpm=settings.groq_rpm, rpd=settings.groq_rpd, tpm=settings.groq_tpm)
    return ProviderLimits(rpm=settings.gemini_rpm, rpd=settings.gemini_rpd, tpm=settings.gemini_tpm)


def _minute_bucket() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M")


def _day_bucket() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%d")


def has_headroom(provider: str) -> bool:
    """True if the provider has request/token headroom left for the current
    minute and day, per the configured free-tier limits."""
    client = _redis_client()
    limits = _limits(provider)
    minute, day = _minute_bucket(), _day_bucket()

    rpm_used = int(client.get(f"llm:quota:{provider}:rpm:{minute}") or 0)
    rpd_used = int(client.get(f"llm:quota:{provider}:rpd:{day}") or 0)
    tpm_used = int(client.get(f"llm:quota:{provider}:tpm:{minute}") or 0)

    return rpm_used < limits.rpm and rpd_used < limits.rpd and tpm_used < limits.tpm


def record_usage(provider: str, total_tokens: int) -> None:
    client = _redis_client()
    minute, day = _minute_bucket(), _day_bucket()

    pipe = client.pipeline()
    pipe.incr(f"llm:quota:{provider}:rpm:{minute}")
    pipe.expire(f"llm:quota:{provider}:rpm:{minute}", 120)
    pipe.incr(f"llm:quota:{provider}:rpd:{day}")
    pipe.expire(f"llm:quota:{provider}:rpd:{day}", 90000)
    pipe.incrby(f"llm:quota:{provider}:tpm:{minute}", total_tokens)
    pipe.expire(f"llm:quota:{provider}:tpm:{minute}", 120)
    pipe.execute()


def quota_headroom(provider: str) -> dict:
    """Live headroom for the admin quota view."""
    client = _redis_client()
    limits = _limits(provider)
    minute, day = _minute_bucket(), _day_bucket()
    rpm_used = int(client.get(f"llm:quota:{provider}:rpm:{minute}") or 0)
    rpd_used = int(client.get(f"llm:quota:{provider}:rpd:{day}") or 0)
    tpm_used = int(client.get(f"llm:quota:{provider}:tpm:{minute}") or 0)
    return {
        "rpm_used": rpm_used,
        "rpm_limit": limits.rpm,
        "rpd_used": rpd_used,
        "rpd_limit": limits.rpd,
        "tpm_used": tpm_used,
        "tpm_limit": limits.tpm,
        "circuit_open": circuit_open(provider),
    }


def circuit_open(provider: str) -> bool:
    return _redis_client().exists(f"llm:cb:{provider}:open") == 1


def record_failure(provider: str) -> None:
    settings = get_settings()
    client = _redis_client()
    key = f"llm:cb:{provider}:failures"
    pipe = client.pipeline()
    pipe.incr(key)
    pipe.expire(key, CB_FAILURE_TTL_SECONDS)
    failures = pipe.execute()[0]
    if failures >= settings.llm_circuit_breaker_failures:
        client.setex(
            f"llm:cb:{provider}:open", settings.llm_circuit_breaker_cooldown_seconds, "1"
        )


def record_success(provider: str) -> None:
    _redis_client().delete(f"llm:cb:{provider}:failures")
