from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.schemas.screening import (
    ScoreBreakdownResponse,
    ScreeningHitResponse,
    ScreeningSearchRequest,
    ScreeningSearchResponse,
)
from backend.app.services.screening.service import ScreeningQuery, screen_name

router = APIRouter(prefix="/screening", tags=["screening"])


@router.post("/search", response_model=ScreeningSearchResponse)
def search(
    request: ScreeningSearchRequest, db: Session = Depends(get_db)
) -> ScreeningSearchResponse:
    query = ScreeningQuery(
        full_name=request.full_name,
        date_of_birth=request.date_of_birth,
        nationality=request.nationality,
        id_number=request.id_number,
        entity_type=request.entity_type,
        top_n=request.top_n,
    )
    result = screen_name(db, query)

    return ScreeningSearchResponse(
        query_full_name=result.query_full_name,
        query_normalized=result.query_normalized,
        candidate_count=result.candidate_count,
        duration_ms=round(result.duration_ms, 2),
        hits=[
            ScreeningHitResponse(
                entity_uid=hit.entity_uid,
                source=hit.source,
                sdn_type=hit.sdn_type,
                primary_name=hit.primary_name,
                matched_name=hit.matched_name,
                programs=hit.programs,
                retrieval_methods=hit.retrieval_methods,
                scores=ScoreBreakdownResponse(
                    composite_score=hit.breakdown.composite_score,
                    name_score=hit.breakdown.name_score,
                    token_set_ratio=hit.breakdown.token_set_ratio,
                    token_sort_ratio=hit.breakdown.token_sort_ratio,
                    jaro_winkler=hit.breakdown.jaro_winkler,
                    embedding_similarity=hit.breakdown.embedding_similarity,
                    adjustments=hit.breakdown.adjustments,
                    forced=hit.breakdown.forced,
                ),
            )
            for hit in result.hits
        ],
    )
