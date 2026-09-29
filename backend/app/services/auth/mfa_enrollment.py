"""TOTP MFA enrollment: generate a secret and recovery codes, persist the
secret encrypted, and confirm enrollment with a first valid code.

See PROJECT_PLAN.md Phase 4.1.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security.encryption import decrypt_with_master_key, encrypt_with_master_key
from backend.app.core.security.mfa import (
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_codes,
    provisioning_uri,
    verify_totp_code,
)
from backend.app.models.identity import MfaFactor, User


class MfaEnrollmentError(Exception):
    pass


@dataclass
class EnrollmentStart:
    factor_id: int
    provisioning_uri: str
    recovery_codes: list[str]  # shown to the user exactly once


def start_totp_enrollment(session: Session, user_id: int) -> EnrollmentStart:
    user = session.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise MfaEnrollmentError("Unknown user")

    existing = session.execute(
        select(MfaFactor).where(MfaFactor.user_id == user_id, MfaFactor.factor_type == "totp")
    ).scalar_one_or_none()
    if existing is not None and existing.verified_at is not None:
        raise MfaEnrollmentError("TOTP is already enrolled for this user")

    secret = generate_totp_secret()
    recovery_codes = generate_recovery_codes()

    if existing is not None:
        existing.secret_encrypted = encrypt_with_master_key(secret)
        existing.recovery_codes_hashed = hash_recovery_codes(recovery_codes)
        existing.verified_at = None
        factor = existing
    else:
        factor = MfaFactor(
            tenant_id=user.tenant_id,
            user_id=user_id,
            factor_type="totp",
            secret_encrypted=encrypt_with_master_key(secret),
            recovery_codes_hashed=hash_recovery_codes(recovery_codes),
        )
        session.add(factor)
    session.flush()

    return EnrollmentStart(
        factor_id=factor.id,
        provisioning_uri=provisioning_uri(secret, account_email=user.email),
        recovery_codes=recovery_codes,
    )


def confirm_totp_enrollment(session: Session, user_id: int, code: str) -> None:
    factor = session.execute(
        select(MfaFactor).where(MfaFactor.user_id == user_id, MfaFactor.factor_type == "totp")
    ).scalar_one_or_none()
    if factor is None:
        raise MfaEnrollmentError("No pending TOTP enrollment for this user")

    secret = decrypt_with_master_key(factor.secret_encrypted)
    if not verify_totp_code(secret, code):
        raise MfaEnrollmentError("Invalid TOTP code")

    factor.verified_at = dt.datetime.now(dt.UTC)

    user = session.execute(select(User).where(User.id == user_id)).scalar_one()
    user.mfa_enabled = True
    session.flush()
