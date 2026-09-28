from backend.app.services.screening.normalize import normalize_name


def test_transliterates_and_casefolds():
    result = normalize_name("Müller")
    assert result.normalized == "MULLER"


def test_strips_honorifics_and_punctuation():
    result = normalize_name("Dr. Ayman al-Zawahiri")
    assert "DR" not in result.tokens
    assert "AYMAN" in result.tokens
    assert "AL" in result.tokens
    assert "ZAWAHIRI" in result.tokens


def test_collapses_transliteration_variants():
    mohammed = normalize_name("Mohammed Ali")
    muhammad = normalize_name("Muhammad Ali")
    assert mohammed.normalized == muhammad.normalized


def test_legal_suffix_normalized_to_low_weight_token():
    result = normalize_name("Acme LLC")
    assert result.tokens[-1] == "SUFFIXCORP"


def test_empty_name_returns_empty_result():
    result = normalize_name("")
    assert result.normalized == ""
    assert result.tokens == []


def test_sorted_token_key_is_order_independent():
    a = normalize_name("Ayman Zawahiri")
    b = normalize_name("Zawahiri Ayman")
    assert a.sorted_token_key == b.sorted_token_key


def test_phonetic_keys_generated_for_tokens():
    result = normalize_name("Smith")
    assert result.phonetic
