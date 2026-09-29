import datetime as dt

from backend.app.services.screening.candidates import Candidate
from backend.app.services.screening.normalize import normalize_name
from backend.app.services.screening.scoring import (
    EntityAttributes,
    SecondaryAttributes,
    score_candidate,
)


def _candidate(full_name: str, strength: str = "strong", sdn_type: str = "Individual") -> Candidate:
    normalized = normalize_name(full_name)
    return Candidate(
        name_id=1,
        entity_id=1,
        entity_uid=100,
        source="ofac_sdn",
        sdn_type=sdn_type,
        primary_name=full_name,
        programs=["SDGT"],
        full_name=full_name,
        normalized=normalized.normalized,
        tokens=normalized.tokens,
        phonetic=normalized.phonetic,
        strength=strength,
        name_type="primary",
        embedding=None,
    )


def test_exact_match_scores_near_100():
    query = normalize_name("Ayman Al Zawahiri")
    candidate = _candidate("Ayman Al Zawahiri")
    breakdown = score_candidate(query, candidate)
    assert breakdown.composite_score >= 95


def test_unrelated_names_score_below_review_threshold():
    query = normalize_name("Ayman Al Zawahiri")
    candidate = _candidate("Maria Garcia Lopez")
    breakdown = score_candidate(query, candidate)
    assert breakdown.composite_score < 72  # below the default Review threshold


def test_weak_aka_is_capped():
    query = normalize_name("Ayman Al Zawahiri")
    candidate = _candidate("Ayman Al Zawahiri", strength="weak")
    breakdown = score_candidate(query, candidate)
    assert breakdown.composite_score <= 80


def test_exact_id_match_forces_100():
    query = normalize_name("Ayman Al Zawahiri")
    candidate = _candidate("Totally Different Name")
    secondary = SecondaryAttributes(id_number="ABC123")
    entity_attrs = EntityAttributes(id_numbers=["abc123"])
    breakdown = score_candidate(query, candidate, secondary=secondary, entity_attrs=entity_attrs)
    assert breakdown.composite_score == 100.0
    assert breakdown.forced == "exact_id_match"


def test_dob_exact_match_bonus_applied():
    query = normalize_name("Ayman Al Zawahiri")
    candidate = _candidate("Ayman Al Zawahiri")
    dob = dt.date(1951, 6, 19)
    secondary = SecondaryAttributes(date_of_birth=dob)
    entity_attrs = EntityAttributes(dobs=[dob], dob_years=[1951])
    breakdown = score_candidate(query, candidate, secondary=secondary, entity_attrs=entity_attrs)
    assert breakdown.adjustments.get("dob_exact_match") == 10
    assert breakdown.composite_score == 100.0  # already near-100 name score + bonus, clamped


def test_dob_conflict_penalty_applied():
    query = normalize_name("Ayman Al Zawahiri")
    candidate = _candidate("Ayman Al Zawahiri")
    secondary = SecondaryAttributes(date_of_birth=dt.date(1990, 1, 1))
    entity_attrs = EntityAttributes(dobs=[dt.date(1951, 6, 19)], dob_years=[1951])
    breakdown = score_candidate(query, candidate, secondary=secondary, entity_attrs=entity_attrs)
    assert breakdown.adjustments.get("dob_conflict") == -25


def test_entity_type_mismatch_penalty_applied():
    query = normalize_name("Acme Corp")
    candidate = _candidate("Acme Corp", sdn_type="Entity")
    secondary = SecondaryAttributes(entity_type="individual")
    breakdown = score_candidate(query, candidate, secondary=secondary)
    assert breakdown.adjustments.get("entity_type_mismatch") == -30


def test_nationality_match_and_conflict():
    query = normalize_name("Ayman Al Zawahiri")
    candidate = _candidate("Ayman Al Zawahiri")
    entity_attrs = EntityAttributes(nationalities=["Egypt"])

    match = score_candidate(
        query,
        candidate,
        secondary=SecondaryAttributes(nationality="Egypt"),
        entity_attrs=entity_attrs,
    )
    assert match.adjustments.get("nationality_match") == 5

    conflict = score_candidate(
        query,
        candidate,
        secondary=SecondaryAttributes(nationality="Yemen"),
        entity_attrs=entity_attrs,
    )
    assert conflict.adjustments.get("nationality_conflict") == -10


def test_rare_token_missing_penalty():
    query = normalize_name("Ayman Zawahiri")
    candidate = _candidate("Ayman Smith")
    idf = {"AYMAN": 1.0, "ZAWAHIRI": 9.5}
    breakdown = score_candidate(query, candidate, idf=idf)
    assert breakdown.adjustments.get("rare_token_missing", 0) < 0


def test_score_is_always_clamped_0_to_100():
    query = normalize_name("A")
    candidate = _candidate("Completely Different Long Name Entity")
    breakdown = score_candidate(query, candidate)
    assert 0.0 <= breakdown.composite_score <= 100.0
