"""Password hashing (Argon2id) and policy enforcement.

See PROJECT_PLAN.md Phase 4.1: Argon2id with 64 MB memory cost and time cost
3, a 12 character minimum, and rejection of passwords on a bundled common
password list.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

MIN_PASSWORD_LENGTH = 12
ARGON2_MEMORY_COST_KIB = 64 * 1024  # 64 MB
ARGON2_TIME_COST = 3
ARGON2_PARALLELISM = 4

_COMMON_PASSWORDS_PATH = Path(__file__).parent / "common_passwords.txt"

_hasher = PasswordHasher(
    memory_cost=ARGON2_MEMORY_COST_KIB,
    time_cost=ARGON2_TIME_COST,
    parallelism=ARGON2_PARALLELISM,
)


class PasswordPolicyError(ValueError):
    pass


@lru_cache(maxsize=1)
def _common_passwords() -> frozenset[str]:
    text = _COMMON_PASSWORDS_PATH.read_text(encoding="utf-8")
    return frozenset(line.strip().casefold() for line in text.splitlines() if line.strip())


def validate_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if password.casefold() in _common_passwords():
        raise PasswordPolicyError("Password is too common; choose a less predictable password")


def hash_password(password: str) -> str:
    validate_password_policy(password)
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
