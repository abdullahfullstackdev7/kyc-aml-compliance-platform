"""llm_cache: identical (purpose, prompt_version, payload) never calls a
provider twice. See PROJECT_PLAN.md Phase 6.3.4.
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.governance import LlmCache


def cache_key(purpose: str, prompt_version: str, payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest_input = f"{purpose}|{prompt_version}|{canonical}"
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


def get_cached(session: Session, key: str) -> dict | None:
    entry = session.execute(
        select(LlmCache.response).where(LlmCache.cache_key == key)
    ).scalar_one_or_none()
    return entry


def store_cached(
    session: Session, *, key: str, purpose: str, prompt_version: str, response: dict
) -> None:
    existing = session.execute(
        select(LlmCache).where(LlmCache.cache_key == key)
    ).scalar_one_or_none()
    if existing is not None:
        return
    session.add(
        LlmCache(cache_key=key, purpose=purpose, prompt_version=prompt_version, response=response)
    )
    session.flush()
