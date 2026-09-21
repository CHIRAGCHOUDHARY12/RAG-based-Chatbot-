"""
Password hashing and session-token helpers.

We deliberately use only Python's standard library (hashlib.pbkdf2_hmac)
rather than bcrypt/passlib. PBKDF2-HMAC-SHA256 with a per-user random salt
and a high iteration count is a NIST-recommended, well-vetted construction,
and keeping this dependency-free avoids platform-specific wheel issues for
a project meant to "just run" locally.

Stored format: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 260_000
_SALT_BYTES = 16

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iterations_s, salt_hex, digest_hex = stored_hash.split("$")
    except ValueError:
        return False
    if algo != _ALGO:
        return False
    iterations = int(iterations_s)
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email.strip())) and len(email) <= 254


def is_valid_username(username: str) -> bool:
    return bool(_USERNAME_RE.match(username.strip()))


def is_valid_password(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if password.lower() == password or password.upper() == password:
        return False, "Password must mix uppercase and lowercase letters."
    if not any(c.isdigit() for c in password):
        return False, "Password must include at least one number."
    return True, ""


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)
