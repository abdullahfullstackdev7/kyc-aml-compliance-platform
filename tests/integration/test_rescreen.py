"""Continuous rescreening (PROJECT_PLAN.md Phase 5.5): find_affected_customers
reads real screening_hits/sanctions_entities, and rescreen_customer opens a
new case only when the (mocked, to avoid fuzzy-match flakiness) rescreen
result crosses into Review/High Risk territory.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_settings
from backend.app.models.cases import Case
from backend.app.models.onboarding import Application, Customer
from backend.app.models.sanctions import SanctionsEntity
from backend.app.models.screening import ScreeningHit, ScreeningRun
from backend.app.models.tenancy import Tenant
from backend.app.services.screening.scoring import ScoreBreakdown
from backend.app.services.screening.service import ScreeningHitResult, ScreeningResult
from backend.app.services.sanctions import rescreen


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
def tenant_and_customer(db_session):
    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(name=f"Rescreen Test {unique}", slug=f"rescreen-test-{unique}", region="NA")
    db_session.add(tenant)
    db_session.flush()

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
    # rescreen_customer looks up the customer's application via an existing
    # Case row (see rescreen.py), which every onboarded customer has - even
    # a Clear tier gets one (screening_integration.py always creates a
    # Case). Seed that precondition here so the fixture matches reality.
    initial_case = Case(
        tenant_id=tenant.id,
        application_id=application.id,
        customer_id=customer.id,
        tier="clear",
        state="CLEARED",
    )
    db_session.add(initial_case)
    db_session.flush()
    db_session.commit()

    yield tenant, customer, application

    db_session.execute(delete(Case).where(Case.tenant_id == tenant.id))
    db_session.execute(delete(ScreeningHit).where(ScreeningHit.tenant_id == tenant.id))
    db_session.execute(delete(ScreeningRun).where(ScreeningRun.tenant_id == tenant.id))
    db_session.execute(delete(Application).where(Application.tenant_id == tenant.id))
    db_session.execute(delete(Customer).where(Customer.tenant_id == tenant.id))
    db_session.commit()


def _fake_result(score: float | None) -> ScreeningResult:
    hits = []
    if score is not None:
        breakdown = ScoreBreakdown(
            composite_score=score,
            name_score=score,
            token_set_ratio=score,
            token_sort_ratio=score,
            jaro_winkler=score,
            embedding_similarity=None,
            adjustments={},
        )
        hits.append(
            ScreeningHitResult(
                entity_id=1,
                entity_uid=1,
                source="ofac_sdn",
                sdn_type="Individual",
                primary_name="Test Entity",
                matched_name="Test Entity",
                programs=[],
                breakdown=breakdown,
                retrieval_methods=["token"],
            )
        )
    return ScreeningResult(query_full_name="x", query_normalized="X", hits=hits, duration_ms=1.0)


def test_find_affected_customers_returns_empty_for_empty_input(db_session):
    assert rescreen.find_affected_customers(db_session, []) == []


def test_find_affected_customers_identifies_customer_with_matching_hit(
    db_session, tenant_and_customer
):
    tenant, customer, _application = tenant_and_customer

    entity = db_session.execute(select(SanctionsEntity).limit(1)).scalars().first()
    if entity is None:
        pytest.skip("no sanctions_entities loaded in this dev database")

    run = ScreeningRun(tenant_id=tenant.id, customer_id=customer.id, trigger="onboarding", status="completed")
    db_session.add(run)
    db_session.flush()
    db_session.add(
        ScreeningHit(
            tenant_id=tenant.id,
            screening_run_id=run.id,
            entity_uid=entity.uid,
            matched_name="whoever",
            composite_score=90,
        )
    )
    db_session.commit()

    affected = rescreen.find_affected_customers(db_session, [entity.id])
    assert customer.id in affected

    other_entity = db_session.execute(
        select(SanctionsEntity).where(SanctionsEntity.id != entity.id).limit(1)
    ).scalars().first()
    if other_entity is not None:
        assert customer.id not in rescreen.find_affected_customers(db_session, [other_entity.id])


def test_rescreen_customer_high_score_opens_a_case(db_session, tenant_and_customer, monkeypatch):
    # Score alone (without a corroborating secondary attribute) routes to
    # Review, not High Risk - see routing.py's high_risk_min branch, which
    # additionally requires has_corroborating_attribute/exact_id_match/FATF.
    # Either tier is enough to exercise rescreen.py's case-opening branch.
    tenant, customer, application = tenant_and_customer
    monkeypatch.setattr(rescreen, "screen_name", lambda session, query: _fake_result(95.0))

    run = rescreen.rescreen_customer(db_session, customer, "Full Name")
    db_session.commit()

    assert run.trigger == "rescreen"
    case = db_session.execute(
        select(Case).where(Case.customer_id == customer.id, Case.tier == "review")
    ).scalar_one_or_none()
    assert case is not None
    assert case.application_id == application.id
    assert case.state == "PENDING_L1"


def test_rescreen_customer_low_score_does_not_open_a_case(db_session, tenant_and_customer, monkeypatch):
    tenant, customer, _application = tenant_and_customer
    monkeypatch.setattr(rescreen, "screen_name", lambda session, query: _fake_result(None))

    rescreen.rescreen_customer(db_session, customer, "Full Name")
    db_session.commit()

    cases = db_session.execute(select(Case).where(Case.customer_id == customer.id)).scalars().all()
    assert [c.tier for c in cases] == ["clear"]  # only the seeded case, nothing new opened


def test_rescreen_customer_does_not_duplicate_an_existing_open_case(
    db_session, tenant_and_customer, monkeypatch
):
    tenant, customer, application = tenant_and_customer
    monkeypatch.setattr(rescreen, "screen_name", lambda session, query: _fake_result(95.0))

    rescreen.rescreen_customer(db_session, customer, "Full Name")
    db_session.commit()
    rescreen.rescreen_customer(db_session, customer, "Full Name")
    db_session.commit()

    open_cases = db_session.execute(
        select(Case).where(Case.customer_id == customer.id, Case.state == "PENDING_L1")
    ).scalars().all()
    assert len(open_cases) == 1
