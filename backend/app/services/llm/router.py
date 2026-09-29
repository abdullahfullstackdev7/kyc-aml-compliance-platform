"""Picks a provider with headroom, retries transient failures once, fails
over to the other provider, and falls back to a deterministic template if
both are unavailable. See PROJECT_PLAN.md Phase 6.2. The workflow never
blocks on an LLM: every path here returns a result.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from backend.app.services.llm import quota, runtime_settings
from backend.app.services.llm.provider import (
    LLMProvider,
    LLMResult,
    LLMTransientError,
    get_provider,
)

PROVIDERS = ("groq", "gemini")


@dataclass
class RouterResult:
    result: LLMResult | None
    provider: str | None  # None when both providers failed (template fallback)
    status: str  # ok | fallback
    latency_ms: int


def _fallback_provider_order() -> list[str]:
    primary = runtime_settings.get_primary_provider()
    return [primary, *[p for p in PROVIDERS if p != primary]]


def _provider_available(name: str) -> bool:
    return quota.has_headroom(name) and not quota.circuit_open(name)


def _call_with_retry(provider: LLMProvider, **kwargs) -> LLMResult:
    try:
        return provider.generate_json(**kwargs)
    except LLMTransientError:
        time.sleep(0.2 + random.uniform(0, 0.3))
        return provider.generate_json(**kwargs)


def generate_json(
    *, purpose: str, system_prompt: str, user_payload: dict, max_tokens: int
) -> RouterResult:
    start = time.monotonic()

    if not runtime_settings.is_enabled():
        return RouterResult(result=None, provider=None, status="fallback", latency_ms=0)

    primary = _fallback_provider_order()[0]
    primary_failed = False

    for name in _fallback_provider_order():
        if not _provider_available(name):
            if name == primary:
                primary_failed = True
            continue
        try:
            provider = get_provider(name)
            result = _call_with_retry(
                provider,
                purpose=purpose,
                system_prompt=system_prompt,
                user_payload=user_payload,
                max_tokens=max_tokens,
            )
        except Exception:  # noqa: BLE001 - any provider failure fails over; never blocks the workflow
            quota.record_failure(name)
            if name == primary:
                primary_failed = True
            continue

        if primary_failed and name != primary:
            from backend.app.core.observability import LLM_FAILOVERS_TOTAL

            LLM_FAILOVERS_TOTAL.inc()

        quota.record_success(name)
        quota.record_usage(name, result.prompt_tokens + result.completion_tokens)
        return RouterResult(
            result=result,
            provider=name,
            status="ok",
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    return RouterResult(
        result=None, provider=None, status="fallback", latency_ms=int((time.monotonic() - start) * 1000)
    )
