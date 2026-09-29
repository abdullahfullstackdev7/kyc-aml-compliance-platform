"""TOTP MFA enrollment and verification, with hashed one-time recovery codes.

See PROJECT_PLAN.md Phase 4.1: mandatory TOTP for staff roles, QR enrollment,
10 one-time recovery codes (hashed, each usable once).
"""

from __future__ import annotations

import hashlib
import secrets

import pyotp

from backend.app.core.config import get_settings

RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_BYTES = 5  # -> 8 base32 characters, grouped for readability


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, *, account_email: str) -> str:
    settings = get_settings()
    return pyotp.TOTP(secret).provisioning_uri(name=account_email, issuer_name=settings.totp_issuer)


def verify_totp_code(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    codes = []
    for _ in range(count):
        raw = secrets.token_hex(RECOVERY_CODE_BYTES).upper()
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def hash_recovery_code(code: str) -> str:
    normalized = code.strip().upper().replace("-", "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def hash_recovery_codes(codes: list[str]) -> list[str]:
    return [hash_recovery_code(c) for c in codes]


def verify_and_consume_recovery_code(hashed_codes: list[str], code: str) -> list[str] | None:
    """Returns the updated hashed-code list with the matched code removed,
    or None if the code did not match any remaining code."""
    target = hash_recovery_code(code)
    if target not in hashed_codes:
        return None
    remaining = hashed_codes.copy()
    remaining.remove(target)
    return remaining
