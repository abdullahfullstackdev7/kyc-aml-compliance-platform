"""Password reset: a signed, single-use, 30-minute token.

See PROJECT_PLAN.md Phase 4.1. The token is a short-lived JWT (reusing the
platform's RS256 keypair, purpose-scoped) so no extra table is needed to
store it; single-use is enforced by recording each token's jti in Redis with
a TTL matching the token's own expiry, so a used jti simply disappears once
the token would have expired anyway.

Email delivery (a local Mailpit container in the demo) is not wired up here;
callers are expected to send `token` to the user out of band. Never log or
return the token to anyone other than the verified account holder.
"""

from __future__ import annotations

import datetime as dt
import uuid

import jwt
import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security.jwt_tokens import rsa_private_key, rsa_public_key
from backend.app.core.security.passwords import hash_password
from backend.app.models.identity import User

PURPOSE = "password_reset"
TOKEN_LIFETIME_MINUTES = 30
ALGORITHM = "RS256"


class PasswordResetError(Exception):
    pass


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(get_settings().redis_url)


def create_reset_token(user_id: int, tenant_id: int | None) -> str:
    settings = get_settings()
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id) if tenant_id is not None else None,
        "purpose": PURPOSE,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + dt.timedelta(minutes=TOKEN_LIFETIME_MINUTES),
        "iss": settings.jwt_issuer,
    }
    return jwt.encode(payload, rsa_private_key(), algorithm=ALGORITHM)


def _decode_reset_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            rsa_public_key(),
            algorithms=[ALGORITHM],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "jti", "purpose"]},
        )
    except jwt.InvalidTokenError as exc:
        raise PasswordResetError(f"Invalid or expired reset token: {exc}") from exc

    if payload.get("purpose") != PURPOSE:
        raise PasswordResetError("Token is not a password reset token")
    return payload


def consume_reset_token(session: Session, token: str, new_password: str) -> None:
    from backend.app.api.deps import set_tenant_context

    payload = _decode_reset_token(token)
    jti = payload["jti"]

    client = _redis_client()
    redis_key = f"password_reset_used:{jti}"
    if client.get(redis_key):
        raise PasswordResetError("This reset token has already been used")

    user_id = int(payload["sub"])
    tenant_id = int(payload["tid"]) if payload.get("tid") is not None else None
    set_tenant_context(session, tenant_id)
    user = session.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise PasswordResetError("Unknown user")

    user.password_hash = hash_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    session.flush()

    ttl_seconds = max(1, int(payload["exp"] - dt.datetime.now(dt.UTC).timestamp()))
    client.set(redis_key, "1", ex=ttl_seconds)
