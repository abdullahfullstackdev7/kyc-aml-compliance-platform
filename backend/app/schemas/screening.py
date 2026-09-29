from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


class ScreeningSearchRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    date_of_birth: dt.date | None = None
    nationality: str | None = None
    id_number: str | None = None
    entity_type: Literal["individual", "entity"] | None = None
    top_n: int = Field(default=10, ge=1, le=50)


class ScoreBreakdownResponse(BaseModel):
    composite_score: float
    name_score: float
    token_set_ratio: float
    token_sort_ratio: float
    jaro_winkler: float
    embedding_similarity: float | None
    adjustments: dict[str, float]
    forced: str | None


class ScreeningHitResponse(BaseModel):
    entity_uid: int
    source: str
    sdn_type: str | None
    primary_name: str
    matched_name: str
    programs: list[str]
    retrieval_methods: list[str]
    scores: ScoreBreakdownResponse


class ScreeningSearchResponse(BaseModel):
    query_full_name: str
    query_normalized: str
    candidate_count: int
    duration_ms: float
    hits: list[ScreeningHitResponse]
