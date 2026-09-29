"""Field-level PII encryption: AES-256-GCM envelope encryption with per-tenant
data encryption keys (DEKs), each DEK itself encrypted by a master key (KEK).

See PROJECT_PLAN.md Phase 4.3. The master key comes from environment
configuration in this deployment (`ENCRYPTION_MASTER_KEY`); a production
deployment would source it from a secret manager such as OpenBao instead.

Ciphertext layout (all bytes, concatenated): `key_version(1) || nonce(12) ||
ciphertext_with_tag`. The key version lets a DEK be rotated without having
to re-encrypt every ciphertext at once: old ciphertexts keep decrypting under
their original DEK version until a background job re-encrypts them.
"""

from __future__ import annotations

import base64
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.governance import DataEncryptionKey

NONCE_BYTES = 12
GCM_KEY_BYTES = 32


class EncryptionError(Exception):
    pass


@lru_cache(maxsize=1)
def _master_key() -> bytes:
    settings = get_settings()
    if not settings.encryption_master_key:
        raise EncryptionError("ENCRYPTION_MASTER_KEY is not configured")
    return base64.b64decode(settings.encryption_master_key)


def _wrap_dek(dek: bytes) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    aesgcm = AESGCM(_master_key())
    return nonce + aesgcm.encrypt(nonce, dek, None)


def encrypt_with_master_key(plaintext: str) -> bytes:
    """For platform authentication secrets (e.g. TOTP seeds) that belong to
    the auth system itself rather than to a tenant's business data, and so
    have no tenant DEK to encrypt under. Layout: nonce(12) || ciphertext_with_tag.
    """
    nonce = os.urandom(NONCE_BYTES)
    aesgcm = AESGCM(_master_key())
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ciphertext


def decrypt_with_master_key(blob: bytes) -> str:
    nonce, ciphertext = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    aesgcm = AESGCM(_master_key())
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


def _unwrap_dek(wrapped: bytes) -> bytes:
    nonce, ciphertext = wrapped[:NONCE_BYTES], wrapped[NONCE_BYTES:]
    aesgcm = AESGCM(_master_key())
    return aesgcm.decrypt(nonce, ciphertext, None)


def get_or_create_tenant_dek(session: Session, tenant_id: int) -> DataEncryptionKey:
    """Fetches the active DEK for a tenant, creating one on first use."""
    existing = (
        session.execute(
            select(DataEncryptionKey)
            .where(DataEncryptionKey.tenant_id == tenant_id, DataEncryptionKey.is_active.is_(True))
            .order_by(DataEncryptionKey.key_version.desc())
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing

    dek = AESGCM.generate_key(bit_length=GCM_KEY_BYTES * 8)
    record = DataEncryptionKey(
        tenant_id=tenant_id,
        key_version=1,
        encrypted_dek=_wrap_dek(dek),
        is_active=True,
    )
    session.add(record)
    session.flush()
    return record


def encrypt_pii(session: Session, tenant_id: int, plaintext: str) -> bytes:
    if not plaintext:
        raise EncryptionError("Cannot encrypt empty plaintext")

    dek_record = get_or_create_tenant_dek(session, tenant_id)
    dek = _unwrap_dek(dek_record.encrypted_dek)

    nonce = os.urandom(NONCE_BYTES)
    aesgcm = AESGCM(dek)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

    version_byte = dek_record.key_version.to_bytes(1, "big")
    return version_byte + nonce + ciphertext


def decrypt_pii(session: Session, tenant_id: int, blob: bytes) -> str:
    if len(blob) < 1 + NONCE_BYTES:
        raise EncryptionError("Ciphertext too short to contain a key version and nonce")

    key_version = blob[0]
    nonce = blob[1 : 1 + NONCE_BYTES]
    ciphertext = blob[1 + NONCE_BYTES :]

    dek_record = session.execute(
        select(DataEncryptionKey).where(
            DataEncryptionKey.tenant_id == tenant_id, DataEncryptionKey.key_version == key_version
        )
    ).scalar_one_or_none()
    if dek_record is None:
        raise EncryptionError(f"No DEK found for tenant {tenant_id} version {key_version}")

    dek = _unwrap_dek(dek_record.encrypted_dek)
    aesgcm = AESGCM(dek)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


def rotate_tenant_dek(session: Session, tenant_id: int) -> DataEncryptionKey:
    """Issues a new active DEK version for a tenant; old ciphertexts remain
    decryptable because old DEK versions are kept (is_active=False)."""
    current = (
        session.execute(
            select(DataEncryptionKey)
            .where(DataEncryptionKey.tenant_id == tenant_id, DataEncryptionKey.is_active.is_(True))
            .order_by(DataEncryptionKey.key_version.desc())
        )
        .scalars()
        .first()
    )

    next_version = (current.key_version + 1) if current else 1
    if current is not None:
        current.is_active = False

    dek = AESGCM.generate_key(bit_length=GCM_KEY_BYTES * 8)
    record = DataEncryptionKey(
        tenant_id=tenant_id,
        key_version=next_version,
        encrypted_dek=_wrap_dek(dek),
        is_active=True,
    )
    session.add(record)
    session.flush()
    return record
