"""IDOR, rate limiting and privilege escalation against the real running API
(PROJECT_PLAN.md Phase 10.3), using TestClient end to end rather than
calling service functions directly, since these are request-boundary
concerns (auth headers, tenant-scoped ownership checks, rate limiter
middleware)."""

from __future__ import annotations

import io
import uuid

import pytest
import redis
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_settings
from backend.app.core.security.passwords import hash_password
from backend.app.main import app
from backend.app.models.identity import Role, User, UserRole
from backend.app.models.tenancy import Tenant

PASSWORD = "IdorTest!Pass2024"


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    """The login rate limiter is Redis-backed and keyed by client IP, which
    TestClient always reports as the same synthetic address - so without
    resetting it, tests in this file (and any other file that logs in
    multiple times) exhaust each other's quota. Not a workaround for a
    flaky test: it isolates each test's own behavior from unrelated
    requests, the same way a real deployment would isolate two different
    users' IPs from each other."""
    client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    for key in client.scan_iter("LIMITS:LIMITER/testclient/*"):
        client.delete(key)
    yield
    for key in client.scan_iter("LIMITS:LIMITER/testclient/*"):
        client.delete(key)


@pytest.fixture
def db_session():
    settings = get_settings()
    try:
        engine = create_engine(settings.sync_database_url())
        engine.connect().close()
    except Exception as exc:  # noqa: BLE001 - environment guard
        pytest.skip(f"Postgres not reachable: {exc}")
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def client():
    return TestClient(app)


def _make_customer(db_session, tenant, suffix):
    role = db_session.execute(select(Role).where(Role.code == "customer")).scalar_one()
    user = User(
        tenant_id=tenant.id,
        email=f"idor-{suffix}@example.com",
        password_hash=hash_password(PASSWORD),
        full_name=f"IDOR Test {suffix}",
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=role.id, tenant_id=tenant.id))
    db_session.commit()
    return user


def _login(client, email, tenant_id):
    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD, "tenant_id": tenant_id}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def tenant(db_session):
    from backend.app.models.onboarding import Application, Customer, Document, DocumentCheck

    unique = uuid.uuid4().hex[:8]
    t = Tenant(name=f"IDOR Test {unique}", slug=f"idor-test-{unique}", region="NA")
    db_session.add(t)
    db_session.flush()
    db_session.commit()
    yield t
    db_session.execute(
        delete(DocumentCheck).where(
            DocumentCheck.document_id.in_(select(Document.id).where(Document.tenant_id == t.id))
        )
    )
    db_session.execute(delete(Document).where(Document.tenant_id == t.id))
    db_session.execute(delete(Application).where(Application.tenant_id == t.id))
    db_session.execute(delete(Customer).where(Customer.tenant_id == t.id))
    db_session.execute(delete(UserRole).where(UserRole.tenant_id == t.id))
    db_session.execute(delete(User).where(User.tenant_id == t.id))
    db_session.commit()


