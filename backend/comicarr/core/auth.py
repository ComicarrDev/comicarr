"""Authentication utilities (password hashing, verification)."""

from __future__ import annotations

import bcrypt
import structlog

logger = structlog.get_logger("comicarr.auth")

# Bcrypt rounds (12 is a good balance between security and performance)
BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Bcrypt hash string
    """
    # Generate salt and hash password
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    password_hash = bcrypt.hashpw(password.encode("utf-8"), salt)
    return password_hash.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash.

    Args:
        password: Plain text password to verify
        password_hash: Bcrypt hash to verify against

    Returns:
        True if password matches hash, False otherwise
    """
    try:
        # bcrypt.checkpw returns True if password matches hash
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except Exception as e:
        logger.warning(
            "Password verification failed",
            error=str(e),
            exc_info=True,
        )
        return False
