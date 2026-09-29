"""Customer risk scoring, independent of name-match scoring.

See PROJECT_PLAN.md Phase 3.4. Combines country risk (from `country_risk`,
seeded from FATF jurisdiction status), a coarse occupation risk heuristic,
entity-type opacity, expected transaction volume, and document check outcome
into a Low / Medium / High rating.

The full curated `occupations_risk.csv` reference dataset (PROJECT_PLAN.md
section 5.2) is introduced with the rest of the dataset scripts; until then
this module ships a small, explicit keyword table covering the clearest
higher-risk occupation categories (PEP-adjacent, cash-intensive, currency
exchange) so the scoring pipeline has real behavior rather than a stub.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.governance import CountryRisk

HIGH_RISK_OCCUPATION_KEYWORDS = (
    "politically exposed",
    "government official",
    "minister",
    "military officer",
    "money service",
    "money exchange",
    "currency exchange",
    "casino",
    "arms dealer",
    "precious metals dealer",
)

MEDIUM_RISK_OCCUPATION_KEYWORDS = (
    "real estate",
    "jewelry",
    "import",
    "export",
    "cash",
    "consultant",
)

HIGH_VOLUME_THRESHOLD = 250_000
MEDIUM_VOLUME_THRESHOLD = 50_000


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


_LEVEL_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}


def _max_level(*levels: RiskLevel) -> RiskLevel:
    return max(levels, key=lambda lvl: _LEVEL_ORDER[lvl])


@dataclass
class CustomerRiskFactors:
    customer_type: str  # "individual" | "entity"
    nationality: str | None
    residence_country: str | None
    occupation: str | None
    expected_monthly_volume: int | None
    document_check_status: str | None  # "pass" | "warn" | "fail" | None


@dataclass
class CustomerRiskResult:
    level: RiskLevel
    factors: dict[str, str]


def _country_risk_level(session: Session, country: str | None) -> RiskLevel:
    if not country:
        return RiskLevel.MEDIUM
    row = session.execute(
        select(CountryRisk.risk_level).where(CountryRisk.country == country)
    ).scalar_one_or_none()
    if row is None:
        return RiskLevel.MEDIUM
    return RiskLevel(row)


def _occupation_risk_level(occupation: str | None) -> RiskLevel:
    if not occupation:
        return RiskLevel.LOW
    lowered = occupation.casefold()
    if any(keyword in lowered for keyword in HIGH_RISK_OCCUPATION_KEYWORDS):
        return RiskLevel.HIGH
    if any(keyword in lowered for keyword in MEDIUM_RISK_OCCUPATION_KEYWORDS):
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _volume_risk_level(expected_monthly_volume: int | None) -> RiskLevel:
    if expected_monthly_volume is None:
        return RiskLevel.LOW
    if expected_monthly_volume >= HIGH_VOLUME_THRESHOLD:
        return RiskLevel.HIGH
    if expected_monthly_volume >= MEDIUM_VOLUME_THRESHOLD:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _entity_opacity_risk_level(customer_type: str) -> RiskLevel:
    return RiskLevel.MEDIUM if customer_type == "entity" else RiskLevel.LOW


def _document_check_risk_level(status: str | None) -> RiskLevel:
    if status == "fail":
        return RiskLevel.HIGH
    if status == "warn":
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def compute_customer_risk(session: Session, factors: CustomerRiskFactors) -> CustomerRiskResult:
    nationality_risk = _country_risk_level(session, factors.nationality)
    residence_risk = _country_risk_level(session, factors.residence_country)
    occupation_risk = _occupation_risk_level(factors.occupation)
    volume_risk = _volume_risk_level(factors.expected_monthly_volume)
    opacity_risk = _entity_opacity_risk_level(factors.customer_type)
    document_risk = _document_check_risk_level(factors.document_check_status)

    overall = _max_level(
        nationality_risk, residence_risk, occupation_risk, volume_risk, opacity_risk, document_risk
    )

    return CustomerRiskResult(
        level=overall,
        factors={
            "nationality_risk": nationality_risk.value,
            "residence_risk": residence_risk.value,
            "occupation_risk": occupation_risk.value,
            "volume_risk": volume_risk.value,
            "entity_opacity_risk": opacity_risk.value,
            "document_check_risk": document_risk.value,
        },
    )
