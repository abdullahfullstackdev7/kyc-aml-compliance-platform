"""JWT access tokens (RS256), 15 minute lifetime, claims sub/tid/roles/jti.

See PROJECT_PLAN.md Phase 4.1. Signing is asymmetric (RS256) so the public
key can be distributed to services that only need to verify tokens without
holding the signing key.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import jwt

from backend.app.core.config import get_settings

ALGORITHM = "RS256"


class TokenError(Exception):
    pass


@dataclass
class AccessTokenClaims:
    sub: str  # user id
    tid: str | None  # tenant id, None for platform-level users
    roles: list[str]
    jti: str
    exp: dt.datetime
    iat: dt.datetime


@lru_cache(maxsize=1)
def rsa_private_key() -> str:
    settings = get_settings()
    if not settings.jwt_private_key_path:
        raise TokenError("JWT_PRIVATE_KEY_PATH is not configured")
    return Path(settings.jwt_private_key_path).read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def rsa_public_key() -> str:
    settings = get_settings()
    if not settings.jwt_public_key_path:
        raise TokenError("JWT_PUBLIC_KEY_PATH is not configured")
    return Path(settings.jwt_public_key_path).read_text(encoding="utf-8")


def create_access_token(*, user_id: int, tenant_id: int | None, roles: list[str]) -> str:
    settings = get_settings()
    now = dt.datetime.now(dt.UTC)
    expires = now + dt.timedelta(minutes=settings.jwt_access_token_minutes)
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id) if tenant_id is not None else None,
        "roles": roles,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expires,
        "iss": settings.jwt_issuer,
    }
    return jwt.encode(payload, rsa_private_key(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> AccessTokenClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            rsa_public_key(),
            algorithms=[ALGORITHM],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Access token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError(f"Invalid access token: {exc}") from exc

    return AccessTokenClaims(
        sub=payload["sub"],
        tid=payload.get("tid"),
        roles=payload.get("roles", []),
        jti=payload["jti"],
        exp=dt.datetime.fromtimestamp(payload["exp"], tz=dt.UTC),
        iat=dt.datetime.fromtimestamp(payload["iat"], tz=dt.UTC),
    )
