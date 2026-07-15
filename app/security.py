"""Password hashing and signed-session helpers."""

from __future__ import annotations

import hashlib
import hmac
import os

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long")
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, expected_hex = encoded.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


class SessionSigner:
    def __init__(self, secret_key: str) -> None:
        self.serializer = URLSafeTimedSerializer(secret_key, salt="finance-tracker-session")

    def create(self, user_id: int) -> str:
        return self.serializer.dumps({"user_id": user_id})

    def read(self, token: str, max_age: int = 604_800) -> int | None:
        try:
            payload = self.serializer.loads(token, max_age=max_age)
            return int(payload["user_id"])
        except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError):
            return None
