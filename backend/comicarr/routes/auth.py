"""Authentication routes (login, logout, session, setup)."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from comicarr.core.auth import hash_password, verify_password
from comicarr.core.config import get_settings
from comicarr.core.metrics import auth_login_failures_total
from comicarr.core.security import SecurityConfig

logger = structlog.get_logger("comicarr.auth.routes")
router = APIRouter(prefix="/api/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    """Login request model."""

    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class LoginResponse(BaseModel):
    """Login response model."""

    success: bool = Field(..., description="Whether login was successful")
    message: str = Field(..., description="Response message")


class SessionResponse(BaseModel):
    """Session status response model."""

    authenticated: bool = Field(..., description="Whether user is authenticated")
    auth_method: str = Field(..., description="Current authentication method")
    setup_required: bool = Field(..., description="Whether initial setup is required")
    username: str | None = Field(None, description="Current username if authenticated")


class SetupRequest(BaseModel):
    """Initial setup request model."""

    username: str = Field(..., min_length=1, description="Username for authentication")
    password: str = Field(..., min_length=1, description="Password for authentication")


class SetupResponse(BaseModel):
    """Setup response model."""

    success: bool = Field(..., description="Whether setup was successful")
    message: str = Field(..., description="Response message")


def _is_authenticated(request: Request) -> bool:
    """Check if user is authenticated via session.

    Args:
        request: FastAPI request object

    Returns:
        True if authenticated, False otherwise
    """
    return request.session.get("authenticated", False) is True


def _get_session_username(request: Request) -> str | None:
    """Get username from session.

    Args:
        request: FastAPI request object

    Returns:
        Username if authenticated, None otherwise
    """
    if _is_authenticated(request):
        return request.session.get("username")
    return None


@router.post("/login", response_model=LoginResponse)
async def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
) -> LoginResponse:
    """Login endpoint.

    Authenticates user and creates a session.
    Only works if auth_method is 'forms'.
    """
    settings = get_settings()
    security_config = SecurityConfig.load()

    # Check if authentication is enabled
    if security_config is None:
        auth_login_failures_total.labels(reason="not_configured").inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication not configured. Please run initial setup.",
        )

    if security_config.auth_method == "none":
        # No authentication required
        request.session["authenticated"] = True
        request.session["username"] = None
        return LoginResponse(
            success=True,
            message="Authentication disabled",
        )

    if security_config.auth_method != "forms":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Authentication method '{security_config.auth_method}' not implemented",
        )

    # Verify credentials
    if security_config.username is None or security_config.password_hash is None:
        auth_login_failures_total.labels(reason="not_properly_configured").inc()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication not properly configured",
        )

    # Check username
    if credentials.username != security_config.username:
        auth_login_failures_total.labels(reason="invalid_username").inc()
        logger.warning(
            "Login failed: invalid username",
            username=credentials.username,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Verify password
    if not verify_password(credentials.password, security_config.password_hash):
        auth_login_failures_total.labels(reason="invalid_password").inc()
        logger.warning(
            "Login failed: invalid password",
            username=credentials.username,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Create session
    request.session["authenticated"] = True
    request.session["username"] = credentials.username

    logger.info("User logged in", username=credentials.username)

    return LoginResponse(
        success=True,
        message="Login successful",
    )


@router.post("/logout", response_model=LoginResponse)
async def logout(request: Request) -> LoginResponse:
    """Logout endpoint.

    Destroys the current session.
    """
    username = _get_session_username(request)

    # Clear session
    request.session.clear()

    logger.info("User logged out", username=username)

    return LoginResponse(
        success=True,
        message="Logout successful",
    )


@router.get("/session", response_model=SessionResponse)
async def get_session(request: Request) -> SessionResponse:
    """Get current session status.

    Returns authentication status and current auth method.
    """
    settings = get_settings()
    security_config = SecurityConfig.load()

    # Check if setup is required
    if security_config is None or not security_config.is_configured():
        return SessionResponse(
            authenticated=False,
            auth_method="none",
            setup_required=True,
            username=None,
        )

    authenticated = _is_authenticated(request)
    username = None

    # If auth_method is 'none', user is always authenticated
    if security_config.auth_method == "none":
        authenticated = True
    elif authenticated:
        # Get username from session if authenticated
        username = _get_session_username(request)

    return SessionResponse(
        authenticated=authenticated,
        auth_method=security_config.auth_method,
        setup_required=False,
        username=username,
    )


@router.post("/setup", response_model=SetupResponse)
async def setup(credentials: SetupRequest) -> SetupResponse:
    """Initial setup endpoint.

    Creates initial security configuration.
    Only works if no security.json exists yet.
    """
    settings = get_settings()

    # Check if security config already exists
    existing_config = SecurityConfig.load()
    if existing_config is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Security configuration already exists. Cannot run setup again.",
        )

    # Create new security config
    password_hash = hash_password(credentials.password)
    security_config = SecurityConfig(
        auth_method="forms",
        username=credentials.username,
        password_hash=password_hash,
    )

    # Save to file
    try:
        security_config.save()
        logger.info("Initial setup completed", username=credentials.username)
        return SetupResponse(
            success=True,
            message="Setup completed successfully",
        )
    except Exception as e:
        logger.error(
            "Setup failed",
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save security configuration: {str(e)}",
        )
