"""Prompt text and versions. See PROJECT_PLAN.md Phase 6.3.1 (short static
system prompt, byte-identical across calls to benefit from provider prompt
caching) and 6.3.3 (strict JSON output schema, shared by both purposes so
the router and cache logic stay purpose-agnostic). 6.5: bump the version
constant whenever prompt text changes, since it is part of the cache key.
"""

from __future__ import annotations

CASE_SUMMARY_VERSION = "v1"
DECISION_RATIONALE_VERSION = "v1"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_factors": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "suggested_action": {
            "type": "string",
            "enum": ["clear", "escalate", "confirm_match", "request_info"],
        },
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["summary", "key_factors", "suggested_action", "confidence"],
}

CASE_SUMMARY_SYSTEM_PROMPT = (
    "You are a KYC/AML screening assistant. Given a case's screening hits and "
    "risk factors as JSON, return ONLY a JSON object matching the schema: "
    'summary (<=60 words), key_factors (<=4 short strings), suggested_action '
    "(clear|escalate|confirm_match|request_info), confidence (low|medium|high). "
    "Never state a final decision as fact; you only assist a human reviewer."
)

DECISION_RATIONALE_SYSTEM_PROMPT = (
    "You are a KYC/AML screening assistant. A reviewer has chosen a decision "
    "for this case (see proposed_decision in the JSON); return ONLY a JSON "
    "object matching the schema: summary (<=60 words, a draft decision "
    "rationale a reviewer can edit and submit), key_factors (<=4 short "
    "strings), suggested_action (the closest of clear|escalate|"
    "confirm_match|request_info to the reviewer's proposed_decision), "
    "confidence (low|medium|high). Never claim the decision is final; it is "
    "a draft for the reviewer to edit."
)

MAX_OUTPUT_TOKENS = 400
