from __future__ import annotations

import datetime as dt

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

EMBEDDING_DIM = 384


class SanctionsListVersion(Base):
    __tablename__ = "sanctions_list_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    publish_date: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    record_count: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    etag: Mapped[str | None] = mapped_column(String(255))
    last_modified: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ingested")
    file_path: Mapped[str | None] = mapped_column(String(512))

    changes: Mapped[list[SanctionsChange]] = relationship(back_populates="version")

    __table_args__ = (Index("ix_sanctions_list_versions_source_fetched", "source", "fetched_at"),)


class SanctionsEntity(Base):
    __tablename__ = "sanctions_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="ofac_sdn")
    sdn_type: Mapped[str | None] = mapped_column(String(32))
    primary_name: Mapped[str] = mapped_column(Text, nullable=False)
    programs: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    remarks: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    first_seen_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("sanctions_list_versions.id")
    )
    last_seen_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("sanctions_list_versions.id")
    )
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    names: Mapped[list[SanctionsName]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    identifiers: Mapped[list[SanctionsIdentifier]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    dobs: Mapped[list[SanctionsDob]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    nationalities: Mapped[list[SanctionsNationality]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    addresses: Mapped[list[SanctionsAddress]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("source", "uid", name="uq_sanctions_entities_source_uid"),
        Index("ix_sanctions_entities_is_active", "is_active"),
    )


class SanctionsName(Base):
    __tablename__ = "sanctions_names"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_uid: Mapped[int] = mapped_column(
        ForeignKey("sanctions_entities.id", ondelete="CASCADE"), nullable=False
    )
    name_type: Mapped[str] = mapped_column(String(16), nullable=False)  # primary | aka
    aka_type: Mapped[str | None] = mapped_column(String(16))  # a.k.a. | f.k.a. | n.k.a.
    strength: Mapped[str] = mapped_column(String(8), nullable=False, default="strong")
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    phonetic: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    entity: Mapped[SanctionsEntity] = relationship(back_populates="names")

    __table_args__ = (
        Index("ix_sanctions_names_tokens", "tokens", postgresql_using="gin"),
        Index(
            "ix_sanctions_names_normalized_trgm",
            "normalized",
            postgresql_using="gin",
            postgresql_ops={"normalized": "gin_trgm_ops"},
        ),
        Index(
            "ix_sanctions_names_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class SanctionsIdentifier(Base):
    __tablename__ = "sanctions_identifiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_uid: Mapped[int] = mapped_column(
        ForeignKey("sanctions_entities.id", ondelete="CASCADE"), nullable=False
    )
    id_type: Mapped[str] = mapped_column(String(255), nullable=False)
    id_number: Mapped[str] = mapped_column(Text, nullable=False)
    id_country: Mapped[str | None] = mapped_column(String(128))
    issue_date: Mapped[dt.date | None] = mapped_column(Date)
    expiry_date: Mapped[dt.date | None] = mapped_column(Date)

    entity: Mapped[SanctionsEntity] = relationship(back_populates="identifiers")

    __table_args__ = (Index("ix_sanctions_identifiers_id_number", "id_number"),)


class SanctionsDob(Base):
    __tablename__ = "sanctions_dobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_uid: Mapped[int] = mapped_column(
        ForeignKey("sanctions_entities.id", ondelete="CASCADE"), nullable=False
    )
    date_of_birth: Mapped[dt.date | None] = mapped_column(Date)
    year_only: Mapped[int | None] = mapped_column(Integer)
    dob_text: Mapped[str | None] = mapped_column(String(128))

    entity: Mapped[SanctionsEntity] = relationship(back_populates="dobs")


class SanctionsNationality(Base):
    __tablename__ = "sanctions_nationalities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_uid: Mapped[int] = mapped_column(
        ForeignKey("sanctions_entities.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # nationality | citizenship
    country: Mapped[str] = mapped_column(String(128), nullable=False)

    entity: Mapped[SanctionsEntity] = relationship(back_populates="nationalities")


class SanctionsAddress(Base):
    __tablename__ = "sanctions_addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_uid: Mapped[int] = mapped_column(
        ForeignKey("sanctions_entities.id", ondelete="CASCADE"), nullable=False
    )
    address1: Mapped[str | None] = mapped_column(String(255))
    address2: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(128))
    state_province: Mapped[str | None] = mapped_column(String(128))
    postal_code: Mapped[str | None] = mapped_column(String(32))
    country: Mapped[str | None] = mapped_column(String(128))
    raw: Mapped[str | None] = mapped_column(Text)

    entity: Mapped[SanctionsEntity] = relationship(back_populates="addresses")


class SanctionsChange(Base):
    __tablename__ = "sanctions_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("sanctions_list_versions.id", ondelete="CASCADE"), nullable=False
    )
    entity_uid: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)  # added|removed|modified
    diff: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    version: Mapped[SanctionsListVersion] = relationship(back_populates="changes")

    __table_args__ = (Index("ix_sanctions_changes_version_type", "version_id", "change_type"),)
