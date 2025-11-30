"""Tests for authentication utilities."""

from __future__ import annotations

from comicarr.core.auth import hash_password, verify_password


def test_hash_password():
    """Test password hashing."""
    password = "test_password_123"
    hash1 = hash_password(password)
    hash2 = hash_password(password)

    # Each hash should be different (due to salt)
    assert hash1 != hash2

    # Both should be valid bcrypt hashes
    assert hash1.startswith("$2b$")
    assert hash2.startswith("$2b$")

    # Both should verify against the original password
    assert verify_password(password, hash1)
    assert verify_password(password, hash2)


def test_verify_password_correct():
    """Test password verification with correct password."""
    password = "correct_password"
    password_hash = hash_password(password)

    assert verify_password(password, password_hash) is True


def test_verify_password_incorrect():
    """Test password verification with incorrect password."""
    password = "correct_password"
    wrong_password = "wrong_password"
    password_hash = hash_password(password)

    assert verify_password(wrong_password, password_hash) is False


def test_verify_password_empty():
    """Test password verification with empty password."""
    password = "test_password"
    password_hash = hash_password(password)

    assert verify_password("", password_hash) is False


def test_hash_password_different_passwords():
    """Test that different passwords produce different hashes."""
    password1 = "password1"
    password2 = "password2"

    hash1 = hash_password(password1)
    hash2 = hash_password(password2)

    assert hash1 != hash2

    # Each should only verify against its own password
    assert verify_password(password1, hash1) is True
    assert verify_password(password2, hash2) is True
    assert verify_password(password1, hash2) is False
    assert verify_password(password2, hash1) is False
