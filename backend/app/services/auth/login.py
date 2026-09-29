"""Login flow: lockout check, Argon2id verification, MFA gate, token
issuance, and login event recording.

See PROJECT_PLAN.md Phase 4.1: account lockout with exponential backoff after
5 failures; login events recorded with IP and user agent; MFA mandatory for
staff roles.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security.encryption import decrypt_with_master_key
from backend.app.core.security.jwt_tokens import create_access_token
from backend.app.core.security.mfa import verify_and_consume_recovery_code, verify_totp_code
from backend.app.core.security.passwords import verify_password
from backend.app.core.security.refresh_tokens import issue_refresh_token
from backend.app.models.identity import LoginEvent, MfaFactor, Role, User, UserRole

STAFF_ROLES = {"platform_admin", "tenant_admin", "compliance_analyst", "senior_reviewer", "auditor"}


class LoginError(Exception):
    pass


class AccountLockedError(LoginError):
    def __init__(self, locked_until: dt.datetime):
        self.locked_until = locked_until
        super().__init__(f"Account locked until {locked_until.isoformat()}")


class MfaRequiredError(LoginError):
    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__("MFA verification required")


@dataclass
class LoginResult:
    access_token: str
    refresh_token: str
    user_id: int
    tenant_id: int | None
    roles: list[str]


def _get_user_roles(session: Session, user_id: int) -> list[str]:
    rows = (
        session.execute(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        .scalars()
        .all()
    )
    return list(rows)


def _record_login_event(
    session: Session,
    *,
    user_id: int | None,
    tenant_id: int | None,
    email_attempted: str,
    success: bool,
    failure_reason: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    session.add(
        LoginEvent(
            tenant_id=tenant_id,
            user_id=user_id,
            email_attempted=email_attempted,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            failure_reason=failure_reason,
        )
    )
    session.flush()


def _apply_lockout_backoff(session: Session, user: User) -> None:
    settings = get_settings()
    user.failed_login_count += 1
    if user.failed_login_count >= settings.login_lockout_threshold:
        overflow = user.failed_login_count - settings.login_lockout_threshold
        backoff_seconds = settings.login_lockout_base_seconds * (2**overflow)
        user.locked_until = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=backoff_seconds)
    session.flush()


def login(
    session: Session,
    *,
    email: str,
    password: str,
    tenant_id: int | None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> LoginResult:
    user = session.execute(
        select(User).where(User.email == email, User.tenant_id == tenant_id)
    ).scalar_one_or_none()

    if user is None:
        _record_login_event(
            session,
            user_id=None,
            tenant_id=tenant_id,
            email_attempted=email,
            success=False,
            failure_reason="unknown_user",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise LoginError("Invalid credentials")

    now = dt.datetime.now(dt.UTC)
    if user.locked_until is not None and user.locked_until > now:
        _record_login_event(
            session,
            user_id=user.id,
            tenant_id=tenant_id,
            email_attempted=email,
            success=False,
            failure_reason="locked",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise AccountLockedError(user.locked_until)

    if not verify_password(password, user.password_hash):
        _apply_lockout_backoff(session, user)
        _record_login_event(
            session,
            user_id=user.id,
            tenant_id=tenant_id,
            email_attempted=email,
            success=False,
            failure_reason="bad_password",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise LoginError("Invalid credentials")

    roles = _get_user_roles(session, user.id)

    if user.mfa_enabled or set(roles) & STAFF_ROLES:
        if not user.mfa_enabled:
            # Staff role without enrolled MFA: block login rather than allow
            # a silent bypass of the "mandatory for staff roles" policy.
            _record_login_event(
                session,
                user_id=user.id,
                tenant_id=tenant_id,
                email_attempted=email,
                success=False,
                failure_reason="mfa_not_enrolled",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise LoginError("MFA enrollment is required for this role before logging in")
        raise MfaRequiredError(user.id)

    return _issue_tokens_and_finalize(
        session, user, roles, tenant_id, ip_address=ip_address, user_agent=user_agent
    )


def complete_mfa_login(
    session: Session,
    *,
    user_id: int,
    code: str,
    tenant_id: int | None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> LoginResult:
    user = session.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise LoginError("Unknown user")

    factor = session.execute(
        select(MfaFactor).where(MfaFactor.user_id == user_id, MfaFactor.factor_type == "totp")
    ).scalar_one_or_none()
    if factor is None:
        raise LoginError("MFA is not enrolled for this user")

    secret = decrypt_with_master_key(factor.secret_encrypted)

    verified = verify_totp_code(secret, code)
    if not verified:
        remaining = verify_and_consume_recovery_code(factor.recovery_codes_hashed, code)
        if remaining is not None:
            factor.recovery_codes_hashed = remaining
            verified = True

    if not verified:
        _apply_lockout_backoff(session, user)
        _record_login_event(
            session,
            user_id=user.id,
            tenant_id=tenant_id,
            email_attempted=user.email,
            success=False,
            failure_reason="bad_mfa_code",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise LoginError("Invalid MFA code")

    roles = _get_user_roles(session, user.id)
    return _issue_tokens_and_finalize(
        session, user, roles, tenant_id, ip_address=ip_address, user_agent=user_agent
    )


def _issue_tokens_and_finalize(
    session: Session,
    user: User,
    roles: list[str],
    tenant_id: int | None,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> LoginResult:
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = dt.datetime.now(dt.UTC)

    access_token = create_access_token(user_id=user.id, tenant_id=user.tenant_id, roles=roles)
    refresh_plaintext, _ = issue_refresh_token(session, user_id=user.id, tenant_id=user.tenant_id)

    _record_login_event(
        session,
        user_id=user.id,
        tenant_id=tenant_id,
        email_attempted=user.email,
        success=True,
        failure_reason=None,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return LoginResult(
        access_token=access_token,
        refresh_token=refresh_plaintext,
        user_id=user.id,
        tenant_id=user.tenant_id,
        roles=roles,
    )
