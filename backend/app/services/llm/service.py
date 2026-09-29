"""Entry points for the two lazy LLM flows (Phase 6.1): case_summary and
decision_rationale_draft. Both go through the same cache -> router ->
template-fallback path and log every call to llm_calls (Phase 6.3.6).
"""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from backend.app.models.cases import Case
from backend.app.models.governance import LlmCall
from backend.app.services.llm import cache, prompts, router

_DECISION_TO_SUGGESTED_ACTION = {"approve": "clear", "clear": "clear", "reject": "escalate"}


def _template_fallback(payload: dict) -> dict:
    hits = payload.get("hits") or []
    top = hits[0] if hits else None
    summary = (
        f"Case {payload['alias']}, tier {payload['tier']}. Top match: {top['name']} "
        f"(score {top['score']})."
        if top
        else f"Case {payload['alias']}, tier {payload['tier']}. No screening hits recorded."
    )
    proposed_decision = str(payload.get("proposed_decision") or "")
    suggested_action = _DECISION_TO_SUGGESTED_ACTION.get(proposed_decision, "escalate")
    return {
        "summary": summary,
        "key_factors": [f"doc_status={payload.get('doc_status')}"],
        "suggested_action": suggested_action,
        "confidence": "low",
        "source": "Automated summary (assistant unavailable)",
    }


def _run(
    session: Session,
    *,
    purpose: str,
    prompt_version: str,
    system_prompt: str,
    payload: dict,
    tenant_id: int | None,
    case_id: int | None,
) -> dict:
    key = cache.cache_key(purpose, prompt_version, payload)
    cached = cache.get_cached(session, key)
    if cached is not None:
        session.add(
            LlmCall(
                tenant_id=tenant_id,
                case_id=case_id,
                provider="cache",
                model="cache",
                purpose=purpose,
                prompt_tokens=0,
                completion_tokens=0,
                cached_tokens=1,
                latency_ms=0,
                status="cached",
            )
        )
        session.flush()
        return cached

    start = time.monotonic()
    outcome = router.generate_json(
        purpose=purpose,
        system_prompt=system_prompt,
        user_payload=payload,
        max_tokens=prompts.MAX_OUTPUT_TOKENS,
    )

    if outcome.status == "ok" and outcome.result is not None:
        response = outcome.result.data
        cache.store_cached(
            session, key=key, purpose=purpose, prompt_version=prompt_version, response=response
        )
        session.add(
            LlmCall(
                tenant_id=tenant_id,
                case_id=case_id,
                provider=outcome.provider,
                model=outcome.result.model,
                purpose=purpose,
                prompt_tokens=outcome.result.prompt_tokens,
                completion_tokens=outcome.result.completion_tokens,
                cached_tokens=0,
                latency_ms=outcome.latency_ms,
                status="success",
            )
        )
        session.flush()
        return response

    response = _template_fallback(payload)
    session.add(
        LlmCall(
            tenant_id=tenant_id,
            case_id=case_id,
            provider="none",
            model="template",
            purpose=purpose,
            prompt_tokens=0,
            completion_tokens=0,
            cached_tokens=0,
            latency_ms=int((time.monotonic() - start) * 1000),
            status="fallback",
        )
    )
    session.flush()
    return response


def generate_case_summary(session: Session, case: Case, payload: dict) -> dict:
    return _run(
        session,
        purpose="case_summary",
        prompt_version=prompts.CASE_SUMMARY_VERSION,
        system_prompt=prompts.CASE_SUMMARY_SYSTEM_PROMPT,
        payload=payload,
        tenant_id=case.tenant_id,
        case_id=case.id,
    )


def generate_decision_rationale_draft(
    session: Session, case: Case, payload: dict, proposed_decision: str
) -> dict:
    draft_payload = {**payload, "proposed_decision": proposed_decision}
    return _run(
        session,
        purpose="decision_rationale_draft",
        prompt_version=prompts.DECISION_RATIONALE_VERSION,
        system_prompt=prompts.DECISION_RATIONALE_SYSTEM_PROMPT,
        payload=draft_payload,
        tenant_id=case.tenant_id,
        case_id=case.id,
    )
