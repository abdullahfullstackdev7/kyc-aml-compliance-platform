"""Live, admin-toggleable LLM settings (primary provider, enabled/disabled),
stored in Redis so an admin can flip them without a redeploy. See
PROJECT_PLAN.md Phase 6.2: "Admin page lets a platform admin set primary
provider, view live quota headroom and disable LLM features entirely."
`Settings.llm_primary`/`Settings.llm_enabled` remain the defaults until an
admin overrides them here.
"""

from __future__ import annotations

from backend.app.core.config import get_settings
from backend.app.services.llm.quota import redis_client

_PRIMARY_KEY = "llm:settings:primary_provider"
_ENABLED_KEY = "llm:settings:enabled"


def get_primary_provider() -> str:
    value = redis_client().get(_PRIMARY_KEY)
    return str(value) if value else get_settings().llm_primary


def set_primary_provider(provider: str) -> None:
    if provider not in ("groq", "gemini"):
        raise ValueError("primary_provider must be groq or gemini")
    redis_client().set(_PRIMARY_KEY, provider)


def is_enabled() -> bool:
    value = redis_client().get(_ENABLED_KEY)
    if value is None:
        return get_settings().llm_enabled
    return value == "1"


def set_enabled(enabled: bool) -> None:
    redis_client().set(_ENABLED_KEY, "1" if enabled else "0")
