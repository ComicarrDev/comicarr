"""FastAPI dependencies for authentication and authorization."""

from __future__ import annotations

import structlog
from fastapi import HTTPException, Request, status

from comicarr.core.security import SecurityConfig

logger = structlog.get_logger("comicarr.dependencies")


def get_security_config() -> SecurityConfig | None:
    """Get current security configuration.

    Returns:
        SecurityConfig instance if exists, None otherwise
    """
    return SecurityConfig.load()


def require_auth(request: Request) -> bool:
    """Dependency to require authentication for a route.

    Raises HTTPException if user is not authenticated.
    Works for both 'none' and 'forms' auth methods.

    Args:
        request: FastAPI request object

    Returns:
        True if authenticated (always returns True, raises exception otherwise)

    Raises:
        HTTPException: If authentication is required but user is not authenticated
    """
    security_config = SecurityConfig.load()

    # If no security config or auth_method is 'none', always allow
    if security_config is None or security_config.auth_method == "none":
        return True

    # For 'forms' auth, check session
    if security_config.auth_method == "forms":
        authenticated = request.session.get("authenticated", False)
        if not authenticated:
            logger.warning(
                "Unauthenticated access attempt",
                path=request.url.path,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        return True

    # Unknown auth method
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Authentication method '{security_config.auth_method if security_config else 'unknown'}' not implemented",
    )
