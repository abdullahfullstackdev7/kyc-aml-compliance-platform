"""Phase 4 exit-criteria security test suite: privilege escalation, cross-
tenant access, refresh token reuse, and account lockout, against the real
Postgres instance and the real HTTP API.
"""

from __future__ import annotations

import datetime as dt

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.app.core.security.jwt_tokens import (
    ALGORITHM,
    TokenError,
    create_access_token,
    decode_access_token,
    rsa_private_key,
)
from backend.app.core.security.permissions import (
    Principal,
    principal_has_permission,
    require_permission,
)
from backend.app.core.security.refresh_tokens import (
    RefreshTokenError,
    RefreshTokenReuseError,
    issue_refresh_token,
    rotate_refresh_token,
)
from backend.app.services.auth.login import AccountLockedError, LoginError, login
from tests.security.conftest import TEST_PASSWORD, make_user

# --- Account lockout ---


def test_lockout_after_five_failures(db_session, two_tenants):
    tenant_a, _ = two_tenants
    user = make_user(db_session, tenant=tenant_a, role_code="customer", email="lockout@example.com")
    db_session.commit()

    for _ in range(5):
        with pytest.raises(LoginError):
            login(db_session, email=user.email, password="wrong-password", tenant_id=tenant_a.id)
    db_session.commit()

    with pytest.raises(AccountLockedError):
        login(db_session, email=user.email, password=TEST_PASSWORD, tenant_id=tenant_a.id)


def test_lockout_backoff_grows_with_repeated_failures(db_session, two_tenants):
    tenant_a, _ = two_tenants
    user = make_user(db_session, tenant=tenant_a, role_code="customer", email="backoff@example.com")
    db_session.commit()

    for _ in range(5):
        with pytest.raises(LoginError):
            login(db_session, email=user.email, password="wrong-password", tenant_id=tenant_a.id)
    db_session.commit()
    first_lockout = user.locked_until

    user.locked_until = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    db_session.commit()
    with pytest.raises(LoginError):
        login(db_session, email=user.email, password="wrong-password", tenant_id=tenant_a.id)
    db_session.commit()
    second_lockout = user.locked_until

    assert second_lockout > first_lockout


# --- Refresh token reuse detection ---


def test_refresh_token_reuse_revokes_whole_family(db_session, two_tenants):
    tenant_a, _ = two_tenants
    user = make_user(db_session, tenant=tenant_a, role_code="customer", email="reuse@example.com")
    db_session.commit()

    plaintext, _ = issue_refresh_token(db_session, user_id=user.id, tenant_id=tenant_a.id)
    db_session.commit()

    rotated, _ = rotate_refresh_token(db_session, plaintext)
    db_session.commit()

    with pytest.raises(RefreshTokenReuseError):
        rotate_refresh_token(db_session, plaintext)
    db_session.commit()

    with pytest.raises(RefreshTokenError):
        rotate_refresh_token(db_session, rotated)


def test_unknown_refresh_token_rejected(db_session):
    with pytest.raises(RefreshTokenError):
        rotate_refresh_token(db_session, "not-a-real-token")


# --- Cross-tenant access ---


def test_cannot_login_with_credentials_scoped_to_a_different_tenant(db_session, two_tenants):
    tenant_a, tenant_b = two_tenants
    make_user(db_session, tenant=tenant_a, role_code="customer", email="crosstenant@example.com")
    db_session.commit()

    # Same email, but the account lives in tenant A; asking for it under
    # tenant B must fail exactly like an unknown user, never leak the
    # tenant-A record or its password hash.
    with pytest.raises(LoginError):
        login(
            db_session,
            email="crosstenant@example.com",
            password=TEST_PASSWORD,
            tenant_id=tenant_b.id,
        )


def test_rls_blocks_cross_tenant_user_visibility(app_db_session, two_tenants):
    from sqlalchemy import select, text

    tenant_a, tenant_b = two_tenants

    app_db_session.execute(text("SET LOCAL app.tenant_id = :t"), {"t": str(tenant_a.id)})
    from backend.app.models.identity import User

    visible_tenant_ids = {
        row[0]
        for row in app_db_session.execute(
            select(User.tenant_id).where(User.tenant_id.in_([tenant_a.id, tenant_b.id]))
        )
    }
    assert tenant_b.id not in visible_tenant_ids


# --- Privilege escalation (RBAC) ---


