from collections.abc import Iterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings
from backend.app.core.security.jwt_tokens import TokenError, decode_access_token

# The running application connects as the restricted role (migration 0004:
# no superuser, RLS not bypassed, INSERT/SELECT only on audit_log), never as
# the migration-owner role Alembic and the Dagster pipelines use.
_engine = create_engine(get_settings().app_sync_database_url(), pool_pre_ping=True)
_session_factory = sessionmaker(bind=_engine, expire_on_commit=False)

_bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    session = _session_factory()
    try:
        yield session
    finally:
        session.close()


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
):
    from backend.app.core.security.permissions import Principal

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return Principal(
        user_id=int(claims.sub),
        tenant_id=int(claims.tid) if claims.tid is not None else None,
        roles=claims.roles,
    )


def set_tenant_context(db: Session, tenant_id: int | None) -> None:
    """Sets `app.tenant_id` for the remainder of the current transaction, so
    Row-Level Security (migration 0002/0004) scopes queries to that tenant.

    Used both post-authentication (from the JWT's trusted `tid` claim, via
    get_tenant_scoped_db below) and pre-authentication in the login/MFA/
    password-reset flows, where the caller supplies the tenant explicitly as
    part of stating which account they are trying to authenticate as. That is
    safe: choosing which tenant's user row to query is not itself a
    privilege, since the caller still has to satisfy password/MFA checks
    against whatever row RLS lets them see for that tenant.
    """
    if tenant_id is not None:
        db.execute(text("SET LOCAL app.tenant_id = :tenant_id"), {"tenant_id": str(tenant_id)})


def get_tenant_scoped_db(
    principal=Depends(get_current_principal), db: Session = Depends(get_db)
) -> Iterator[Session]:
    """A DB session with `app.tenant_id` set for the request's authenticated
    tenant, so Row-Level Security (migration 0002/0004) actually scopes every
    query issued through it to that tenant. Use this instead of `get_db` for
    any endpoint reading or writing tenant-owned tables."""
    set_tenant_context(db, principal.tenant_id)
    yield db