def _sharp_image_bytes() -> bytes:
    img = Image.new("L", (700, 700))
    pixels = img.load()
    for x in range(700):
        for y in range(700):
            pixels[x, y] = 200 if (x // 12 + y // 12) % 2 == 0 else 50
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_customer_cannot_upload_a_document_to_another_customers_application(
    client, db_session, tenant
):
    victim = _make_customer(db_session, tenant, "victim")
    attacker = _make_customer(db_session, tenant, "attacker")

    victim_token = _login(client, victim.email, tenant.id)
    attacker_token = _login(client, attacker.email, tenant.id)

    create = client.post(
        "/api/v1/portal/applications",
        json={"customer_type": "individual", "full_name": "Victim Applicant"},
        headers={"Authorization": f"Bearer {victim_token}"},
    )
    assert create.status_code == 201
    victim_application_id = create.json()["id"]

    idor_attempt = client.post(
        f"/api/v1/portal/applications/{victim_application_id}/documents",
        params={"doc_type": "passport"},
        files={"file": ("passport.png", _sharp_image_bytes(), "image/png")},
        headers={"Authorization": f"Bearer {attacker_token}"},
    )
    assert idor_attempt.status_code == 403


def test_customer_cannot_update_another_customers_application(client, db_session, tenant):
    victim = _make_customer(db_session, tenant, "victim2")
    attacker = _make_customer(db_session, tenant, "attacker2")

    victim_token = _login(client, victim.email, tenant.id)
    attacker_token = _login(client, attacker.email, tenant.id)

    create = client.post(
        "/api/v1/portal/applications",
        json={"customer_type": "individual", "full_name": "Victim Applicant"},
        headers={"Authorization": f"Bearer {victim_token}"},
    )
    victim_application_id = create.json()["id"]

    idor_attempt = client.put(
        f"/api/v1/portal/applications/{victim_application_id}",
        json={"full_name": "Renamed By Attacker"},
        headers={"Authorization": f"Bearer {attacker_token}"},
    )
    assert idor_attempt.status_code == 403


def test_case_from_another_tenant_is_invisible_not_just_forbidden(client, db_session, tenant):
    """RLS makes a cross-tenant case_id lookup return nothing at all - a 404,
    not a 403 - so an attacker probing IDs cannot distinguish "exists but
    not yours" from "does not exist"."""
    import pyotp

    from backend.app.models.cases import Case
    from backend.app.models.onboarding import Application, Customer
    from backend.app.services.auth.mfa_enrollment import confirm_totp_enrollment, start_totp_enrollment

    other_unique = uuid.uuid4().hex[:8]
    other_tenant = Tenant(name=f"IDOR Other {other_unique}", slug=f"idor-other-{other_unique}", region="NA")
    db_session.add(other_tenant)
    db_session.flush()

    other_customer = Customer(
        tenant_id=other_tenant.id, customer_type="individual",
        full_name_encrypted=b"x", full_name_blind_index="d" * 64,
    )
    db_session.add(other_customer)
    db_session.flush()
    other_application = Application(tenant_id=other_tenant.id, customer_id=other_customer.id, state="SCREENING")
    db_session.add(other_application)
    db_session.flush()
    other_case = Case(
        tenant_id=other_tenant.id, application_id=other_application.id,
        customer_id=other_customer.id, tier="review", state="PENDING_L1",
    )
    db_session.add(other_case)
    db_session.flush()

    role = db_session.execute(select(Role).where(Role.code == "compliance_analyst")).scalar_one()
    analyst = User(
        tenant_id=tenant.id,
        email=f"idor-analyst-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password(PASSWORD),
        full_name="IDOR Analyst",
    )
    db_session.add(analyst)
    db_session.flush()
    db_session.add(UserRole(user_id=analyst.id, role_id=role.id, tenant_id=tenant.id))
    db_session.commit()

    enrollment = start_totp_enrollment(db_session, analyst.id)
    db_session.commit()
    secret = pyotp.parse_uri(enrollment.provisioning_uri).secret
    confirm_totp_enrollment(db_session, analyst.id, pyotp.TOTP(secret).now())
    db_session.commit()

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": analyst.email, "password": PASSWORD, "tenant_id": tenant.id},
    )
    assert login_resp.json()["status"] == "mfa_required"
    verify_resp = client.post(
        "/api/v1/auth/mfa/verify",
        json={"user_id": login_resp.json()["user_id"], "code": pyotp.TOTP(secret).now(), "tenant_id": tenant.id},
    )
    token = verify_resp.json()["access_token"]

    cross_tenant_attempt = client.get(
        f"/api/v1/cases/{other_case.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert cross_tenant_attempt.status_code == 404

    db_session.execute(delete(Case).where(Case.tenant_id == other_tenant.id))
    db_session.execute(delete(Application).where(Application.tenant_id == other_tenant.id))
    db_session.execute(delete(Customer).where(Customer.tenant_id == other_tenant.id))
    db_session.execute(delete(UserRole).where(UserRole.user_id == analyst.id))
    db_session.execute(delete(User).where(User.id == analyst.id))
    db_session.execute(delete(Tenant).where(Tenant.id == other_tenant.id))
    db_session.commit()


def test_login_is_rate_limited(client, db_session, tenant):
    limit = get_settings().rate_limit_login
    max_attempts = int(limit.split("/")[0])

    statuses = []
    for _ in range(max_attempts + 2):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent@example.com", "password": "wrong", "tenant_id": tenant.id},
        )
        statuses.append(resp.status_code)

    assert 429 in statuses, f"expected a 429 within {max_attempts + 2} attempts, got {statuses}"
