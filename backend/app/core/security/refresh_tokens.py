"""Opaque refresh tokens: stored hashed, rotated on each use, with reuse
detection that revokes the whole token family.

See PROJECT_PLAN.md Phase 4.1. The plaintext token is returned to the caller
exactly once (at issue or rotation time) and is never stored; only its
SHA-256 hash lives in `refresh_tokens.token_hash`. If a hash is presented
that matches an already-rotated (replaced) token, that is a stolen or
replayed token: every token in the family is revoked immediately.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.identity import RefreshToken

TOKEN_BYTES = 32


class RefreshTokenError(Exception):
    pass


class RefreshTokenReuseError(RefreshTokenError):
    """Raised when a previously-rotated refresh token is presented again."""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_refresh_token(
    session: Session, *, user_id: int, tenant_id: int | None, family_id: str | None = None
) -> tuple[str, RefreshToken]:
    settings = get_settings()
    plaintext = secrets.token_urlsafe(TOKEN_BYTES)
    now = dt.datetime.now(dt.UTC)

    record = RefreshToken(
        tenant_id=tenant_id,
        user_id=user_id,
        token_hash=_hash_token(plaintext),
        family_id=family_id or str(uuid.uuid4()),
        issued_at=now,
        expires_at=now + dt.timedelta(days=settings.refresh_token_days),
    )
    session.add(record)
    session.flush()
    return plaintext, record


def rotate_refresh_token(session: Session, plaintext: str) -> tuple[str, RefreshToken]:
    """Validate and rotate a refresh token, returning the new plaintext token.

    Raises RefreshTokenReuseError (revoking the family) if the presented
    token was already rotated away, and RefreshTokenError for any other
    invalid/expired/unknown token.
    """
    token_hash = _hash_token(plaintext)
    record = session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one_or_none()

    if record is None:
        raise RefreshTokenError("Unknown refresh token")

    if record.replaced_by_id is not None:
        _revoke_family(session, record.family_id)
        raise RefreshTokenReuseError(
            f"Refresh token reuse detected for family {record.family_id}; family revoked"
        )

    now = dt.datetime.now(dt.UTC)
    if record.revoked_at is not None:
        raise RefreshTokenError("Refresh token has been revoked")
    if record.expires_at < now:
        raise RefreshTokenError("Refresh token has expired")

    new_plaintext, new_record = issue_refresh_token(
        session, user_id=record.user_id, tenant_id=record.tenant_id, family_id=record.family_id
    )
    record.replaced_by_id = new_record.id
    record.revoked_at = now
    session.flush()
    return new_plaintext, new_record


def revoke_refresh_token(session: Session, plaintext: str) -> None:
    token_hash = _hash_token(plaintext)
    record = session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one_or_none()
    if record is not None and record.revoked_at is None:
        record.revoked_at = dt.datetime.now(dt.UTC)
        session.flush()


def _revoke_family(session: Session, family_id: str) -> None:
    now = dt.datetime.now(dt.UTC)
    records = session.execute(
        select(RefreshToken).where(
            RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)
        )
    ).scalars()
    for record in records:
        record.revoked_at = now
    session.flush()
