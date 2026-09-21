from app.auth.security import (
    hash_password,
    is_valid_email,
    is_valid_password,
    is_valid_username,
    verify_password,
)


def test_hash_password_is_not_plaintext():
    hashed = hash_password("Sup3rSecret")
    assert hashed != "Sup3rSecret"
    assert hashed.startswith("pbkdf2_sha256$")


def test_verify_password_correct_and_incorrect():
    hashed = hash_password("Sup3rSecret")
    assert verify_password("Sup3rSecret", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_two_hashes_of_same_password_differ_due_to_salt():
    assert hash_password("Sup3rSecret") != hash_password("Sup3rSecret")


def test_email_validation():
    assert is_valid_email("student@example.com") is True
    assert is_valid_email("not-an-email") is False


def test_username_validation():
    assert is_valid_username("valid_user.1") is True
    assert is_valid_username("ab") is False  # too short
    assert is_valid_username("has a space") is False


def test_password_policy():
    ok, _ = is_valid_password("Strong1Pass")
    assert ok is True
    ok, reason = is_valid_password("short")
    assert ok is False and "8 characters" in reason
    ok, reason = is_valid_password("alllowercase1")
    assert ok is False and "uppercase" in reason
