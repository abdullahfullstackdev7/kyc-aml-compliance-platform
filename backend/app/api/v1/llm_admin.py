"""Platform-admin LLM provider settings and live quota headroom.
See PROJECT_PLAN.md Phase 6.2: "Admin page lets a platform admin set primary
provider, view live quota headroom and disable LLM features entirely."
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.security.permissions import Principal, require_permission
from backend.app.services.llm import quota, runtime_settings

router = APIRouter(prefix="/llm", tags=["llm-admin"])


@router.get("/quota")
def get_quota(principal: Principal = Depends(require_permission("llm:manage"))) -> dict:
    return {
        "primary_provider": runtime_settings.get_primary_provider(),
        "enabled": runtime_settings.is_enabled(),
        "providers": {name: quota.quota_headroom(name) for name in ("groq", "gemini")},
    }


@router.post("/settings")
def update_settings(
    primary_provider: str | None = None,
    enabled: bool | None = None,
    principal: Principal = Depends(require_permission("llm:manage")),
) -> dict:
    if primary_provider is not None:
        try:
            runtime_settings.set_primary_provider(primary_provider)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if enabled is not None:
        runtime_settings.set_enabled(enabled)
    return {
        "primary_provider": runtime_settings.get_primary_provider(),
        "enabled": runtime_settings.is_enabled(),
    }
