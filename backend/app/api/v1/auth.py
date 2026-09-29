import ipaddress

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.app.api.deps import (
    get_current_principal,
    get_db,
    get_tenant_scoped_db,
    set_tenant_context,
)
from backend.app.core.config import get_settings
from backend.app.core.rate_limit import limiter
from backend.app.core.security.permissions import Principal
from backend.app.core.security.refresh_tokens import (
    RefreshTokenError,
    RefreshTokenReuseError,
    revoke_refresh_token,
    rotate_refresh_token,
)
from backend.app.schemas.auth import (
    LoginRequest,
    LoginSuccessResponse,
    LogoutRequest,
    MfaEnrollConfirmRequest,
    MfaEnrollStartResponse,
    MfaRequiredResponse,
    MfaVerifyRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequestRequest,
    PasswordResetRequestResponse,
    RefreshRequest,
    RefreshResponse,
)
from backend.app.services.auth.login import (
    AccountLockedError,
    LoginError,
    MfaRequiredError,
    complete_mfa_login,
)
from backend.app.services.auth.login import (
    login as login_service,
)
from backend.app.services.auth.mfa_enrollment import (
    MfaEnrollmentError,
    confirm_totp_enrollment,
    start_totp_enrollment,
)
from backend.app.services.auth.password_reset import (
    PasswordResetError,
    consume_reset_token,
    create_reset_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    """The `inet` column rejects anything that isn't a real IP; a reverse
    proxy misconfiguration or a test client can put a hostname there
    instead, so this degrades to None rather than 500ing the request."""
    if request.client is None:
        return None
    try:
        ipaddress.ip_address(request.client.host)
    except ValueError:
        return None
    return request.client.host


@router.post("/login", response_model=LoginSuccessResponse | MfaRequiredResponse)
@limiter.limit(get_settings().rate_limit_login)
def login(
    request: Request, body: LoginRequest, db: Session = Depends(get_db)
) -> LoginSuccessResponse | MfaRequiredResponse:
    set_tenant_context(db, body.tenant_id)
    ip_address = _client_ip(request)
    user_agent = request.headers.get("user-agent")
    try:
        result = login_service(
            db,
            email=body.email,
            password=body.password,
            tenant_id=body.tenant_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except MfaRequiredError as exc:
        db.commit()
        return MfaRequiredResponse(user_id=exc.user_id)
    except AccountLockedError as exc:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Account locked until {exc.locked_until.isoformat()}",
        ) from exc
    except LoginError as exc:
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    db.commit()
    return LoginSuccessResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        user_id=result.user_id,
        tenant_id=result.tenant_id,
        roles=result.roles,
    )


@router.post("/mfa/verify", response_model=LoginSuccessResponse)
@limiter.limit(get_settings().rate_limit_login)
def mfa_verify(
    request: Request, body: MfaVerifyRequest, db: Session = Depends(get_db)
) -> LoginSuccessResponse:
    set_tenant_context(db, body.tenant_id)
    ip_address = _client_ip(request)
    user_agent = request.headers.get("user-agent")
    try:
        result = complete_mfa_login(
            db,
            user_id=body.user_id,
            code=body.code,
            tenant_id=body.tenant_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except LoginError as exc:
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    db.commit()
    return LoginSuccessResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        user_id=result.user_id,
        tenant_id=result.tenant_id,
        roles=result.roles,
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> RefreshResponse:
    try:
        new_token, _ = rotate_refresh_token(db, body.refresh_token)
    except RefreshTokenReuseError as exc:
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except RefreshTokenError as exc:
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    db.commit()
    return RefreshResponse(refresh_token=new_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: LogoutRequest, db: Session = Depends(get_db)) -> None:
    revoke_refresh_token(db, body.refresh_token)
    db.commit()


@router.post("/password/reset", response_model=PasswordResetRequestResponse)
def request_password_reset(
    body: PasswordResetRequestRequest, db: Session = Depends(get_db)
) -> PasswordResetRequestResponse:
    from sqlalchemy import select

    from backend.app.models.identity import User

    set_tenant_context(db, body.tenant_id)
    user = db.execute(
        select(User).where(User.email == body.email, User.tenant_id == body.tenant_id)
    ).scalar_one_or_none()

    settings = get_settings()
    detail = "If that account exists, a password reset link has been sent."
    if user is None:
        return PasswordResetRequestResponse(detail=detail)

    token = create_reset_token(user.id, user.tenant_id)
    reset_token = token if settings.environment != "production" else None
    return PasswordResetRequestResponse(detail=detail, reset_token=reset_token)


@router.post("/password/reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(
    body: PasswordResetConfirmRequest, db: Session = Depends(get_db)
) -> None:
    try:
        consume_reset_token(db, body.token, body.new_password)
    except PasswordResetError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()


@router.post("/mfa/enroll/start", response_model=MfaEnrollStartResponse)
def mfa_enroll_start(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_tenant_scoped_db),
) -> MfaEnrollStartResponse:
    try:
        result = start_totp_enrollment(db, principal.user_id)
    except MfaEnrollmentError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return MfaEnrollStartResponse(
        factor_id=result.factor_id,
        provisioning_uri=result.provisioning_uri,
        recovery_codes=result.recovery_codes,
    )


@router.post("/mfa/enroll/confirm", status_code=status.HTTP_204_NO_CONTENT)
def mfa_enroll_confirm(
    body: MfaEnrollConfirmRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_tenant_scoped_db),
) -> None:
    try:
        confirm_totp_enrollment(db, principal.user_id, body.code)
    except MfaEnrollmentError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
