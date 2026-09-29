"""Case management service tests: queue assignment, disposition, four-eyes
decisions, bulk clear (L2-only), RFI. See PROJECT_PLAN.md Phase 5.4.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_settings
from backend.app.core.security.passwords import hash_password
from backend.app.core.security.permissions import AuthorizationError, Principal
from backend.app.models.cases import Case, CaseEvent
from backend.app.models.identity import Role, User, UserRole
from backend.app.models.onboarding import Application, Customer
from backend.app.models.screening import ScreeningHit, ScreeningRun
from backend.app.models.tenancy import Tenant
from backend.app.services.onboarding.case_service import (
    CaseServiceError,
    assign_case,
    bulk_clear_low_score_hits,
    decide_case,
    request_information,
    set_hit_disposition,
    sla_breached,
)


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
def fixture_case(db_session):
    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"Case Service Tenant {unique}", slug=f"case-service-{unique}", region="NA"
    )
    db_session.add(tenant)
    db_session.flush()

    analyst_role = db_session.execute(
        select(Role).where(Role.code == "compliance_analyst")
    ).scalar_one()
    reviewer_role = db_session.execute(
        select(Role).where(Role.code == "senior_reviewer")
    ).scalar_one()

    analyst = User(
        tenant_id=tenant.id,
        email=f"analyst-{unique}@example.com",
        password_hash=hash_password("AnalystPass!2024"),
        full_name="Analyst One",
        mfa_enabled=True,
    )
    reviewer1 = User(
        tenant_id=tenant.id,
        email=f"reviewer1-{unique}@example.com",
        password_hash=hash_password("Reviewer1Pass!2024"),
        full_name="Reviewer One",
        mfa_enabled=True,
    )
    reviewer2 = User(
        tenant_id=tenant.id,
        email=f"reviewer2-{unique}@example.com",
        password_hash=hash_password("Reviewer2Pass!2024"),
        full_name="Reviewer Two",
        mfa_enabled=True,
    )
    db_session.add_all([analyst, reviewer1, reviewer2])
    db_session.flush()
    db_session.add_all(
        [
            UserRole(user_id=analyst.id, role_id=analyst_role.id, tenant_id=tenant.id),
            UserRole(user_id=reviewer1.id, role_id=reviewer_role.id, tenant_id=tenant.id),
            UserRole(user_id=reviewer2.id, role_id=reviewer_role.id, tenant_id=tenant.id),
        ]
    )

    customer = Customer(
        tenant_id=tenant.id,
        customer_type="individual",
        full_name_encrypted=b"\x00fake",
        full_name_blind_index="a" * 64,
    )
    db_session.add(customer)
    db_session.flush()
    application = Application(tenant_id=tenant.id, customer_id=customer.id, state="SCREENING")
    db_session.add(application)
    db_session.flush()
    run = ScreeningRun(
        tenant_id=tenant.id, customer_id=customer.id, trigger="onboarding", status="completed"
    )
    db_session.add(run)
    db_session.flush()
    hit_low = ScreeningHit(
        tenant_id=tenant.id,
        screening_run_id=run.id,
        entity_uid=1,
        matched_name="Low Score Match",
        composite_score=55.0,
    )
    hit_high = ScreeningHit(
        tenant_id=tenant.id,
        screening_run_id=run.id,
        entity_uid=2,
        matched_name="High Score Match",
        composite_score=95.0,
    )
    db_session.add_all([hit_low, hit_high])
    case = Case(
        tenant_id=tenant.id,
        application_id=application.id,
        customer_id=customer.id,
        screening_run_id=run.id,
        tier="high_risk",
        state="PENDING_L2",
        sla_due_at=dt.datetime.now(dt.UTC)
        - dt.timedelta(hours=1),  # already breached, for the SLA test
    )
    db_session.add(case)
    db_session.commit()

    yield {
        "tenant": tenant,
        "analyst": analyst,
        "reviewer1": reviewer1,
        "reviewer2": reviewer2,
        "customer": customer,
        "case": case,
        "hit_low": hit_low,
        "hit_high": hit_high,
    }

    db_session.execute(delete(CaseEvent).where(CaseEvent.tenant_id == tenant.id))
    db_session.execute(delete(Case).where(Case.tenant_id == tenant.id))
    db_session.execute(delete(ScreeningHit).where(ScreeningHit.tenant_id == tenant.id))
    db_session.execute(delete(ScreeningRun).where(ScreeningRun.tenant_id == tenant.id))
    db_session.execute(delete(Application).where(Application.tenant_id == tenant.id))
    db_session.execute(delete(Customer).where(Customer.tenant_id == tenant.id))
    db_session.commit()


def test_assign_case_round_robin_picks_a_reviewer(db_session, fixture_case):
    case = fixture_case["case"]
    # Principal.roles is a claim, not DB-verified here, so any real user row
    # can stand in as the actor; what matters is that actor_id satisfies the
    # case_events/audit_log foreign keys.
    admin = Principal(
        user_id=fixture_case["analyst"].id,
        tenant_id=fixture_case["tenant"].id,
        roles=["platform_admin"],
    )
    assign_case(db_session, case, assignee_id=None, actor=admin)
    db_session.commit()
    assert case.assignee_id in (fixture_case["reviewer1"].id, fixture_case["reviewer2"].id)


def test_sla_breached_detects_overdue_open_case(fixture_case):
    assert sla_breached(fixture_case["case"]) is True


def test_disposition_requires_valid_reason_code(db_session, fixture_case):
    actor = Principal(
        user_id=fixture_case["reviewer1"].id,
        tenant_id=fixture_case["tenant"].id,
        roles=["senior_reviewer"],
    )
    with pytest.raises(CaseServiceError):
        set_hit_disposition(
            db_session,
            fixture_case["hit_low"],
            disposition="false_positive",
            reason_code="nonsense",
            actor=actor,
        )


def test_disposition_records_actor_and_reason(db_session, fixture_case):
    actor = Principal(
        user_id=fixture_case["reviewer1"].id,
        tenant_id=fixture_case["tenant"].id,
        roles=["senior_reviewer"],
    )
    hit = set_hit_disposition(
        db_session,
        fixture_case["hit_low"],
        disposition="false_positive",
        reason_code="confirmed_transliteration_variant",
        actor=actor,
    )
    db_session.commit()
    assert hit.disposition == "false_positive"
    assert hit.disposition_by_id == fixture_case["reviewer1"].id


def test_bulk_clear_requires_senior_reviewer(db_session, fixture_case):
    analyst_actor = Principal(
        user_id=fixture_case["analyst"].id,
        tenant_id=fixture_case["tenant"].id,
        roles=["compliance_analyst"],
    )
    with pytest.raises(AuthorizationError):
        bulk_clear_low_score_hits(
            db_session,
            fixture_case["case"],
            [fixture_case["hit_low"], fixture_case["hit_high"]],
            threshold=80.0,
            actor=analyst_actor,
        )


def test_bulk_clear_only_touches_hits_below_threshold(db_session, fixture_case):
    reviewer_actor = Principal(
        user_id=fixture_case["reviewer1"].id,
        tenant_id=fixture_case["tenant"].id,
        roles=["senior_reviewer"],
    )
    cleared = bulk_clear_low_score_hits(
        db_session,
        fixture_case["case"],
        [fixture_case["hit_low"], fixture_case["hit_high"]],
        threshold=80.0,
        actor=reviewer_actor,
    )
    db_session.commit()
    assert [h.id for h in cleared] == [fixture_case["hit_low"].id]
    assert fixture_case["hit_high"].disposition == "pending"


def test_high_risk_reject_requires_two_distinct_approvers(db_session, fixture_case):
    case = fixture_case["case"]
    case.assignee_id = fixture_case["reviewer1"].id
    db_session.commit()

    first = Principal(
        user_id=fixture_case["reviewer1"].id,
        tenant_id=fixture_case["tenant"].id,
        roles=["senior_reviewer"],
    )
    decide_case(db_session, case, decision="reject", actor=first, is_second_approval=False)
    db_session.commit()
    assert case.state == "PENDING_L2"  # still open, awaiting second approval

    with pytest.raises(AuthorizationError):
        decide_case(db_session, case, decision="reject", actor=first, is_second_approval=True)

    second = Principal(
        user_id=fixture_case["reviewer2"].id,
        tenant_id=fixture_case["tenant"].id,
        roles=["senior_reviewer"],
    )
    decide_case(db_session, case, decision="reject", actor=second, is_second_approval=True)
    db_session.commit()
    assert case.state == "REJECTED"
    assert case.second_approver_id == fixture_case["reviewer2"].id


def test_request_information_sets_rfi_state(db_session, fixture_case):
    case = fixture_case["case"]
    case.assignee_id = fixture_case["reviewer1"].id
    db_session.commit()
    actor = Principal(
        user_id=fixture_case["reviewer1"].id,
        tenant_id=fixture_case["tenant"].id,
        roles=["senior_reviewer"],
    )
    request_information(db_session, case, message="Please provide a clearer photo ID", actor=actor)
    db_session.commit()
    assert case.state == "RFI_REQUESTED"
