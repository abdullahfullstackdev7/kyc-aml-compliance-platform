"""Loads a parsed, normalized, embedded SDN snapshot into Postgres in one transaction.

Entities are upserted by (source, uid). Entities that were active in a previous
version but are absent from the current snapshot are marked inactive rather than
deleted, so the audit trail and rescreening history stay intact. See
PROJECT_PLAN.md Phase 1, asset `sdn_loaded`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.models.sanctions import (
    SanctionsAddress,
    SanctionsChange,
    SanctionsDob,
    SanctionsEntity,
    SanctionsIdentifier,
    SanctionsName,
    SanctionsNationality,
)
from backend.app.services.sanctions.dob_parser import parse_dob
from backend.app.services.sanctions.ofac_parser import SdnEntry


@dataclass
class LoadStats:
    added: int = 0
    removed: int = 0
    modified: int = 0
    unchanged: int = 0
    total_active: int = 0
    changed_uids: list[int] = field(default_factory=list)


def _entry_fingerprint(entry: SdnEntry) -> dict:
    """A compact representation used to detect whether an entity actually changed."""
    return {
        "first_name": entry.first_name,
        "last_name": entry.last_name,
        "title": entry.title,
        "sdn_type": entry.sdn_type,
        "remarks": entry.remarks,
        "programs": sorted(entry.programs),
        "akas": sorted(
            (a.first_name or "", a.last_name or "", a.aka_type or "", a.category or "")
            for a in entry.akas
        ),
        "addresses": sorted(
            (a.address1 or "", a.city or "", a.country or "") for a in entry.addresses
        ),
        "identifiers": sorted((i.id_type or "", i.id_number or "") for i in entry.identifiers),
        "dobs": sorted(d.date_of_birth or "" for d in entry.dates_of_birth),
        "nationalities": sorted(n.country or "" for n in entry.nationalities),
    }


def load_sdn_snapshot(
    session: Session,
    *,
    source: str,
    version_id: int,
    entries: list[SdnEntry],
    name_rows_by_uid: dict[int, list[dict]],
) -> LoadStats:
    stats = LoadStats()

    existing_rows = (
        session.execute(select(SanctionsEntity).where(SanctionsEntity.source == source))
        .scalars()
        .all()
    )
    existing_by_uid: dict[int, SanctionsEntity] = {row.uid: row for row in existing_rows}

    new_uids = {e.uid for e in entries}
    removed = [row for uid, row in existing_by_uid.items() if row.is_active and uid not in new_uids]
    for row in removed:
        row.is_active = False
        stats.removed += 1
        stats.changed_uids.append(row.uid)
        session.add(
            SanctionsChange(
                version_id=version_id,
                entity_uid=row.uid,
                source=source,
                change_type="removed",
                diff={"primary_name": row.primary_name},
            )
        )

    new_entities: list[SanctionsEntity] = []
    touched_entities: list[SanctionsEntity] = []

    for entry in entries:
        fingerprint = _entry_fingerprint(entry)
        existing = existing_by_uid.get(entry.uid)

        if existing is None:
            row = SanctionsEntity(
                uid=entry.uid,
                source=source,
                sdn_type=entry.sdn_type,
                primary_name=entry.primary_name,
                programs=entry.programs,
                remarks=entry.remarks,
                is_active=True,
                first_seen_version_id=version_id,
                last_seen_version_id=version_id,
                raw=asdict(entry),
            )
            new_entities.append(row)
            touched_entities.append(row)
            stats.added += 1
            stats.changed_uids.append(entry.uid)
            session.add(
                SanctionsChange(
                    version_id=version_id,
                    entity_uid=entry.uid,
                    source=source,
                    change_type="added",
                    diff={"primary_name": entry.primary_name},
                )
            )
        else:
            previous_fingerprint = {
                k: v
                for k, v in (existing.raw or {}).items()
                if k
                in (
                    "first_name",
                    "last_name",
                    "title",
                    "sdn_type",
                    "remarks",
                    "programs",
                )
            }
            changed = (
                existing.raw is None or _entry_fingerprint_from_raw(existing.raw) != fingerprint
            )
            existing.sdn_type = entry.sdn_type
            existing.primary_name = entry.primary_name
            existing.programs = entry.programs
            existing.remarks = entry.remarks
            existing.is_active = True
            existing.last_seen_version_id = version_id
            existing.raw = asdict(entry)
            touched_entities.append(existing)
            if changed:
                stats.modified += 1
                stats.changed_uids.append(entry.uid)
                session.add(
                    SanctionsChange(
                        version_id=version_id,
                        entity_uid=entry.uid,
                        source=source,
                        change_type="modified",
                        diff={"before": previous_fingerprint, "after": fingerprint},
                    )
                )
            else:
                stats.unchanged += 1

    if new_entities:
        session.add_all(new_entities)
    session.flush()

    entity_pk_by_uid = {row.uid: row.id for row in touched_entities}

    touched_ids = list(entity_pk_by_uid.values())
    if touched_ids:
        session.execute(delete(SanctionsName).where(SanctionsName.entity_uid.in_(touched_ids)))
        session.execute(
            delete(SanctionsIdentifier).where(SanctionsIdentifier.entity_uid.in_(touched_ids))
        )
        session.execute(delete(SanctionsDob).where(SanctionsDob.entity_uid.in_(touched_ids)))
        session.execute(
            delete(SanctionsNationality).where(SanctionsNationality.entity_uid.in_(touched_ids))
        )
        session.execute(
            delete(SanctionsAddress).where(SanctionsAddress.entity_uid.in_(touched_ids))
        )

    name_objs: list[SanctionsName] = []
    identifier_objs: list[SanctionsIdentifier] = []
    dob_objs: list[SanctionsDob] = []
    nationality_objs: list[SanctionsNationality] = []
    address_objs: list[SanctionsAddress] = []

    for entry in entries:
        entity_id = entity_pk_by_uid.get(entry.uid)
        if entity_id is None:
            continue

        for name_row in name_rows_by_uid.get(entry.uid, []):
            name_objs.append(SanctionsName(entity_uid=entity_id, **name_row))

        for ident in entry.identifiers:
            identifier_objs.append(
                SanctionsIdentifier(
                    entity_uid=entity_id,
                    id_type=ident.id_type or "unknown",
                    id_number=ident.id_number or "",
                    id_country=ident.id_country,
                )
            )

        for dob in entry.dates_of_birth:
            exact, year = parse_dob(dob.date_of_birth)
            dob_objs.append(
                SanctionsDob(
                    entity_uid=entity_id,
                    date_of_birth=exact,
                    year_only=year,
                    dob_text=dob.date_of_birth,
                )
            )

        for nat in entry.nationalities:
            if nat.country:
                nationality_objs.append(
                    SanctionsNationality(
                        entity_uid=entity_id, kind="nationality", country=nat.country
                    )
                )
        for cit in entry.citizenships:
            if cit.country:
                nationality_objs.append(
                    SanctionsNationality(
                        entity_uid=entity_id, kind="citizenship", country=cit.country
                    )
                )

        for addr in entry.addresses:
            address_objs.append(
                SanctionsAddress(
                    entity_uid=entity_id,
                    address1=addr.address1,
                    address2=addr.address2,
                    city=addr.city,
                    state_province=addr.state_or_province,
                    postal_code=addr.postal_code,
                    country=addr.country,
                )
            )

    for chunk_objs in (name_objs, identifier_objs, dob_objs, nationality_objs, address_objs):
        if chunk_objs:
            session.add_all(chunk_objs)

    stats.total_active = (
        session.execute(
            select(SanctionsEntity).where(
                SanctionsEntity.source == source, SanctionsEntity.is_active.is_(True)
            )
        )
        .scalars()
        .all()
        .__len__()
    )

    return stats


def _entry_fingerprint_from_raw(raw: dict) -> dict:
    return {
        "first_name": raw.get("first_name"),
        "last_name": raw.get("last_name"),
        "title": raw.get("title"),
        "sdn_type": raw.get("sdn_type"),
        "remarks": raw.get("remarks"),
        "programs": sorted(raw.get("programs") or []),
        "akas": sorted(
            (
                a.get("first_name") or "",
                a.get("last_name") or "",
                a.get("aka_type") or "",
                a.get("category") or "",
            )
            for a in raw.get("akas") or []
        ),
        "addresses": sorted(
            (a.get("address1") or "", a.get("city") or "", a.get("country") or "")
            for a in raw.get("addresses") or []
        ),
        "identifiers": sorted(
            (i.get("id_type") or "", i.get("id_number") or "") for i in raw.get("identifiers") or []
        ),
        "dobs": sorted((d.get("date_of_birth") or "") for d in raw.get("dates_of_birth") or []),
        "nationalities": sorted((n.get("country") or "") for n in raw.get("nationalities") or []),
    }
