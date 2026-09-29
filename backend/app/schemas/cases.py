from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


class CaseSummary(BaseModel):
    id: int
    tier: str
    state: str
    assignee_id: int | None
    sla_due_at: dt.datetime | None
    sla_breached: bool
    created_at: dt.datetime


class HitResponse(BaseModel):
    id: int
    entity_uid: int
    matched_name: str
    composite_score: float
    disposition: str
    disposition_reason: str | None
    scores: dict


class CaseDetail(BaseModel):
    id: int
    tenant_id: int
    application_id: int
    customer_id: int
    tier: str
    state: str
    assignee_id: int | None
    decision: str | None
    decided_by_id: int | None
    second_approver_id: int | None
    sla_due_at: dt.datetime | None
    sla_breached: bool
    hits: list[HitResponse]


class AssignRequest(BaseModel):
    assignee_id: int | None = None


class DispositionRequest(BaseModel):
    disposition: Literal["true_match", "false_positive"]
    reason_code: str


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject", "clear"]
    is_second_approval: bool = False


class RfiCreateRequest(BaseModel):
    message: str = Field(..., min_length=1)


class NoteCreateRequest(BaseModel):
    body: str = Field(..., min_length=1)


class BulkClearRequest(BaseModel):
    threshold: float = Field(..., ge=0, le=100)


class DecisionRationaleDraftRequest(BaseModel):
    proposed_decision: Literal["approve", "reject", "clear"]


class LlmDraftResponse(BaseModel):
    summary: str
    key_factors: list[str]
    suggested_action: str
    confidence: str
    source: str | None = None
