import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import dagster as dg
import pandas as pd
from dagster import AssetCheckExecutionContext, AssetExecutionContext, SensorEvaluationContext
from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.models.sanctions import SanctionsListVersion
from backend.app.services.sanctions.fetcher import fetch_with_conditional_get
from backend.app.services.sanctions.loader import load_sdn_snapshot
from backend.app.services.sanctions.ofac_parser import (
    SdnEntry,
    iter_sdn_entries,
    parse_publish_info,
)
from backend.app.services.sanctions.rescreen import enqueue_customer_rescreen
from backend.app.services.screening.normalize import normalize_name
from sentinelkyc_pipelines.resources import DatabaseResource, EmbeddingModelResource

SOURCE = "ofac_sdn"


@dataclass
class RawFetchOutput:
    status: str  # "ingested" | "unchanged"
    source: str
    file_path: str | None
    sha256: str
    etag: str | None
    last_modified: str | None
    declared_record_count: int | None
    version_id: int


@dataclass
class ParsedOutput:
    status: str
    source: str
    version_id: int
    entries: list[SdnEntry] = field(default_factory=list)


@dataclass
class NormalizedOutput:
    status: str
    source: str
    version_id: int
    entries: list[SdnEntry] = field(default_factory=list)
    name_rows_by_uid: dict[int, list[dict]] = field(default_factory=dict)


@dataclass
class LoadOutput:
    status: str
    version_id: int
    added: int = 0
    removed: int = 0
    modified: int = 0
    unchanged: int = 0
    total_active: int = 0
    changed_uids: list[int] = field(default_factory=list)


