from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


class ApplicationCreateRequest(BaseModel):
    customer_type: Literal["individual", "entity"]
    full_name: str = Field(..., min_length=1, max_length=255)
    date_of_birth: dt.date | None = None
    nationality: str | None = None
    residence_country: str | None = None
    occupation: str | None = None
    source_of_funds: str | None = None
    expected_monthly_volume: int | None = None


class ApplicationUpdateRequest(BaseModel):
    full_name: str | None = None
    date_of_birth: dt.date | None = None
    nationality: str | None = None
    residence_country: str | None = None
    occupation: str | None = None
    source_of_funds: str | None = None
    expected_monthly_volume: int | None = None


class ApplicationResponse(BaseModel):
    id: int
    customer_id: int
    state: str
    created_at: dt.datetime
    submitted_at: dt.datetime | None
    decided_at: dt.datetime | None


class DocumentCheckResponse(BaseModel):
    check_type: str
    result: str
    details: dict


class DocumentUploadResponse(BaseModel):
    document_id: int
    checks: list[DocumentCheckResponse]
    overall_status: str


class ApplicationStatusResponse(BaseModel):
    id: int
    state: str
    tier: str | None = None
    case_id: int | None = None
    submitted_at: dt.datetime | None
    decided_at: dt.datetime | None
