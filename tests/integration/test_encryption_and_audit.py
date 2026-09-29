"""Integration tests for field-level encryption (per-tenant DEKs) and the
audit hash chain, against the real running Postgres instance.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_settings
from backend.app.core.security.audit import verify_audit_chain, write_audit_event
from backend.app.core.security.encryption import (
    EncryptionError,
    decrypt_pii,
    encrypt_pii,
    rotate_tenant_dek,
)
from backend.app.models.governance import AuditLog, DataEncryptionKey
from backend.app.models.tenancy import Tenant


@pytest.fixture
def db_session():
    settings = get_settings()
    try:
        engine = create_engine(settings.sync_database_url())
        engine.connect().close()
    except Exception as exc:  # noqa: BLE001 - environment guard, any connection failure skips
        pytest.skip(f"Postgres not reachable for this test: {exc}")

    # expire_on_commit=False, matching the app's own session factory: without
    # it, any attribute access after commit() (e.g. asserting on a just-
    # written row) silently opens a new implicit transaction that then
    # outlives the test and deadlocks a fixture teardown that needs an
    # exclusive lock (dropping/recreating the audit_log trigger).
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def tenant(db_session):
    t = Tenant(name="Encryption Test Tenant", slug="encryption-test-tenant", region="NA")
    db_session.add(t)
    db_session.flush()
    db_session.commit()
    yield t
    db_session.execute(delete(DataEncryptionKey).where(DataEncryptionKey.tenant_id == t.id))
    db_session.execute(delete(Tenant).where(Tenant.id == t.id))
    db_session.commit()


def test_encrypt_decrypt_round_trip(db_session, tenant):
    ciphertext = encrypt_pii(db_session, tenant.id, "Ayman Al Zawahiri")
    db_session.commit()
    assert decrypt_pii(db_session, tenant.id, ciphertext) == "Ayman Al Zawahiri"


def test_ciphertext_is_not_plaintext(db_session, tenant):
    ciphertext = encrypt_pii(db_session, tenant.id, "sensitive-name")
    assert b"sensitive-name" not in ciphertext


def test_key_rotation_keeps_old_ciphertext_decryptable(db_session, tenant):
    ciphertext = encrypt_pii(db_session, tenant.id, "pre-rotation value")
    db_session.commit()

    rotate_tenant_dek(db_session, tenant.id)
    db_session.commit()

    assert decrypt_pii(db_session, tenant.id, ciphertext) == "pre-rotation value"

    new_ciphertext = encrypt_pii(db_session, tenant.id, "post-rotation value")
    assert new_ciphertext[0] == 2
    assert decrypt_pii(db_session, tenant.id, new_ciphertext) == "post-rotation value"


def test_cannot_decrypt_under_wrong_tenant(db_session, tenant):
    other = Tenant(name="Other Tenant", slug="encryption-test-other-tenant", region="NA")
    db_session.add(other)
    db_session.flush()

    ciphertext = encrypt_pii(db_session, tenant.id, "belongs to tenant one")
    db_session.commit()

    with pytest.raises(EncryptionError):
        decrypt_pii(db_session, other.id, ciphertext)

    db_session.execute(delete(Tenant).where(Tenant.id == other.id))
    db_session.commit()


def test_empty_plaintext_rejected(db_session, tenant):
    with pytest.raises(EncryptionError):
        encrypt_pii(db_session, tenant.id, "")


# --- Audit hash chain ---


@pytest.fixture
def clean_audit_log(db_session):
    yield
    from sqlalchemy import text

    engine = create_engine(get_settings().sync_database_url())
    Session = sessionmaker(bind=engine)
    with Session() as cleanup:
        cleanup.execute(text("DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log"))
        cleanup.execute(delete(AuditLog).where(AuditLog.resource_type == "audit_chain_test"))
        cleanup.execute(
            text(
                "CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log "
                "FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation()"
            )
        )
        cleanup.commit()


def test_audit_chain_valid_after_sequential_writes(db_session, clean_audit_log):
    write_audit_event(
        db_session,
        tenant_id=None,
        actor_id=None,
        actor_role="system",
        action="a1",
        resource_type="audit_chain_test",
        resource_id="1",
    )
    write_audit_event(
        db_session,
        tenant_id=None,
        actor_id=None,
        actor_role="system",
        action="a2",
        resource_type="audit_chain_test",
        resource_id="2",
    )
    db_session.commit()

    valid, broken_id = verify_audit_chain(db_session, None)
    db_session.commit()  # close the read transaction so teardown's DROP TRIGGER doesn't block on it
    assert valid is True
    assert broken_id is None


def test_audit_chain_links_entries_by_hash(db_session, clean_audit_log):
    first = write_audit_event(
        db_session,
        tenant_id=None,
        actor_id=None,
        actor_role="system",
        action="a1",
        resource_type="audit_chain_test",
        resource_id="1",
    )
    second = write_audit_event(
        db_session,
        tenant_id=None,
        actor_id=None,
        actor_role="system",
        action="a2",
        resource_type="audit_chain_test",
        resource_id="2",
    )
    db_session.commit()

    assert second.prev_hash == first.hash
    assert second.hash != first.hash


def test_audit_chain_detects_tampering(db_session, clean_audit_log):
    from sqlalchemy import text

    write_audit_event(
        db_session,
        tenant_id=None,
        actor_id=None,
        actor_role="system",
        action="a1",
        resource_type="audit_chain_test",
        resource_id="1",
    )
    write_audit_event(
        db_session,
        tenant_id=None,
        actor_id=None,
        actor_role="system",
        action="a2",
        resource_type="audit_chain_test",
        resource_id="2",
    )
    db_session.commit()

    # Simulate an attacker who bypassed the append-only trigger directly
    # (e.g. temporary superuser access outside the application).
    engine = create_engine(get_settings().sync_database_url())
    Session = sessionmaker(bind=engine)
    with Session() as tamper_session:
        tamper_session.execute(text("DROP TRIGGER audit_log_append_only ON audit_log"))
        tamper_session.execute(
            text(
                "UPDATE audit_log SET action = 'tampered' WHERE resource_type = 'audit_chain_test' AND action = 'a1'"
            )
        )
        tamper_session.execute(
            text(
                "CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log "
                "FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation()"
            )
        )
        tamper_session.commit()

    valid, broken_id = verify_audit_chain(db_session, None)
    db_session.commit()  # close the read transaction so teardown's DROP TRIGGER doesn't block on it
    assert valid is False
    assert broken_id is not None
