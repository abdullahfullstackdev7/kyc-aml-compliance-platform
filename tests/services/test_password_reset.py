"""Password reset token issue/consume flow (PROJECT_PLAN.md Phase 4.1):
single-use enforced via a Redis-recorded jti, against the real Postgres and
Redis instances."""

from __future__ import annotations

import datetime as dt
import uuid

import jwt
import pytest
from sqlalchemy import delete

from backend.app.core.security.jwt_tokens import rsa_private_key
from backend.app.core.security.passwords import hash_password, verify_password
from backend.app.models.identity import User
from backend.app.models.tenancy import Tenant
from backend.app.services.auth.password_reset import (
    ALGORITHM,
    PURPOSE,
    PasswordResetError,
    consume_reset_token,
    create_reset_token,
)


@pytest.fixture
def user(db_session):
    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(name=f"Reset Test {unique}", slug=f"reset-test-{unique}", region="NA")
    db_session.add(tenant)
    db_session.flush()
    u = User(
        tenant_id=tenant.id,
        email=f"reset-{unique}@example.com",
        password_hash=hash_password("OldPassword!2024"),
        full_name="Reset Test User",
    )
    db_session.add(u)
    db_session.commit()
    yield u
    db_session.execute(delete(User).where(User.id == u.id))
    db_session.commit()


def test_valid_token_resets_the_password(db_session, user):
    token = create_reset_token(user.id, user.tenant_id)
    consume_reset_token(db_session, token, "BrandNewPassword!2024")
    db_session.commit()

    db_session.refresh(user)
    assert verify_password("BrandNewPassword!2024", user.password_hash)
    assert not verify_password("OldPassword!2024", user.password_hash)


def test_token_cannot_be_used_twice(db_session, user):
    token = create_reset_token(user.id, user.tenant_id)
    consume_reset_token(db_session, token, "FirstReset!2024")
    db_session.commit()

    with pytest.raises(PasswordResetError, match="already been used"):
        consume_reset_token(db_session, token, "SecondReset!2024")


def test_tampered_token_is_rejected(db_session, user):
    token = create_reset_token(user.id, user.tenant_id)
    tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")

    with pytest.raises(PasswordResetError, match="Invalid or expired"):
        consume_reset_token(db_session, tampered, "NewPassword!2024")


def test_expired_token_is_rejected(db_session, user):
    now = dt.datetime.now(dt.UTC)
    from backend.app.core.config import get_settings

    payload = {
        "sub": str(user.id),
        "tid": str(user.tenant_id),
        "purpose": PURPOSE,
        "jti": str(uuid.uuid4()),
        "iat": now - dt.timedelta(minutes=60),
        "exp": now - dt.timedelta(minutes=30),
        "iss": get_settings().jwt_issuer,
    }
    expired_token = jwt.encode(payload, rsa_private_key(), algorithm=ALGORITHM)

    with pytest.raises(PasswordResetError, match="Invalid or expired"):
        consume_reset_token(db_session, expired_token, "NewPassword!2024")


def test_wrong_purpose_token_is_rejected(db_session, user):
    now = dt.datetime.now(dt.UTC)
    from backend.app.core.config import get_settings

    payload = {
        "sub": str(user.id),
        "tid": str(user.tenant_id),
        "purpose": "not_password_reset",
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + dt.timedelta(minutes=30),
        "iss": get_settings().jwt_issuer,
    }
    wrong_purpose_token = jwt.encode(payload, rsa_private_key(), algorithm=ALGORITHM)

    with pytest.raises(PasswordResetError, match="not a password reset token"):
        consume_reset_token(db_session, wrong_purpose_token, "NewPassword!2024")


def test_unknown_user_is_rejected(db_session):
    token = create_reset_token(999_999_999, None)
    with pytest.raises(PasswordResetError, match="Unknown user"):
        consume_reset_token(db_session, token, "NewPassword!2024")
