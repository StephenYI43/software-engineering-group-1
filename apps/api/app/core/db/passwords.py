"""Versioned stdlib scrypt hashes; reject unbounded parameters from stored data."""

import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=1, maxmem=67108864
    ).hex()
    return f"scrypt$32768$8$1${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if (algorithm, n, r, p) != ("scrypt", "32768", "8", "1"):
            return False
        if len(salt) != 32 or len(expected) != 128:
            return False
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=1, maxmem=67108864
        ).hex()
        return hmac.compare_digest(digest, expected)
    except ValueError:
        return False