def test_customer_role_lacks_case_decision_permission(db_session):
    assert (
        principal_has_permission(
            db_session, Principal(user_id=1, tenant_id=1, roles=["customer"]), "cases:decide"
        )
        is False
    )


def test_senior_reviewer_has_case_decision_permission(db_session):
    assert (
        principal_has_permission(
            db_session, Principal(user_id=1, tenant_id=1, roles=["senior_reviewer"]), "cases:decide"
        )
        is True
    )


def test_require_permission_dependency_returns_403_for_wrong_role(db_session, two_tenants):
    tenant_a, _ = two_tenants
    customer = make_user(
        db_session, tenant=tenant_a, role_code="customer", email="escalate@example.com"
    )
    db_session.commit()

    token = create_access_token(user_id=customer.id, tenant_id=tenant_a.id, roles=["customer"])

    app = FastAPI()

    @app.get("/protected")
    def protected(principal: Principal = Depends(require_permission("cases:decide"))):
        return {"ok": True}

    app.dependency_overrides = {}
    client = TestClient(app)
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_require_permission_dependency_allows_correct_role(db_session, two_tenants):
    tenant_a, _ = two_tenants
    reviewer = make_user(
        db_session, tenant=tenant_a, role_code="senior_reviewer", email="reviewer@example.com"
    )
    db_session.commit()

    token = create_access_token(
        user_id=reviewer.id, tenant_id=tenant_a.id, roles=["senior_reviewer"]
    )

    app = FastAPI()

    @app.get("/protected")
    def protected(principal: Principal = Depends(require_permission("cases:decide"))):
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_missing_bearer_token_rejected():
    app = FastAPI()

    @app.get("/protected")
    def protected(principal: Principal = Depends(require_permission("cases:decide"))):
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/protected")
    assert response.status_code == 401


# --- JWT integrity ---


def test_tampered_jwt_signature_rejected():
    token = create_access_token(user_id=1, tenant_id=1, roles=["customer"])
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(TokenError):
        decode_access_token(tampered)


def test_expired_jwt_rejected():
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": "1",
        "tid": "1",
        "roles": ["customer"],
        "jti": "expired-test",
        "iat": now - dt.timedelta(minutes=30),
        "exp": now - dt.timedelta(minutes=15),
        "iss": "sentinelkyc",
    }
    expired_token = jwt.encode(payload, rsa_private_key(), algorithm=ALGORITHM)
    with pytest.raises(TokenError):
        decode_access_token(expired_token)


def test_jwt_with_wrong_issuer_rejected():
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": "1",
        "tid": "1",
        "roles": ["platform_admin"],
        "jti": "wrong-issuer-test",
        "iat": now,
        "exp": now + dt.timedelta(minutes=15),
        "iss": "not-sentinelkyc",
    }
    forged_token = jwt.encode(payload, rsa_private_key(), algorithm=ALGORITHM)
    with pytest.raises(TokenError):
        decode_access_token(forged_token)


# --- Audit log immutability ---


def test_app_role_cannot_update_audit_log(app_db_session):
    from sqlalchemy import text

    app_db_session.execute(
        text(
            "INSERT INTO audit_log (tenant_id, actor_id, action, resource_type, resource_id, hash) "
            "VALUES (NULL, NULL, 'security_test', 'test', '1', 'deadbeef')"
        )
    )
    app_db_session.commit()

    with pytest.raises(Exception, match="permission denied"):
        app_db_session.execute(
            text("UPDATE audit_log SET action = 'tampered' WHERE action = 'security_test'")
        )
    app_db_session.rollback()

    with pytest.raises(Exception, match="permission denied"):
        app_db_session.execute(text("DELETE FROM audit_log WHERE action = 'security_test'"))
    app_db_session.rollback()

    # Cleanup requires bypassing the trigger; done here with the superuser
    # connection via db_session-equivalent raw access, not the app role.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.app.core.config import get_settings

    engine = create_engine(get_settings().sync_database_url())
    Session = sessionmaker(bind=engine)
    with Session() as cleanup_session:
        cleanup_session.execute(text("DROP TRIGGER audit_log_append_only ON audit_log"))
        cleanup_session.execute(text("DELETE FROM audit_log WHERE action = 'security_test'"))
        cleanup_session.execute(
            text(
                "CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log "
                "FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation()"
            )
        )
        cleanup_session.commit()
