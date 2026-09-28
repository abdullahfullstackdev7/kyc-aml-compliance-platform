"""Onboarding domain: customers, applications, documents.

Customer PII columns are stored as ciphertext (`bytea`) with a companion blind
index (HMAC-SHA256 of the normalized plaintext) for equality lookups without
decryption. Field-level encryption itself is implemented in Phase 4; this
schema defines the storage shape so later phases only add the encrypt/decrypt
service, not a migration.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    customer_type: Mapped[str] = mapped_column(String(16), nullable=False)  # individual | entity

    full_name_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    full_name_blind_index: Mapped[str] = mapped_column(String(64), nullable=False)
    dob_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    address_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)

    nationality: Mapped[str | None] = mapped_column(String(128))
    residence_country: Mapped[str | None] = mapped_column(String(128))
    occupation: Mapped[str | None] = mapped_column(String(255))
    source_of_funds: Mapped[str | None] = mapped_column(String(255))
    expected_monthly_volume: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    submitted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    uploaded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DocumentCheck(Base):
    __tablename__ = "document_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    check_type: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)  # pass | warn | fail
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    checked_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
