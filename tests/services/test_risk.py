from backend.app.services.screening.risk import (
    CustomerRiskFactors,
    RiskLevel,
    compute_customer_risk,
)


def test_low_risk_baseline(db_session):
    factors = CustomerRiskFactors(
        customer_type="individual",
        nationality="Germany",
        residence_country="Germany",
        occupation="Software engineer",
        expected_monthly_volume=5000,
        document_check_status="pass",
    )
    result = compute_customer_risk(db_session, factors)
    assert result.level == RiskLevel.LOW


def test_high_risk_country_drives_overall_high(db_session):
    factors = CustomerRiskFactors(
        customer_type="individual",
        nationality="Iran",
        residence_country="Germany",
        occupation="Teacher",
        expected_monthly_volume=1000,
        document_check_status="pass",
    )
    result = compute_customer_risk(db_session, factors)
    assert result.level == RiskLevel.HIGH
    assert result.factors["nationality_risk"] == "high"


def test_high_risk_occupation_drives_overall_high(db_session):
    factors = CustomerRiskFactors(
        customer_type="individual",
        nationality="Germany",
        residence_country="Germany",
        occupation="Currency exchange operator",
        expected_monthly_volume=1000,
        document_check_status="pass",
    )
    result = compute_customer_risk(db_session, factors)
    assert result.level == RiskLevel.HIGH


def test_high_expected_volume_drives_overall_high(db_session):
    factors = CustomerRiskFactors(
        customer_type="individual",
        nationality="Germany",
        residence_country="Germany",
        occupation="Teacher",
        expected_monthly_volume=500_000,
        document_check_status="pass",
    )
    result = compute_customer_risk(db_session, factors)
    assert result.level == RiskLevel.HIGH


def test_failed_document_check_drives_overall_high(db_session):
    factors = CustomerRiskFactors(
        customer_type="individual",
        nationality="Germany",
        residence_country="Germany",
        occupation="Teacher",
        expected_monthly_volume=1000,
        document_check_status="fail",
    )
    result = compute_customer_risk(db_session, factors)
    assert result.level == RiskLevel.HIGH


def test_entity_customer_type_at_least_medium(db_session):
    factors = CustomerRiskFactors(
        customer_type="entity",
        nationality="Germany",
        residence_country="Germany",
        occupation=None,
        expected_monthly_volume=1000,
        document_check_status="pass",
    )
    result = compute_customer_risk(db_session, factors)
    assert result.level in (RiskLevel.MEDIUM, RiskLevel.HIGH)


def test_unknown_country_defaults_to_medium(db_session):
    factors = CustomerRiskFactors(
        customer_type="individual",
        nationality="Narnia",
        residence_country="Narnia",
        occupation="Teacher",
        expected_monthly_volume=1000,
        document_check_status="pass",
    )
    result = compute_customer_risk(db_session, factors)
    assert result.factors["nationality_risk"] == "medium"
