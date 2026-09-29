"""Blind indexes: HMAC-SHA256 of a normalized value, for exact-match lookups
on encrypted columns without decrypting them.

See PROJECT_PLAN.md Phase 4.3. Uses a separate key from the encryption master
key, so compromising one does not compromise the other.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from functools import lru_cache

from backend.app.core.config import get_settings


class BlindIndexError(Exception):
    pass


@lru_cache(maxsize=1)
def _key() -> bytes:
    settings = get_settings()
    if not settings.blind_index_key:
        raise BlindIndexError("BLIND_INDEX_KEY is not configured")
    return base64.b64decode(settings.blind_index_key)


def compute_blind_index(value: str) -> str:
    normalized = value.strip().casefold()
    return hmac.new(_key(), normalized.encode("utf-8"), hashlib.sha256).hexdigest()
