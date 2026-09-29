"""TOTP enrollment start/confirm flow (PROJECT_PLAN.md Phase 4.1), against
the real Postgres instance since it needs the users/mfa_factors tables and
real encryption of the TOTP secret."""

from __future__ import annotations

import uuid

import pyotp
import pytest
from sqlalchemy import delete

from backend.app.core.security.passwords import hash_password
from backend.app.models.identity import MfaFactor, User
from backend.app.models.tenancy import Tenant
from backend.app.services.auth.mfa_enrollment import (
    MfaEnrollmentError,
    confirm_totp_enrollment,
    start_totp_enrollment,
)


@pytest.fixture
def user(db_session):
    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(name=f"MFA Enroll Test {unique}", slug=f"mfa-enroll-test-{unique}", region="NA")
    db_session.add(tenant)
    db_session.flush()
    u = User(
        tenant_id=tenant.id,
        email=f"mfa-{unique}@example.com",
        password_hash=hash_password("TestPass!2024"),
        full_name="MFA Test User",
    )
    db_session.add(u)
    db_session.commit()

    yield u

    db_session.execute(delete(MfaFactor).where(MfaFactor.user_id == u.id))
    db_session.execute(delete(User).where(User.id == u.id))
    db_session.commit()


def test_start_enrollment_for_unknown_user_raises(db_session):
    with pytest.raises(MfaEnrollmentError, match="Unknown user"):
        start_totp_enrollment(db_session, user_id=999_999_999)


def test_start_then_confirm_enables_mfa(db_session, user):
    enrollment = start_totp_enrollment(db_session, user.id)
    db_session.commit()
    assert len(enrollment.recovery_codes) > 0
    assert "otpauth://" in enrollment.provisioning_uri

    secret = pyotp.parse_uri(enrollment.provisioning_uri).secret
    code = pyotp.TOTP(secret).now()
    confirm_totp_enrollment(db_session, user.id, code)
    db_session.commit()

    db_session.refresh(user)
    assert user.mfa_enabled is True


def test_confirm_with_wrong_code_raises_and_does_not_enable_mfa(db_session, user):
    start_totp_enrollment(db_session, user.id)
    db_session.commit()

    with pytest.raises(MfaEnrollmentError, match="Invalid TOTP code"):
        confirm_totp_enrollment(db_session, user.id, "000000")
    db_session.commit()

    db_session.refresh(user)
    assert user.mfa_enabled is False


def test_confirm_without_pending_enrollment_raises(db_session, user):
    with pytest.raises(MfaEnrollmentError, match="No pending TOTP enrollment"):
        confirm_totp_enrollment(db_session, user.id, "000000")


def test_starting_enrollment_again_after_already_verified_raises(db_session, user):
    enrollment = start_totp_enrollment(db_session, user.id)
    db_session.commit()
    secret = pyotp.parse_uri(enrollment.provisioning_uri).secret
    confirm_totp_enrollment(db_session, user.id, pyotp.TOTP(secret).now())
    db_session.commit()

    with pytest.raises(MfaEnrollmentError, match="already enrolled"):
        start_totp_enrollment(db_session, user.id)
