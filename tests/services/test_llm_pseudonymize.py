"""build_case_payload's pseudonymization rules (PROJECT_PLAN.md Phase 6.4):
DOB reduced to year, only the top 3 hits, remarks truncated to 160 chars,
internal IDs replaced by a case-scoped alias. Uses real (but nonexistent-id)
queries against Postgres for the application/entity lookups, and plain
duck-typed objects for the case/customer/hits, since pseudonymize.py only
needs attribute access, not real persisted rows."""

from __future__ import annotations

from types import SimpleNamespace

from backend.app.services.llm.pseudonymize import build_case_payload

CASE = SimpleNamespace(id=42, application_id=-1, tier="review")
CUSTOMER = SimpleNamespace(nationality="Germany", residence_country="Germany", occupation="Engineer")


def _hit(entity_uid: int, score: float, name: str, programs=None, sdn_type=None):
    return SimpleNamespace(
        entity_uid=entity_uid,
        composite_score=score,
        matched_name=name,
        scores={"programs": programs or [], "sdn_type": sdn_type},
    )


def test_alias_replaces_internal_case_id(db_session):
    payload = build_case_payload(db_session, CASE, [], CUSTOMER, "Jamie Applicant", "1990-05-15")
    assert payload["alias"] == "case-42"


def test_dob_is_reduced_to_year_only(db_session):
    payload = build_case_payload(db_session, CASE, [], CUSTOMER, "Jamie Applicant", "1990-05-15")
    assert payload["dob_year"] == 1990
    assert "05" not in str(payload["dob_year"])


def test_dob_none_when_not_supplied(db_session):
    payload = build_case_payload(db_session, CASE, [], CUSTOMER, "Jamie Applicant", None)
    assert payload["dob_year"] is None


def test_only_top_three_hits_are_included(db_session):
    hits = [_hit(i, score=50 + i, name=f"Entity {i}") for i in range(5)]
    payload = build_case_payload(db_session, CASE, hits, CUSTOMER, "Jamie Applicant", None)
    assert len(payload["hits"]) == 3
    # highest scores first
    assert [h["score"] for h in payload["hits"]] == [54, 53, 52]


def test_application_full_name_is_retained_for_comparison(db_session):
    payload = build_case_payload(db_session, CASE, [], CUSTOMER, "Jamie Applicant", None)
    assert payload["name"] == "Jamie Applicant"


def test_no_application_row_degrades_doc_status_to_none(db_session):
    payload = build_case_payload(db_session, CASE, [], CUSTOMER, "Jamie Applicant", None)
    assert payload["doc_status"] is None
