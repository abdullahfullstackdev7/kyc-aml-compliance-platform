import pyotp

from backend.app.core.security.mfa import (
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    hash_recovery_codes,
    provisioning_uri,
    verify_and_consume_recovery_code,
    verify_totp_code,
)


def test_provisioning_uri_contains_account_and_issuer():
    secret = generate_totp_secret()
    uri = provisioning_uri(secret, account_email="user@example.com")
    assert "user%40example.com" in uri or "user@example.com" in uri
    assert "SentinelKYC" in uri


def test_valid_totp_code_accepted():
    secret = generate_totp_secret()
    code = pyotp.TOTP(secret).now()
    assert verify_totp_code(secret, code) is True


def test_invalid_totp_code_rejected():
    secret = generate_totp_secret()
    assert verify_totp_code(secret, "000000") is False


def test_recovery_codes_are_unique_and_correct_count():
    codes = generate_recovery_codes()
    assert len(codes) == 10
    assert len(set(codes)) == 10


def test_recovery_code_hash_is_normalized():
    assert hash_recovery_code("ABCD-1234") == hash_recovery_code("abcd-1234")
    assert hash_recovery_code("ABCD-1234") == hash_recovery_code("ABCD1234")


def test_recovery_code_consumed_once():
    codes = generate_recovery_codes(count=3)
    hashed = hash_recovery_codes(codes)

    remaining = verify_and_consume_recovery_code(hashed, codes[0])
    assert remaining is not None
    assert len(remaining) == 2

    again = verify_and_consume_recovery_code(remaining, codes[0])
    assert again is None


def test_unknown_recovery_code_rejected():
    codes = generate_recovery_codes(count=3)
    hashed = hash_recovery_codes(codes)
    assert verify_and_consume_recovery_code(hashed, "0000-000000") is None
