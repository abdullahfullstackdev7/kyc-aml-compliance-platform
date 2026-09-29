"""Pre-aggregated analytics queries (PROJECT_PLAN.md Phase 9.4-9.5) against
real Postgres. These queries rely entirely on RLS for tenant isolation (no
explicit tenant_id filter in the SQL - see queries.py's docstring), so the
query-under-test must run through the restricted application role with
`app.tenant_id` set, exactly like the real API does via
get_tenant_scoped_db; a superuser session (this repo's other db_session
fixtures) would bypass RLS and see every tenant's rows. Fixture rows are
still created through the superuser session for simplicity.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from backend.app.api.deps import set_tenant_context
from backend.app.core.config import get_settings
from backend.app.models.cases import Case
from backend.app.models.governance import AuditLog, LlmCall
from backend.app.models.onboarding import Application, Customer
from backend.app.models.screening import ScreeningRun
from backend.app.models.tenancy import Tenant
from backend.app.services.analytics import queries


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
def app_session_for(db_session):
    """Returns a factory that opens a fresh restricted-role session scoped
    (via RLS) to the given tenant - fresh per call since SET LOCAL only
    lasts one transaction."""
    settings = get_settings()
    try:
        engine = create_engine(settings.app_sync_database_url())
        engine.connect().close()
    except Exception as exc:  # noqa: BLE001 - environment guard
        pytest.skip(f"Restricted app role not reachable: {exc}")

    Session = sessionmaker(bind=engine, expire_on_commit=False)
    opened = []

    def _factory(tenant_id: int):
        session = Session()
        set_tenant_context(session, tenant_id)
        opened.append(session)
        return session

    yield _factory

    for session in opened:
        session.rollback()
        session.close()


@pytest.fixture
def tenant(db_session):
    unique = uuid.uuid4().hex[:8]
    t = Tenant(name=f"Analytics Query Test {unique}", slug=f"analytics-query-test-{unique}", region="NA")
    db_session.add(t)
    db_session.flush()
    db_session.commit()
    yield t
    db_session.execute(delete(Case).where(Case.tenant_id == t.id))
    db_session.execute(delete(ScreeningRun).where(ScreeningRun.tenant_id == t.id))
    db_session.execute(delete(Customer).where(Customer.tenant_id == t.id))
    db_session.execute(delete(Application).where(Application.tenant_id == t.id))
    db_session.execute(delete(LlmCall).where(LlmCall.tenant_id == t.id))
    # audit_log is append-only (Phase 4.4) even for a superuser; the
    # unique-per-run tenant slug is what keeps these test rows from
    # colliding across runs, not cleanup.
    db_session.commit()


def _audit_state(db_session, tenant_id, resource_id, state):
    db_session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_id=None,
            actor_role="system",
            action="transition",
            resource_type="application",
            resource_id=str(resource_id),
            after={"state": state},
            prev_hash="0" * 64,
            hash=uuid.uuid4().hex + uuid.uuid4().hex,
        )
    )


def test_applications_funnel_counts_distinct_applications_per_milestone(
    db_session, app_session_for, tenant
):
    _audit_state(db_session, tenant.id, 1001, "SUBMITTED")
    _audit_state(db_session, tenant.id, 1001, "DOCS_VERIFIED")
    _audit_state(db_session, tenant.id, 1001, "SCREENING")
    _audit_state(db_session, tenant.id, 1001, "AUTO_APPROVED")
    _audit_state(db_session, tenant.id, 1002, "SUBMITTED")
    db_session.commit()

    scoped = app_session_for(tenant.id)
    funnel = queries.applications_funnel(scoped)
    assert funnel == {"submitted": 2, "docs_verified": 1, "screened": 1, "decided": 1}


def test_routing_distribution_groups_by_tier(db_session, app_session_for, tenant):
    customer = Customer(
        tenant_id=tenant.id, customer_type="individual", full_name_encrypted=b"x", full_name_blind_index="a" * 64
    )
    db_session.add(customer)
    db_session.flush()
    application = Application(tenant_id=tenant.id, customer_id=customer.id, state="SCREENING")
    db_session.add(application)
    db_session.flush()
    db_session.add_all(
        [
            Case(tenant_id=tenant.id, application_id=application.id, customer_id=customer.id, tier="review", state="PENDING_L1"),
            Case(tenant_id=tenant.id, application_id=application.id, customer_id=customer.id, tier="review", state="PENDING_L1"),
            Case(tenant_id=tenant.id, application_id=application.id, customer_id=customer.id, tier="high_risk", state="PENDING_L2"),
        ]
    )
    db_session.commit()

    scoped = app_session_for(tenant.id)
    distribution = {row["tier"]: row["count"] for row in queries.routing_distribution(scoped)}
    assert distribution == {"review": 2, "high_risk": 1}


def test_sla_compliance_counts_breached_open_cases_only(db_session, app_session_for, tenant):
    customer = Customer(
        tenant_id=tenant.id, customer_type="individual", full_name_encrypted=b"x", full_name_blind_index="b" * 64
    )
    db_session.add(customer)
    db_session.flush()
    application = Application(tenant_id=tenant.id, customer_id=customer.id, state="SCREENING")
    db_session.add(application)
    db_session.flush()

    now = dt.datetime.now(dt.UTC)
    db_session.add_all(
        [
            # breached: open state, due in the past
            Case(
                tenant_id=tenant.id, application_id=application.id, customer_id=customer.id,
                tier="review", state="PENDING_L1", sla_due_at=now - dt.timedelta(hours=1),
            ),
            # on track: open state, due in the future
            Case(
                tenant_id=tenant.id, application_id=application.id, customer_id=customer.id,
                tier="review", state="PENDING_L1", sla_due_at=now + dt.timedelta(hours=1),
            ),
            # decided (CLEARED): past-due SLA does not count as breached once closed
            Case(
                tenant_id=tenant.id, application_id=application.id, customer_id=customer.id,
                tier="review", state="CLEARED", sla_due_at=now - dt.timedelta(hours=5),
            ),
        ]
    )
    db_session.commit()

    scoped = app_session_for(tenant.id)
    assert queries.sla_compliance(scoped) == {"breached": 1, "on_track": 1}


def test_llm_usage_aggregates_calls_and_cache_hit_rate(db_session, app_session_for, tenant):
    db_session.add_all(
        [
            LlmCall(tenant_id=tenant.id, provider="groq", model="m", purpose="case_summary", prompt_tokens=10, completion_tokens=5, status="success"),
            LlmCall(tenant_id=tenant.id, provider="cache", model="cache", purpose="case_summary", prompt_tokens=0, completion_tokens=0, status="cached"),
            LlmCall(tenant_id=tenant.id, provider="cache", model="cache", purpose="case_summary", prompt_tokens=0, completion_tokens=0, status="cached"),
            LlmCall(tenant_id=tenant.id, provider="none", model="template", purpose="case_summary", prompt_tokens=0, completion_tokens=0, status="fallback"),
        ]
    )
    db_session.commit()

    scoped = app_session_for(tenant.id)
    result = queries.llm_usage(scoped)
    assert result["total_calls"] == 4
    assert result["cache_hit_rate"] == 0.5


def test_daily_screening_volume_only_counts_recent_runs(db_session, app_session_for, tenant):
    customer = Customer(
        tenant_id=tenant.id, customer_type="individual", full_name_encrypted=b"x", full_name_blind_index="c" * 64
    )
    db_session.add(customer)
    db_session.flush()

    recent = ScreeningRun(tenant_id=tenant.id, customer_id=customer.id, trigger="onboarding", status="completed")
    db_session.add(recent)
    old = ScreeningRun(tenant_id=tenant.id, customer_id=customer.id, trigger="onboarding", status="completed")
    db_session.add(old)
    db_session.flush()
    db_session.query(ScreeningRun).filter(ScreeningRun.id == old.id).update(
        {"started_at": dt.datetime.now(dt.UTC) - dt.timedelta(days=60)}
    )
    db_session.commit()

    scoped = app_session_for(tenant.id)
    volume = queries.daily_screening_volume(scoped, days=30)
    total = sum(row["count"] for row in volume)
    assert total == 1
