"""Business logic for registration and login, separated from the routes
that expose it over HTTP so it can be unit-tested directly."""
from __future__ import annotations

from dataclasses import dataclass

from app.auth.security import (
    hash_password,
    is_valid_email,
    is_valid_password,
    is_valid_username,
    verify_password,
)
from app.database import repositories as repo


class AuthError(Exception):
    """Raised for any user-facing authentication/registration failure."""


@dataclass
class RegisteredUser:
    id: int
    email: str
    username: str


def register_user(email: str, username: str, password: str, confirm_password: str) -> RegisteredUser:
    email = (email or "").strip()
    username = (username or "").strip()

    if not email or not username or not password:
        raise AuthError("All fields are required.")
    if not is_valid_email(email):
        raise AuthError("Please enter a valid email address.")
    if not is_valid_username(username):
        raise AuthError("Username must be 3-32 characters (letters, numbers, . _ -).")
    if password != confirm_password:
        raise AuthError("Passwords do not match.")
    ok, reason = is_valid_password(password)
    if not ok:
        raise AuthError(reason)
    if repo.get_user_by_email(email):
        raise AuthError("An account with that email already exists.")
    if repo.get_user_by_username(username):
        raise AuthError("That username is already taken.")

    user = repo.create_user(email=email, username=username, password_hash=hash_password(password))
    return RegisteredUser(user.id, user.email, user.username)


def authenticate_user(identifier: str, password: str) -> RegisteredUser:
    identifier = (identifier or "").strip()
    if not identifier or not password:
        raise AuthError("Please enter your email/username and password.")

    user = repo.get_user_by_email(identifier) or repo.get_user_by_username(identifier)
    if not user or not verify_password(password, user.password_hash):
        # Same error for "no such user" and "wrong password" to avoid
        # leaking which accounts exist.
        raise AuthError("Invalid credentials. Please try again.")

    return RegisteredUser(user.id, user.email, user.username)
