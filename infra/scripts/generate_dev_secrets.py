"""Generate a local-development JWT RSA keypair and random secret keys.

Writes an RSA keypair to infra/keys/ (gitignored) and prints .env lines for
JWT_PRIVATE_KEY_PATH, JWT_PUBLIC_KEY_PATH, ENCRYPTION_MASTER_KEY and
BLIND_INDEX_KEY. Never run this against a production environment; production
keys must come from a secret manager, not a generated file checked into a
developer's working directory.

Usage: uv run python infra/scripts/generate_dev_secrets.py
"""

from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[2]
KEYS_DIR = ROOT / "infra" / "keys"


def generate_jwt_keypair() -> tuple[Path, Path]:
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    private_path = KEYS_DIR / "jwt_private.pem"
    public_path = KEYS_DIR / "jwt_public.pem"

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_path.write_bytes(private_bytes)
    public_path.write_bytes(public_bytes)
    return private_path, public_path


def main() -> None:
    private_path, public_path = generate_jwt_keypair()
    encryption_master_key = base64.b64encode(secrets.token_bytes(32)).decode()
    blind_index_key = base64.b64encode(secrets.token_bytes(32)).decode()

    print(f"Wrote {private_path} and {public_path}")
    print()
    print("Add these to your .env:")
    print(f"JWT_PRIVATE_KEY_PATH={os.path.relpath(private_path, ROOT)}")
    print(f"JWT_PUBLIC_KEY_PATH={os.path.relpath(public_path, ROOT)}")
    print(f"ENCRYPTION_MASTER_KEY={encryption_master_key}")
    print(f"BLIND_INDEX_KEY={blind_index_key}")


if __name__ == "__main__":
    main()
