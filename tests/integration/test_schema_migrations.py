"""Repository-layer tests against a fresh, disposable Postgres instance.

Spins up `pgvector/pgvector:pg16` via testcontainers, applies every Alembic
migration from scratch, and exercises the core cross-domain relationships
(tenant -> user -> customer -> application -> case) plus Row-Level Security.
This is the "migrations apply cleanly up and down; repository layer unit
tests pass against a testcontainers Postgres" exit criterion for Phase 2.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import sessionmaker
from testcontainers.community.postgres import PostgresContainer

from backend.app.models.cases import Case
from backend.app.models.identity import Role, User
from backend.app.models.onboarding import Application, Customer
from backend.app.models.tenancy import Tenant

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def migrated_db_url():
    with PostgresContainer("pgvector/pgvector:pg16", driver=None) as postgres:
        sync_url = postgres.get_connection_url().replace("postgresql://", "postgresql+psycopg2://")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(ROOT / "alembic.ini"),
                "upgrade",
                "head",
            ],
            check=True,
            cwd=ROOT,
            env={"DATABASE_URL_SYNC": sync_url, **_inherited_env()},
        )
        yield sync_url


def _inherited_env() -> dict:
    import os

    return dict(os.environ)


@pytest.fixture(scope="module")
def engine(migrated_db_url):
    return create_engine(migrated_db_url)


@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


def test_downgrade_and_upgrade_round_trip(migrated_db_url):
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), "downgrade", "base"],
        cwd=ROOT,
        env={"DATABASE_URL_SYNC": migrated_db_url, **_inherited_env()},
        check=False,
    )
    assert result.returncode == 0

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), "upgrade", "head"],
        cwd=ROOT,
        env={"DATABASE_URL_SYNC": migrated_db_url, **_inherited_env()},
        check=False,
    )
    assert result.returncode == 0


def test_tenant_user_customer_application_case_chain(session):
    tenant = Tenant(name="Northbridge Federal Credit Union", slug="northbridge-fcu", region="NA")
    session.add(tenant)
    session.flush()

    role = Role(code="compliance_analyst", name="Compliance Analyst")
    session.add(role)
    session.flush()

    user = User(
        tenant_id=tenant.id,
        email="analyst@northbridge.test",
        password_hash="argon2-hash-placeholder",
        full_name="Jordan Reviewer",
    )
    session.add(user)
    session.flush()

    customer = Customer(
        tenant_id=tenant.id,
        customer_type="individual",
        full_name_encrypted=b"\x00ciphertext",
        full_name_blind_index="a" * 64,
    )
    session.add(customer)
    session.flush()

    application = Application(tenant_id=tenant.id, customer_id=customer.id, state="SUBMITTED")
    session.add(application)
    session.flush()

    case = Case(
        tenant_id=tenant.id,
        application_id=application.id,
        customer_id=customer.id,
        tier="review",
        state="PENDING_L1",
        assignee_id=user.id,
    )
    session.add(case)
    session.commit()

    assert case.id is not None
    assert case.tier == "review"


def test_customer_requires_encrypted_name_columns(session):
    tenant = Tenant(name="Halcyon Pay", slug="halcyon-pay", region="EMEA")
    session.add(tenant)
    session.flush()

    with pytest.raises(IntegrityError):
        session.add(
            Customer(
                tenant_id=tenant.id,
                customer_type="individual",
                full_name_blind_index="b" * 64,
            )
        )
        session.flush()


def test_row_level_security_isolates_tenants(engine, migrated_db_url):
    with engine.connect() as conn:
        conn.execute(text("DROP ROLE IF EXISTS app_role_test"))
        conn.execute(
            text("CREATE ROLE app_role_test LOGIN PASSWORD 'test' NOSUPERUSER NOBYPASSRLS")
        )
        conn.execute(text("GRANT ALL ON ALL TABLES IN SCHEMA public TO app_role_test"))
        conn.execute(text("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO app_role_test"))
        conn.commit()

        tenant_a_id = conn.execute(
            text(
                "INSERT INTO tenants (name, slug, region) VALUES "
                "('RLS Test A', 'rls-test-a', 'NA') RETURNING id"
            )
        ).scalar_one()
        tenant_b_id = conn.execute(
            text(
                "INSERT INTO tenants (name, slug, region) VALUES "
                "('RLS Test B', 'rls-test-b', 'NA') RETURNING id"
            )
        ).scalar_one()
        conn.commit()

    restricted_url = make_url(migrated_db_url).set(username="app_role_test", password="test")
    restricted_engine = create_engine(restricted_url)

    try:
        with restricted_engine.connect() as conn:
            conn.execute(text("SET app.tenant_id = :t"), {"t": str(tenant_a_id)})
            conn.execute(
                text(
                    "INSERT INTO customers (tenant_id, customer_type, full_name_encrypted, "
                    "full_name_blind_index) VALUES (:t, 'individual', '\\x00', 'blind1')"
                ),
                {"t": tenant_a_id},
            )
            conn.commit()

            conn.execute(text("SET app.tenant_id = :t"), {"t": str(tenant_b_id)})
            conn.execute(
                text(
                    "INSERT INTO customers (tenant_id, customer_type, full_name_encrypted, "
                    "full_name_blind_index) VALUES (:t, 'individual', '\\x00', 'blind2')"
                ),
                {"t": tenant_b_id},
            )
            conn.commit()

            conn.execute(text("SET app.tenant_id = :t"), {"t": str(tenant_a_id)})
            rows = conn.execute(
                text("SELECT tenant_id FROM customers WHERE tenant_id IN (:a, :b)"),
                {"a": tenant_a_id, "b": tenant_b_id},
            ).fetchall()
            assert [r[0] for r in rows] == [tenant_a_id]

            conn.execute(text("SET app.tenant_id = :t"), {"t": str(tenant_b_id)})
            rows = conn.execute(
                text("SELECT tenant_id FROM customers WHERE tenant_id IN (:a, :b)"),
                {"a": tenant_a_id, "b": tenant_b_id},
            ).fetchall()
            assert [r[0] for r in rows] == [tenant_b_id]

            conn.execute(text("SET app.tenant_id = :t"), {"t": str(tenant_a_id)})
            with pytest.raises(DBAPIError, match="row-level security"):
                conn.execute(
                    text(
                        "INSERT INTO customers (tenant_id, customer_type, full_name_encrypted, "
                        "full_name_blind_index) VALUES (:t, 'individual', '\\x00', 'blind3')"
                    ),
                    {"t": tenant_b_id},
                )
                conn.commit()
    finally:
        restricted_engine.dispose()
        with engine.connect() as conn:
            conn.execute(
                text("DELETE FROM customers WHERE tenant_id IN (:a, :b)"),
                {"a": tenant_a_id, "b": tenant_b_id},
            )
            conn.execute(
                text("DELETE FROM tenants WHERE id IN (:a, :b)"),
                {"a": tenant_a_id, "b": tenant_b_id},
            )
            conn.execute(text("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_role_test"))
            conn.execute(text("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM app_role_test"))
            conn.execute(text("DROP ROLE IF EXISTS app_role_test"))
            conn.commit()
