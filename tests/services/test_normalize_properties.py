"""Property-based tests for the name normalizer (PROJECT_PLAN.md Phase 10.1:
"normalizer (Hypothesis property tests)"). Complements the example-based
tests in test_normalize.py with invariants that must hold for any input,
including adversarial/garbage text the example tests don't think to try."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.app.services.screening.normalize import normalize_name

# Printable text, including non-Latin scripts (transliteration path) and
# punctuation/control-adjacent characters (robustness path); excludes only
# the null character, which Postgres text columns reject outright and is
# out of scope for a normalizer robustness property.
_NAME_TEXT = st.text(
    alphabet=st.characters(blacklist_characters="\x00", blacklist_categories=("Cs",)),
    max_size=80,
)


@given(_NAME_TEXT)
@settings(max_examples=200)
def test_never_raises_for_any_text_input(raw_name: str):
    normalize_name(raw_name)


@given(_NAME_TEXT)
@settings(max_examples=200)
def test_is_deterministic(raw_name: str):
    first = normalize_name(raw_name)
    second = normalize_name(raw_name)
    assert first.normalized == second.normalized
    assert first.tokens == second.tokens
    assert first.phonetic == second.phonetic


@given(_NAME_TEXT)
@settings(max_examples=200)
def test_sorted_token_key_is_a_permutation_of_tokens(raw_name: str):
    result = normalize_name(raw_name)
    if result.tokens:
        assert sorted(result.tokens) == result.sorted_token_key.split(" ")
    else:
        assert result.sorted_token_key == ""


@given(_NAME_TEXT)
@settings(max_examples=200)
def test_tokens_are_never_empty_strings(raw_name: str):
    result = normalize_name(raw_name)
    assert all(token != "" for token in result.tokens)


@given(_NAME_TEXT)
@settings(max_examples=200)
def test_tokens_contain_no_whitespace(raw_name: str):
    result = normalize_name(raw_name)
    assert all(" " not in token for token in result.tokens)


def test_empty_input_short_circuits_without_calling_the_pipeline():
    result = normalize_name("")
    assert result.normalized == ""
    assert result.tokens == []
    assert result.phonetic == []
