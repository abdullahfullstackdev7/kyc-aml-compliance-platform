"""Risk-tiered routing: maps a screening result to a case tier and SLA.

See PROJECT_PLAN.md Phase 3.5. Thresholds come from `risk_config.thresholds`
(versioned, seeded with defaults in migration 0003) so they can be retuned
without a code change; the routing rules themselves (which conditions apply
at each threshold) are code because they encode compliance policy, not a
per-tenant tunable number.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from backend.app.services.screening.risk import RiskLevel

DEFAULT_THRESHOLDS: dict[str, float] = {
    "clear_max": 72,
    "review_max": 89,
    "high_risk_min": 90,
}

SLA_HOURS = {
    "review": 24,
    "high_risk": 4,
}


class Tier(StrEnum):
    CLEAR = "clear"
    REVIEW = "review"
    HIGH_RISK = "high_risk"
    REJECT = "reject"


@dataclass
class RoutingInput:
    top_score: float | None
    customer_risk: RiskLevel
    document_check_status: str | None  # "pass" | "warn" | "fail" | None
    has_corroborating_attribute: bool = False
    exact_id_match: bool = False
    is_fatf_call_for_action_jurisdiction: bool = False


@dataclass
class RoutingResult:
    tier: Tier
    reason: str
    sla_hours: int | None
    requires_dual_approval_to_reject: bool


def route_case(
    routing_input: RoutingInput, thresholds: dict[str, float] | None = None
) -> RoutingResult:
    thresholds = thresholds or DEFAULT_THRESHOLDS
    score = routing_input.top_score or 0.0

    if routing_input.document_check_status == "fail":
        return RoutingResult(
            tier=Tier.REJECT,
            reason="Document authenticity check failed",
            sla_hours=None,
            requires_dual_approval_to_reject=False,
        )

    corroborated = (
        routing_input.has_corroborating_attribute
        or routing_input.exact_id_match
        or routing_input.is_fatf_call_for_action_jurisdiction
    )
    if score >= thresholds["high_risk_min"] and corroborated:
        return RoutingResult(
            tier=Tier.HIGH_RISK,
            reason=f"Top hit score {score:.1f} at or above high-risk threshold with corroboration",
            sla_hours=SLA_HOURS["high_risk"],
            requires_dual_approval_to_reject=True,
        )

    if score > thresholds["clear_max"]:
        return RoutingResult(
            tier=Tier.REVIEW,
            reason=f"Top hit score {score:.1f} above the clear threshold",
            sla_hours=SLA_HOURS["review"],
            requires_dual_approval_to_reject=False,
        )

    if routing_input.customer_risk == RiskLevel.HIGH:
        return RoutingResult(
            tier=Tier.REVIEW,
            reason="Customer risk rated High",
            sla_hours=SLA_HOURS["review"],
            requires_dual_approval_to_reject=False,
        )

    if routing_input.document_check_status == "warn":
        return RoutingResult(
            tier=Tier.REVIEW,
            reason="Document check produced a warning",
            sla_hours=SLA_HOURS["review"],
            requires_dual_approval_to_reject=False,
        )

    return RoutingResult(
        tier=Tier.CLEAR,
        reason="Below clear threshold, risk not High, documents passed",
        sla_hours=None,
        requires_dual_approval_to_reject=False,
    )
