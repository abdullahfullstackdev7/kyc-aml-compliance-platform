"""Rate limiting via slowapi, backed by Redis so limits are shared across
worker processes. See PROJECT_PLAN.md Phase 4.3: login 5/minute/IP, general
API 300/minute/user.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.core.config import get_settings

limiter = Limiter(key_func=get_remote_address, storage_uri=get_settings().redis_url)
