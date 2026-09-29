"""Fixtures for the Phase 4 security test suite. Uses the real running
Postgres instance (skips gracefully if unreachable, consistent with the
rest of the integration suite) since RLS, the audit trigger and the
restricted application role can only be exercised meaningfully there.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_settings
from backend.app.core.security.passwords import hash_password
from backend.app.models.identity import LoginEvent, RefreshToken, Role, User, UserRole
from backend.app.models.tenancy import Tenant

TEST_PASSWORD = "SecurityTest!Pass9000"


@pytest.fixture
def db_session():
    settings = get_settings()
    try:
        engine = create_engine(settings.sync_database_url())
        engine.connect().close()
    except Exception as exc:  # noqa: BLE001 - environment guard, any connection failure skips
        pytest.skip(f"Postgres not reachable for this test: {exc}")

    # expire_on_commit=False: without it, attribute access after commit()
    # (e.g. asserting on user.locked_until) silently reopens a transaction
    # that outlives the test.
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def app_db_session():
    """A session connected as the restricted application role, the same one
    the running API uses, so RLS and audit_log grants are actually in force."""
    settings = get_settings()
    try:
        engine = create_engine(settings.app_sync_database_url())
        engine.connect().close()
    except Exception as exc:  # noqa: BLE001 - environment guard, any connection failure skips
        pytest.skip(f"Restricted app role not reachable for this test: {exc}")

    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.rollback()
    session.close()


def make_user(
    session, *, tenant, role_code: str, email: str, password: str = TEST_PASSWORD
) -> User:
    role = session.query(Role).filter_by(code=role_code).one()
    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password(password),
        full_name=f"Security Test {role_code}",
    )
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id, tenant_id=tenant.id))
    session.flush()
    return user


@pytest.fixture
def two_tenants(db_session):
    tenant_a = Tenant(name="Security Test Tenant A", slug="sec-test-tenant-a", region="NA")
    tenant_b = Tenant(name="Security Test Tenant B", slug="sec-test-tenant-b", region="NA")
    db_session.add_all([tenant_a, tenant_b])
    db_session.flush()
    db_session.commit()

    yield tenant_a, tenant_b

    db_session.execute(
        delete(RefreshToken).where(RefreshToken.tenant_id.in_([tenant_a.id, tenant_b.id]))
    )
    db_session.execute(
        delete(LoginEvent).where(LoginEvent.tenant_id.in_([tenant_a.id, tenant_b.id]))
    )
    db_session.execute(delete(UserRole).where(UserRole.tenant_id.in_([tenant_a.id, tenant_b.id])))
    db_session.execute(delete(User).where(User.tenant_id.in_([tenant_a.id, tenant_b.id])))
    db_session.execute(delete(Tenant).where(Tenant.id.in_([tenant_a.id, tenant_b.id])))
    db_session.commit()
