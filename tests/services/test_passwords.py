import pytest

from backend.app.core.security.passwords import (
    PasswordPolicyError,
    hash_password,
    validate_password_policy,
    verify_password,
)


def test_rejects_short_password():
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("Short1!")


def test_rejects_common_password_even_if_long_enough():
    with pytest.raises(PasswordPolicyError):
        validate_password_policy("changepassword")


def test_accepts_strong_uncommon_password():
    validate_password_policy("Xk9#mQ7pL2vN!wR4")


def test_hash_and_verify_round_trip():
    password = "Correct-Horse-Battery-9"
    hashed = hash_password(password)
    assert verify_password(password, hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_hash_password_rejects_weak_input():
    with pytest.raises(PasswordPolicyError):
        hash_password("weak")


def test_hash_is_not_the_plaintext():
    password = "Correct-Horse-Battery-9"
    hashed = hash_password(password)
    assert password not in hashed
    assert hashed.startswith("$argon2id$")
