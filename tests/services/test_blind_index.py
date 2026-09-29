from backend.app.core.security.blind_index import compute_blind_index


def test_deterministic():
    assert compute_blind_index("Ayman Al Zawahiri") == compute_blind_index("Ayman Al Zawahiri")


def test_normalizes_case_and_whitespace():
    assert compute_blind_index("Ayman Al Zawahiri") == compute_blind_index("  ayman al zawahiri  ")


def test_different_values_differ():
    assert compute_blind_index("Ayman Al Zawahiri") != compute_blind_index("Someone Else")


def test_output_is_sha256_hex():
    result = compute_blind_index("test")
    assert len(result) == 64
    int(result, 16)  # raises ValueError if not valid hex
