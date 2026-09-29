"""Candidate generation (blocking) for name screening.

Union of three retrievers, each returning up to `limit` candidates, plus a
cheap phonetic filter for short names. See PROJECT_PLAN.md Phase 3.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.models.sanctions import SanctionsEntity, SanctionsName, SanctionsTokenStats

DEFAULT_LIMIT = 50
TRIGRAM_THRESHOLD = 0.35
VECTOR_DISTANCE_THRESHOLD = 0.35
SHORT_NAME_TOKEN_COUNT = 2
TOKEN_POOL_CAP = 1000
SELECTIVE_IDF_FLOOR = 2.0


@dataclass
class Candidate:
    name_id: int
    entity_id: int
    entity_uid: int
    source: str
    sdn_type: str | None
    primary_name: str
    programs: list[str]
    full_name: str
    normalized: str
    tokens: list[str]
    phonetic: list[str]
    strength: str
    name_type: str
    embedding: list[float] | None
    retrieval_methods: set[str] = field(default_factory=set)


def _row_to_candidate(name: SanctionsName, entity: SanctionsEntity, method: str) -> Candidate:
    return Candidate(
        name_id=name.id,
        entity_id=entity.id,
        entity_uid=entity.uid,
        source=entity.source,
        sdn_type=entity.sdn_type,
        primary_name=entity.primary_name,
        programs=list(entity.programs or []),
        full_name=name.full_name,
        normalized=name.normalized,
        tokens=list(name.tokens or []),
        phonetic=list(name.phonetic or []),
        strength=name.strength,
        name_type=name.name_type,
        embedding=list(name.embedding) if name.embedding is not None else None,
        retrieval_methods={method},
    )


def idf_weights(session: Session, tokens: list[str]) -> dict[str, float]:
    if not tokens:
        return {}
    rows = session.execute(
        select(SanctionsTokenStats.token, SanctionsTokenStats.idf).where(
            SanctionsTokenStats.token.in_(tokens)
        )
    ).all()
    return dict(rows)


def token_candidates(
    session: Session,
    query_tokens: list[str],
    *,
    limit: int = DEFAULT_LIMIT,
    pool_cap: int = TOKEN_POOL_CAP,
    selective_idf_floor: float = SELECTIVE_IDF_FLOOR,
) -> list[Candidate]:
    """Blocking via the GIN token index, ranked by IDF-weighted overlap.

    Blocks on the selective (higher-IDF) query tokens only, falling back to
    every token when all of them are common. Without this, a query that is
    entirely common tokens (e.g. a bare legal suffix such as "SA") would pull
    in every name sharing that token, which for the most common tokens in
    this dataset is tens of thousands of rows.
    """
    if not query_tokens:
        return []

    idf = idf_weights(session, query_tokens)
    block_tokens = [t for t in query_tokens if idf.get(t, 99.0) >= selective_idf_floor]
    if not block_tokens:
        block_tokens = query_tokens

    rows = session.execute(
        select(SanctionsName, SanctionsEntity)
        .join(SanctionsEntity, SanctionsEntity.id == SanctionsName.entity_uid)
        .where(
            SanctionsName.tokens.op("&&")(block_tokens),
            SanctionsEntity.is_active.is_(True),
        )
        .limit(pool_cap)
    ).all()

    default_idf = 1.0
    scored = []
    for name, entity in rows:
        overlap = set(name.tokens or []) & set(query_tokens)
        weight = sum(idf.get(t, default_idf) for t in overlap)
        scored.append((weight, name, entity))

    scored.sort(key=lambda row: row[0], reverse=True)
    return [_row_to_candidate(name, entity, "token") for _, name, entity in scored[:limit]]


def trigram_candidates(
    session: Session,
    normalized_query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    threshold: float = TRIGRAM_THRESHOLD,
) -> list[Candidate]:
    """Blocking via pg_trgm similarity on the normalized name."""
    if not normalized_query:
        return []

    # `%` (not similarity(...) > x) is what lets Postgres use the pg_trgm GIN
    # index; the threshold is read from the pg_trgm.similarity_threshold GUC,
    # set per-transaction here rather than compared inline.
    session.execute(
        text("SET LOCAL pg_trgm.similarity_threshold = :threshold"), {"threshold": threshold}
    )
    rows = session.execute(
        text(
            """
            SELECT n.id, similarity(n.normalized, :q) AS sim
            FROM sanctions_names n
            JOIN sanctions_entities e ON e.id = n.entity_uid
            WHERE e.is_active = true AND n.normalized % :q
            ORDER BY sim DESC
            LIMIT :limit
            """
        ),
        {"q": normalized_query, "limit": limit},
    ).mappings()

    name_ids = [row["id"] for row in rows]
    if not name_ids:
        return []
    return _hydrate_candidates(session, name_ids, "trigram")


def vector_candidates(
    session: Session,
    query_embedding: list[float],
    *,
    limit: int = DEFAULT_LIMIT,
    max_distance: float = VECTOR_DISTANCE_THRESHOLD,
) -> list[Candidate]:
    """Blocking via HNSW approximate nearest neighbor on the name embedding."""
    if not query_embedding:
        return []

    vector_literal = "[" + ",".join(str(v) for v in query_embedding) + "]"
    rows = session.execute(
        text(
            """
            SELECT n.id, (n.embedding <=> :vec) AS distance
            FROM sanctions_names n
            JOIN sanctions_entities e ON e.id = n.entity_uid
            WHERE e.is_active = true AND n.embedding IS NOT NULL
            ORDER BY n.embedding <=> :vec
            LIMIT :limit
            """
        ),
        {"vec": vector_literal, "limit": limit},
    ).mappings()

    name_ids = [
        row["id"] for row in rows if row["distance"] is not None and row["distance"] < max_distance
    ]
    if not name_ids:
        return []
    return _hydrate_candidates(session, name_ids, "vector")


def phonetic_candidates(
    session: Session, phonetic_keys: list[str], *, limit: int = DEFAULT_LIMIT
) -> list[Candidate]:
    """Cheap phonetic-key filter, used as a fourth retriever for short names."""
    if not phonetic_keys:
        return []

    rows = session.execute(
        select(SanctionsName, SanctionsEntity)
        .join(SanctionsEntity, SanctionsEntity.id == SanctionsName.entity_uid)
        .where(
            SanctionsName.phonetic.op("&&")(phonetic_keys),
            SanctionsEntity.is_active.is_(True),
        )
        .limit(limit)
    ).all()
    return [_row_to_candidate(name, entity, "phonetic") for name, entity in rows]


def _hydrate_candidates(session: Session, name_ids: list[int], method: str) -> list[Candidate]:
    rows = session.execute(
        select(SanctionsName, SanctionsEntity)
        .join(SanctionsEntity, SanctionsEntity.id == SanctionsName.entity_uid)
        .where(SanctionsName.id.in_(name_ids))
    ).all()
    by_id = {name.id: (name, entity) for name, entity in rows}
    ordered = [by_id[nid] for nid in name_ids if nid in by_id]
    return [_row_to_candidate(name, entity, method) for name, entity in ordered]


def generate_candidates(
    session: Session,
    *,
    tokens: list[str],
    normalized: str,
    phonetic: list[str],
    embedding: list[float] | None,
    limit: int = DEFAULT_LIMIT,
) -> list[Candidate]:
    """Union of all retrievers, deduplicated by name id, methods merged."""
    all_candidates: dict[int, Candidate] = {}

    def _merge(batch: list[Candidate]) -> None:
        for c in batch:
            if c.name_id in all_candidates:
                all_candidates[c.name_id].retrieval_methods |= c.retrieval_methods
            else:
                all_candidates[c.name_id] = c

    _merge(token_candidates(session, tokens, limit=limit))
    _merge(trigram_candidates(session, normalized, limit=limit))
    if embedding:
        _merge(vector_candidates(session, embedding, limit=limit))
    if len(tokens) <= SHORT_NAME_TOKEN_COUNT:
        _merge(phonetic_candidates(session, phonetic, limit=limit))

    return list(all_candidates.values())
