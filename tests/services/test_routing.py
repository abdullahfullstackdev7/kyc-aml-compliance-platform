from backend.app.services.screening.risk import RiskLevel
from backend.app.services.screening.routing import RoutingInput, Tier, route_case


def test_clear_when_low_score_low_risk_docs_pass():
    result = route_case(
        RoutingInput(top_score=40, customer_risk=RiskLevel.LOW, document_check_status="pass")
    )
    assert result.tier == Tier.CLEAR


def test_review_when_score_above_clear_threshold():
    result = route_case(
        RoutingInput(top_score=80, customer_risk=RiskLevel.LOW, document_check_status="pass")
    )
    assert result.tier == Tier.REVIEW
    assert result.sla_hours == 24


def test_review_when_customer_risk_high_even_with_low_score():
    result = route_case(
        RoutingInput(top_score=10, customer_risk=RiskLevel.HIGH, document_check_status="pass")
    )
    assert result.tier == Tier.REVIEW


def test_review_when_document_check_warns():
    result = route_case(
        RoutingInput(top_score=10, customer_risk=RiskLevel.LOW, document_check_status="warn")
    )
    assert result.tier == Tier.REVIEW


def test_high_risk_requires_score_and_corroboration():
    result = route_case(
        RoutingInput(
            top_score=95,
            customer_risk=RiskLevel.LOW,
            document_check_status="pass",
            has_corroborating_attribute=True,
        )
    )
    assert result.tier == Tier.HIGH_RISK
    assert result.sla_hours == 4
    assert result.requires_dual_approval_to_reject is True


def test_high_score_without_corroboration_falls_to_review():
    result = route_case(
        RoutingInput(top_score=95, customer_risk=RiskLevel.LOW, document_check_status="pass")
    )
    assert result.tier == Tier.REVIEW


def test_exact_id_match_counts_as_corroboration():
    result = route_case(
        RoutingInput(
            top_score=100,
            customer_risk=RiskLevel.LOW,
            document_check_status="pass",
            exact_id_match=True,
        )
    )
    assert result.tier == Tier.HIGH_RISK


def test_failed_document_check_always_rejects():
    result = route_case(
        RoutingInput(top_score=0, customer_risk=RiskLevel.LOW, document_check_status="fail")
    )
    assert result.tier == Tier.REJECT
    assert result.sla_hours is None


def test_reject_takes_priority_over_high_score():
    result = route_case(
        RoutingInput(
            top_score=99,
            customer_risk=RiskLevel.HIGH,
            document_check_status="fail",
            has_corroborating_attribute=True,
        )
    )
    assert result.tier == Tier.REJECT