@dg.asset(group_name="sanctions_ingestion", required_resource_keys={"db"})
def ofac_sdn_raw(context: AssetExecutionContext) -> RawFetchOutput:
    """Conditionally fetch the OFAC SDN XML export and record a new list version."""
    settings = get_settings()
    db: DatabaseResource = context.resources.db

    with db.session() as session:
        previous = session.execute(
            select(SanctionsListVersion)
            .where(SanctionsListVersion.source == SOURCE)
            .order_by(SanctionsListVersion.fetched_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        result = fetch_with_conditional_get(
            settings.ofac_sdn_url,
            previous_etag=previous.etag if previous else None,
            previous_last_modified=previous.last_modified if previous else None,
            previous_sha256=previous.sha256 if previous else None,
        )

        if result.status in ("not_modified", "unchanged"):
            context.log.info(f"OFAC SDN list unchanged (http_status={result.status})")
            return RawFetchOutput(
                status="unchanged",
                source=SOURCE,
                file_path=previous.file_path if previous else None,
                sha256=result.sha256 or (previous.sha256 if previous else ""),
                etag=result.etag or (previous.etag if previous else None),
                last_modified=result.last_modified
                or (previous.last_modified if previous else None),
                declared_record_count=previous.record_count if previous else None,
                version_id=previous.id if previous else 0,
            )

        assert result.body is not None and result.sha256 is not None

        directory = Path(settings.dataset_raw_dir) / "ofac" / "sdn"
        directory.mkdir(parents=True, exist_ok=True)
        tmp_path = directory / f"_tmp_{result.sha256[:12]}.xml"
        tmp_path.write_bytes(result.body)

        publish_info = parse_publish_info(tmp_path)
        publish_date_str = (
            publish_info.publish_date.isoformat() if publish_info.publish_date else "unknown-date"
        )
        final_path = directory / f"{publish_date_str}_{result.sha256[:8]}.xml"
        tmp_path.replace(final_path)

        version = SanctionsListVersion(
            source=SOURCE,
            publish_date=(
                dt.datetime.combine(publish_info.publish_date, dt.time(), tzinfo=dt.UTC)
                if publish_info.publish_date
                else None
            ),
            record_count=publish_info.record_count,
            sha256=result.sha256,
            etag=result.etag,
            last_modified=result.last_modified,
            status="ingested",
            file_path=str(final_path),
        )
        session.add(version)
        session.flush()
        version_id = version.id

    context.log.info(
        f"Fetched new OFAC SDN list version {version_id}: "
        f"{publish_info.record_count} declared records, published {publish_date_str}"
    )
    return RawFetchOutput(
        status="ingested",
        source=SOURCE,
        file_path=str(final_path),
        sha256=result.sha256,
        etag=result.etag,
        last_modified=result.last_modified,
        declared_record_count=publish_info.record_count,
        version_id=version_id,
    )


@dg.asset(group_name="sanctions_ingestion")
def ofac_sdn_parsed(context: AssetExecutionContext, ofac_sdn_raw: RawFetchOutput) -> ParsedOutput:
    """Stream-parse the SDN XML and enforce the minimum record count sanity floor."""
    if ofac_sdn_raw.status == "unchanged":
        context.log.info("Skipping parse: raw list unchanged")
        return ParsedOutput(
            status="unchanged", source=ofac_sdn_raw.source, version_id=ofac_sdn_raw.version_id
        )

    assert ofac_sdn_raw.file_path is not None

    settings = get_settings()
    entries = list(iter_sdn_entries(ofac_sdn_raw.file_path))

    if len(entries) < settings.ofac_min_record_count:
        raise dg.Failure(
            description=(
                f"Parsed record count {len(entries)} is below the minimum sanity floor "
                f"{settings.ofac_min_record_count}; refusing to load a truncated list"
            )
        )

    context.log.info(f"Parsed {len(entries)} SDN entries from {ofac_sdn_raw.file_path}")
    return ParsedOutput(
        status="ingested",
        source=ofac_sdn_raw.source,
        version_id=ofac_sdn_raw.version_id,
        entries=entries,
    )


@dg.asset_check(asset=ofac_sdn_parsed)
def check_unique_uid(ofac_sdn_parsed: ParsedOutput) -> dg.AssetCheckResult:
    if ofac_sdn_parsed.status == "unchanged":
        return dg.AssetCheckResult(passed=True, description="skipped: unchanged list")
    uids = [e.uid for e in ofac_sdn_parsed.entries]
    duplicate_count = len(uids) - len(set(uids))
    return dg.AssetCheckResult(
        passed=duplicate_count == 0, metadata={"duplicate_count": duplicate_count}
    )


@dg.asset_check(asset=ofac_sdn_parsed)
def check_no_null_primary_names(ofac_sdn_parsed: ParsedOutput) -> dg.AssetCheckResult:
    if ofac_sdn_parsed.status == "unchanged":
        return dg.AssetCheckResult(passed=True, description="skipped: unchanged list")
    null_count = sum(1 for e in ofac_sdn_parsed.entries if not e.primary_name.strip())
    return dg.AssetCheckResult(
        passed=null_count == 0, metadata={"null_primary_name_count": null_count}
    )


@dg.asset_check(asset=ofac_sdn_parsed, required_resource_keys={"db"})
def check_row_count_within_tolerance(
    context: AssetCheckExecutionContext, ofac_sdn_parsed: ParsedOutput
) -> dg.AssetCheckResult:
    if ofac_sdn_parsed.status == "unchanged":
        return dg.AssetCheckResult(passed=True, description="skipped: unchanged list")

    db: DatabaseResource = context.resources.db
    with db.session() as session:
        previous = session.execute(
            select(SanctionsListVersion)
            .where(
                SanctionsListVersion.source == ofac_sdn_parsed.source,
                SanctionsListVersion.status == "ingested",
                SanctionsListVersion.id != ofac_sdn_parsed.version_id,
            )
            .order_by(SanctionsListVersion.fetched_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    current = len(ofac_sdn_parsed.entries)
    if previous is None or not previous.record_count:
        return dg.AssetCheckResult(
            passed=True, description="no previous version to compare", metadata={"current": current}
        )

    lower = previous.record_count * 0.9
    upper = previous.record_count * 1.1
    passed = lower <= current <= upper
    return dg.AssetCheckResult(
        passed=passed,
        metadata={"current": current, "previous": previous.record_count},
    )


@dg.asset(group_name="sanctions_ingestion")
def sdn_normalized(
    context: AssetExecutionContext, ofac_sdn_parsed: ParsedOutput
) -> NormalizedOutput:
    """Normalize primary names and AKAs into tokens, phonetic keys and Parquet output."""
    if ofac_sdn_parsed.status == "unchanged":
        context.log.info("Skipping normalization: no new entries")
        return NormalizedOutput(
            status="unchanged", source=ofac_sdn_parsed.source, version_id=ofac_sdn_parsed.version_id
        )

    name_rows_by_uid: dict[int, list[dict]] = {}
    entity_records: list[dict] = []
    name_records: list[dict] = []

    for entry in ofac_sdn_parsed.entries:
        rows: list[dict] = []

        primary = normalize_name(entry.primary_name)
        if primary.normalized:
            rows.append(
                {
                    "name_type": "primary",
                    "aka_type": None,
                    "strength": "strong",
                    "full_name": entry.primary_name,
                    "normalized": primary.normalized,
                    "tokens": primary.tokens,
                    "phonetic": primary.phonetic,
                }
            )

        for aka in entry.akas:
            aka_full = " ".join(p for p in (aka.first_name, aka.last_name) if p)
            if not aka_full:
                continue
            normalized = normalize_name(aka_full)
            if not normalized.normalized:
                continue
            strength = "weak" if (aka.category or "").lower() == "weak" else "strong"
            rows.append(
                {
                    "name_type": "aka",
                    "aka_type": aka.aka_type,
                    "strength": strength,
                    "full_name": aka_full,
                    "normalized": normalized.normalized,
                    "tokens": normalized.tokens,
                    "phonetic": normalized.phonetic,
                }
            )

        name_rows_by_uid[entry.uid] = rows
        entity_records.append(
            {
                "uid": entry.uid,
                "sdn_type": entry.sdn_type,
                "primary_name": entry.primary_name,
                "programs": entry.programs,
            }
        )
        for row in rows:
            name_records.append({"entity_uid": entry.uid, **row})

    processed_dir = Path(get_settings().dataset_processed_dir)
    processed_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(entity_records).to_parquet(processed_dir / "sdn_entities.parquet", index=False)
    pd.DataFrame(name_records).to_parquet(processed_dir / "sdn_names.parquet", index=False)

    context.log.info(f"Normalized {len(name_records)} names across {len(entity_records)} entities")
    return NormalizedOutput(
        status="ingested",
        source=ofac_sdn_parsed.source,
        version_id=ofac_sdn_parsed.version_id,
        entries=ofac_sdn_parsed.entries,
        name_rows_by_uid=name_rows_by_uid,
    )


@dg.asset(group_name="sanctions_ingestion", required_resource_keys={"db", "embedding_model"})
def sdn_embeddings(
    context: AssetExecutionContext, sdn_normalized: NormalizedOutput
) -> NormalizedOutput:
    """Batch-embed only new or changed names, reusing previously computed vectors."""
    if sdn_normalized.status == "unchanged":
        context.log.info("Skipping embeddings: no new entries")
        return sdn_normalized

    settings = get_settings()
    db: DatabaseResource = context.resources.db
    embedding_model: EmbeddingModelResource = context.resources.embedding_model

    from backend.app.models.sanctions import SanctionsEntity, SanctionsName

    with db.session() as session:
        existing_rows = session.execute(
            select(SanctionsEntity.uid, SanctionsName.normalized, SanctionsName.embedding)
            .join(SanctionsName, SanctionsName.entity_uid == SanctionsEntity.id)
            .where(SanctionsEntity.source == sdn_normalized.source)
        ).all()
    reuse_cache = {
        (uid, normalized): embedding
        for uid, normalized, embedding in existing_rows
        if embedding is not None
    }

    to_embed_rows: list[dict] = []
    to_embed_texts: list[str] = []
    for uid, rows in sdn_normalized.name_rows_by_uid.items():
        for row in rows:
            key = (uid, row["normalized"])
            if key in reuse_cache:
                row["embedding"] = list(reuse_cache[key])
            else:
                to_embed_rows.append(row)
                to_embed_texts.append(row["normalized"])

    context.log.info(
        f"Embedding {len(to_embed_texts)} new or changed names "
        f"(reusing {len(reuse_cache)} previously computed vectors)"
    )
    if to_embed_texts:
        vectors = embedding_model.encode(to_embed_texts, batch_size=settings.embedding_batch_size)
        for row, vector in zip(to_embed_rows, vectors, strict=True):
            row["embedding"] = vector

    return sdn_normalized


@dg.asset(group_name="sanctions_ingestion", required_resource_keys={"db"})
def sdn_loaded(context: AssetExecutionContext, sdn_embeddings: NormalizedOutput) -> LoadOutput:
    """Upsert the snapshot into Postgres in one transaction and record the change set."""
    if sdn_embeddings.status == "unchanged":
        context.log.info("No changes to load")
        return LoadOutput(status="unchanged", version_id=sdn_embeddings.version_id)

    db: DatabaseResource = context.resources.db
    with db.session() as session:
        stats = load_sdn_snapshot(
            session,
            source=sdn_embeddings.source,
            version_id=sdn_embeddings.version_id,
            entries=sdn_embeddings.entries,
            name_rows_by_uid=sdn_embeddings.name_rows_by_uid,
        )
        version = session.get(SanctionsListVersion, sdn_embeddings.version_id)
        if version is not None:
            version.record_count = len(sdn_embeddings.entries)

    context.log.info(
        f"Loaded snapshot: +{stats.added} -{stats.removed} ~{stats.modified} "
        f"={stats.unchanged}, active={stats.total_active}"
    )
    return LoadOutput(
        status="ingested",
        version_id=sdn_embeddings.version_id,
        added=stats.added,
        removed=stats.removed,
        modified=stats.modified,
        unchanged=stats.unchanged,
        total_active=stats.total_active,
        changed_uids=stats.changed_uids,
    )


@dg.asset(group_name="sanctions_ingestion")
def delta_rescreen(context: AssetExecutionContext, sdn_loaded: LoadOutput) -> dict:
    """Enqueue rescreening for customers potentially affected by this list version."""
    if sdn_loaded.status == "unchanged" or not sdn_loaded.changed_uids:
        context.log.info("No sanctions changes to propagate; skipping rescreen dispatch")
        return {"notified_entities": 0, "affected_customers": 0}

    affected = enqueue_customer_rescreen(sdn_loaded.changed_uids)
    context.log.info(
        f"List update: {len(sdn_loaded.changed_uids)} entities changed in version "
        f"{sdn_loaded.version_id}; dispatched rescreening for {affected} customers"
    )
    return {"notified_entities": len(sdn_loaded.changed_uids), "affected_customers": affected}


sdn_ingestion_job = dg.define_asset_job(
    "sdn_ingestion_job",
    selection=dg.AssetSelection.assets(
        ofac_sdn_raw, ofac_sdn_parsed, sdn_normalized, sdn_embeddings, sdn_loaded, delta_rescreen
    ),
)

sdn_poll_schedule = dg.ScheduleDefinition(
    name="ofac_sdn_poll_schedule",
    job=sdn_ingestion_job,
    cron_schedule="0 */6 * * *",
)


@dg.sensor(job=sdn_ingestion_job, minimum_interval_seconds=3600, required_resource_keys={"db"})
def sdn_freshness_sensor(context: SensorEvaluationContext) -> dg.SkipReason:
    """Logs a warning if the last successful SDN ingest is older than the 48 hour policy."""
    db: DatabaseResource = context.resources.db
    with db.session() as session:
        latest = session.execute(
            select(SanctionsListVersion)
            .where(SanctionsListVersion.source == SOURCE, SanctionsListVersion.status == "ingested")
            .order_by(SanctionsListVersion.fetched_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    if latest is None:
        return dg.SkipReason("No successful OFAC SDN ingest has completed yet")

    age_hours = (dt.datetime.now(dt.UTC) - latest.fetched_at).total_seconds() / 3600
    if age_hours > 48:
        context.log.warning(
            f"OFAC SDN list has not refreshed in {age_hours:.1f} hours (freshness policy: 48h)"
        )
    return dg.SkipReason(f"last successful ingest {age_hours:.1f}h ago")
