import pytest

from app.auth.service import AuthError, authenticate_user, register_user


def test_register_user_success(temp_data_dir):
    user = register_user("student@example.com", "student1", "GoodPass1", "GoodPass1")
    assert user.email == "student@example.com"
    assert user.username == "student1"


def test_register_rejects_mismatched_passwords(temp_data_dir):
    with pytest.raises(AuthError, match="do not match"):
        register_user("a@example.com", "user1", "GoodPass1", "GoodPass2")


def test_register_rejects_duplicate_email(temp_data_dir):
    register_user("dup@example.com", "userone", "GoodPass1", "GoodPass1")
    with pytest.raises(AuthError, match="already exists"):
        register_user("dup@example.com", "usertwo", "GoodPass1", "GoodPass1")


def test_register_rejects_duplicate_username(temp_data_dir):
    register_user("first@example.com", "sameuser", "GoodPass1", "GoodPass1")
    with pytest.raises(AuthError, match="already taken"):
        register_user("second@example.com", "sameuser", "GoodPass1", "GoodPass1")


def test_login_success_with_email_or_username(temp_data_dir):
    register_user("login@example.com", "loginuser", "GoodPass1", "GoodPass1")
    assert authenticate_user("login@example.com", "GoodPass1").username == "loginuser"
    assert authenticate_user("loginuser", "GoodPass1").username == "loginuser"


def test_login_rejects_wrong_password(temp_data_dir):
    register_user("wrongpw@example.com", "wrongpwuser", "GoodPass1", "GoodPass1")
    with pytest.raises(AuthError, match="Invalid credentials"):
        authenticate_user("wrongpwuser", "SomethingElse1")


def test_login_rejects_unknown_user(temp_data_dir):
    with pytest.raises(AuthError, match="Invalid credentials"):
        authenticate_user("nobody@example.com", "whatever1A")
