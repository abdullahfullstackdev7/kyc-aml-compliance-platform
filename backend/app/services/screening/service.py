"""Screening orchestration: normalize, retrieve candidates, score, rank.

Ties together normalize.py, candidates.py, scoring.py (Phase 3.1-3.3) into
the single entry point the API and evaluation harness both call.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.sanctions import SanctionsDob, SanctionsIdentifier, SanctionsNationality
from backend.app.services.screening.candidates import Candidate, generate_candidates, idf_weights
from backend.app.services.screening.embeddings import embed_text
from backend.app.services.screening.normalize import normalize_name
from backend.app.services.screening.scoring import (
    EntityAttributes,
    ScoreBreakdown,
    SecondaryAttributes,
    score_candidate,
)

DEFAULT_TOP_N = 10
DEFAULT_CANDIDATE_LIMIT = 50


@dataclass
class ScreeningQuery:
    full_name: str
    date_of_birth: dt.date | None = None
    nationality: str | None = None
    id_number: str | None = None
    entity_type: str | None = None  # "individual" | "entity"
    top_n: int = DEFAULT_TOP_N


@dataclass
class ScreeningHitResult:
    entity_id: int
    entity_uid: int
    source: str
    sdn_type: str | None
    primary_name: str
    matched_name: str
    programs: list[str]
    breakdown: ScoreBreakdown
    retrieval_methods: list[str]


@dataclass
class ScreeningResult:
    query_full_name: str
    query_normalized: str
    hits: list[ScreeningHitResult] = field(default_factory=list)
    candidate_count: int = 0
    duration_ms: float = 0.0


def fetch_entity_attributes(session: Session, entity_ids: set[int]) -> dict[int, EntityAttributes]:
    if not entity_ids:
        return {}

    attrs: dict[int, EntityAttributes] = {eid: EntityAttributes() for eid in entity_ids}

    for entity_id, dob, year in session.execute(
        select(SanctionsDob.entity_uid, SanctionsDob.date_of_birth, SanctionsDob.year_only).where(
            SanctionsDob.entity_uid.in_(entity_ids)
        )
    ):
        if dob is not None:
            attrs[entity_id].dobs.append(dob)
        if year is not None:
            attrs[entity_id].dob_years.append(year)

    for entity_id, country in session.execute(
        select(SanctionsNationality.entity_uid, SanctionsNationality.country).where(
            SanctionsNationality.entity_uid.in_(entity_ids)
        )
    ):
        attrs[entity_id].nationalities.append(country)

    for entity_id, id_number in session.execute(
        select(SanctionsIdentifier.entity_uid, SanctionsIdentifier.id_number).where(
            SanctionsIdentifier.entity_uid.in_(entity_ids)
        )
    ):
        attrs[entity_id].id_numbers.append(id_number)

    return attrs


def screen_name(
    session: Session,
    query: ScreeningQuery,
    *,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    use_embedding: bool = True,
) -> ScreeningResult:
    start = time.perf_counter()

    normalized = normalize_name(query.full_name)
    query_embedding = (
        embed_text(normalized.normalized) if use_embedding and normalized.normalized else None
    )

    candidates: list[Candidate] = generate_candidates(
        session,
        tokens=normalized.tokens,
        normalized=normalized.normalized,
        phonetic=normalized.phonetic,
        embedding=query_embedding,
        limit=candidate_limit,
    )

    idf = idf_weights(session, normalized.tokens)
    entity_ids = {c.entity_id for c in candidates}
    entity_attrs = fetch_entity_attributes(session, entity_ids)

    secondary = SecondaryAttributes(
        date_of_birth=query.date_of_birth,
        nationality=query.nationality,
        id_number=query.id_number,
        entity_type=query.entity_type,
    )

    scored: dict[int, tuple[ScoreBreakdown, Candidate]] = {}
    for candidate in candidates:
        breakdown = score_candidate(
            normalized,
            candidate,
            query_embedding=query_embedding,
            idf=idf,
            secondary=secondary,
            entity_attrs=entity_attrs.get(candidate.entity_id),
        )
        existing = scored.get(candidate.entity_id)
        if existing is None or breakdown.composite_score > existing[0].composite_score:
            scored[candidate.entity_id] = (breakdown, candidate)

    ranked = sorted(scored.values(), key=lambda pair: pair[0].composite_score, reverse=True)
    top = ranked[: query.top_n]

    hits = [
        ScreeningHitResult(
            entity_id=candidate.entity_id,
            entity_uid=candidate.entity_uid,
            source=candidate.source,
            sdn_type=candidate.sdn_type,
            primary_name=candidate.primary_name,
            matched_name=candidate.full_name,
            programs=candidate.programs,
            breakdown=breakdown,
            retrieval_methods=sorted(candidate.retrieval_methods),
        )
        for breakdown, candidate in top
    ]

    duration_ms = (time.perf_counter() - start) * 1000
    return ScreeningResult(
        query_full_name=query.full_name,
        query_normalized=normalized.normalized,
        hits=hits,
        candidate_count=len(candidates),
        duration_ms=duration_ms,
    )
