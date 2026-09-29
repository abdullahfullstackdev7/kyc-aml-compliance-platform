"""Composite name-match scoring (0-100) with secondary attribute adjustments.

See PROJECT_PLAN.md Phase 3.3. Weights and adjustment magnitudes come from
`risk_config.weights` (versioned, seeded with defaults in migration 0003) so
they can be tuned without a code change.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler

from backend.app.services.screening.candidates import Candidate
from backend.app.services.screening.normalize import NormalizedName

DEFAULT_WEIGHTS: dict[str, float] = {
    "token_set": 0.35,
    "token_sort": 0.25,
    "jaro_winkler": 0.25,
    "embedding": 0.15,
    "dob_exact_bonus": 10,
    "dob_year_bonus": 5,
    "dob_conflict_penalty": -25,
    "nationality_match_bonus": 5,
    "nationality_conflict_penalty": -10,
    "entity_type_mismatch_penalty": -30,
    "weak_aka_cap": 80,
    "rare_token_missing_penalty": 8,
    "rare_token_missing_cap": 25,
    "rare_idf_threshold": 2.0,
}

DOB_CONFLICT_YEARS = 2


@dataclass
class SecondaryAttributes:
    date_of_birth: dt.date | None = None
    nationality: str | None = None
    id_number: str | None = None
    entity_type: str | None = None  # "individual" | "entity"


@dataclass
class EntityAttributes:
    dobs: list[dt.date] = field(default_factory=list)
    dob_years: list[int] = field(default_factory=list)
    nationalities: list[str] = field(default_factory=list)
    id_numbers: list[str] = field(default_factory=list)


@dataclass
class ScoreBreakdown:
    composite_score: float
    name_score: float
    token_set_ratio: float
    token_sort_ratio: float
    jaro_winkler: float
    embedding_similarity: float | None
    adjustments: dict[str, float]
    forced: str | None = None  # e.g. "exact_id_match"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return max(0.0, min(1.0, dot))  # embeddings are L2-normalized, so dot == cosine


def _name_score(
    query: NormalizedName,
    candidate: Candidate,
    query_embedding: list[float] | None,
    weights: dict[str, float],
) -> tuple[float, float, float, float, float | None]:
    token_set = fuzz.token_set_ratio(query.normalized, candidate.normalized)
    token_sort = fuzz.token_sort_ratio(query.normalized, candidate.normalized)
    candidate_sorted_key = " ".join(sorted(candidate.tokens))
    jw = JaroWinkler.normalized_similarity(query.sorted_token_key, candidate_sorted_key) * 100

    embedding_sim: float | None = None
    if query_embedding and candidate.embedding:
        embedding_sim = _cosine_similarity(query_embedding, candidate.embedding) * 100

    if embedding_sim is not None:
        score = (
            weights["token_set"] * token_set
            + weights["token_sort"] * token_sort
            + weights["jaro_winkler"] * jw
            + weights["embedding"] * embedding_sim
        )
    else:
        remaining = weights["token_set"] + weights["token_sort"] + weights["jaro_winkler"]
        score = (
            weights["token_set"] / remaining * token_set
            + weights["token_sort"] / remaining * token_sort
            + weights["jaro_winkler"] / remaining * jw
        )

    return score, token_set, token_sort, jw, embedding_sim


def _rare_token_penalty(
    query: NormalizedName, candidate: Candidate, idf: dict[str, float], weights: dict[str, float]
) -> float:
    threshold = weights["rare_idf_threshold"]
    rare_tokens = [t for t in query.tokens if idf.get(t, 0.0) > threshold]
    missing = [t for t in rare_tokens if t not in candidate.tokens]
    penalty = min(
        len(missing) * weights["rare_token_missing_penalty"], weights["rare_token_missing_cap"]
    )
    return -penalty


def _secondary_adjustments(
    secondary: SecondaryAttributes | None,
    entity_attrs: EntityAttributes | None,
    candidate_sdn_type: str | None,
    weights: dict[str, float],
) -> tuple[dict[str, float], str | None]:
    adjustments: dict[str, float] = {}
    forced: str | None = None

    if secondary is None:
        return adjustments, forced

    if (
        secondary.id_number
        and entity_attrs
        and entity_attrs.id_numbers
        and secondary.id_number.strip().upper()
        in {i.strip().upper() for i in entity_attrs.id_numbers}
    ):
        return adjustments, "exact_id_match"

    if entity_attrs and secondary.date_of_birth:
        if secondary.date_of_birth in entity_attrs.dobs:
            adjustments["dob_exact_match"] = weights["dob_exact_bonus"]
        elif secondary.date_of_birth.year in entity_attrs.dob_years:
            adjustments["dob_year_match"] = weights["dob_year_bonus"]
        elif entity_attrs.dob_years:
            closest_gap = min(abs(secondary.date_of_birth.year - y) for y in entity_attrs.dob_years)
            if closest_gap > DOB_CONFLICT_YEARS:
                adjustments["dob_conflict"] = weights["dob_conflict_penalty"]

    if entity_attrs and secondary.nationality and entity_attrs.nationalities:
        normalized_nats = {n.strip().casefold() for n in entity_attrs.nationalities}
        if secondary.nationality.strip().casefold() in normalized_nats:
            adjustments["nationality_match"] = weights["nationality_match_bonus"]
        else:
            adjustments["nationality_conflict"] = weights["nationality_conflict_penalty"]

    if secondary.entity_type and candidate_sdn_type:
        candidate_is_individual = candidate_sdn_type == "Individual"
        query_is_individual = secondary.entity_type == "individual"
        if candidate_is_individual != query_is_individual:
            adjustments["entity_type_mismatch"] = weights["entity_type_mismatch_penalty"]

    return adjustments, forced


def score_candidate(
    query: NormalizedName,
    candidate: Candidate,
    *,
    query_embedding: list[float] | None = None,
    idf: dict[str, float] | None = None,
    secondary: SecondaryAttributes | None = None,
    entity_attrs: EntityAttributes | None = None,
    weights: dict[str, float] | None = None,
) -> ScoreBreakdown:
    weights = weights or DEFAULT_WEIGHTS
    idf = idf or {}

    name_score, token_set, token_sort, jw, embedding_sim = _name_score(
        query, candidate, query_embedding, weights
    )

    rare_penalty = _rare_token_penalty(query, candidate, idf, weights)
    adjustments: dict[str, float] = {}
    if rare_penalty:
        adjustments["rare_token_missing"] = rare_penalty

    secondary_adjustments, forced = _secondary_adjustments(
        secondary, entity_attrs, candidate.sdn_type, weights
    )
    adjustments.update(secondary_adjustments)

    if forced == "exact_id_match":
        composite = 100.0
    else:
        composite = name_score + sum(adjustments.values())
        if candidate.strength == "weak":
            composite = min(composite, weights["weak_aka_cap"])
        composite = max(0.0, min(100.0, composite))

    return ScoreBreakdown(
        composite_score=round(composite, 2),
        name_score=round(name_score, 2),
        token_set_ratio=round(token_set, 2),
        token_sort_ratio=round(token_sort, 2),
        jaro_winkler=round(jw, 2),
        embedding_similarity=round(embedding_sim, 2) if embedding_sim is not None else None,
        adjustments=adjustments,
        forced=forced,
    )
