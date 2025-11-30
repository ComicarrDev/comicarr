"""Security settings management (authentication configuration)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import structlog
from pydantic import BaseModel, Field

from comicarr.core.config import get_settings

logger = structlog.get_logger("comicarr.security")


class SecurityConfig(BaseModel):
    """Security configuration stored in security.json.

    This file contains authentication settings including auth method,
    username, and password hash (bcrypt).
    """

    auth_method: Literal["none", "forms"] = Field(
        default="none",
        description="Authentication method: 'none' for no auth, 'forms' for form-based login",
    )

    username: str | None = Field(
        default=None,
        description="Username for authentication (required if auth_method is 'forms')",
    )

    password_hash: str | None = Field(
        default=None,
        description="Bcrypt password hash (required if auth_method is 'forms')",
    )

    api_key: str | None = Field(
        default=None,
        description="API key for external applications to authenticate with Comicarr's API",
    )

    @property
    def security_file(self) -> Path:
        """Path to security.json file."""
        settings = get_settings()
        return settings.config_dir / "security.json"

    @classmethod
    def load(cls) -> SecurityConfig | None:
        """Load security configuration from file.

        Returns:
            SecurityConfig instance if file exists, None otherwise
        """
        settings = get_settings()
        security_file = settings.config_dir / "security.json"

        if not security_file.exists():
            logger.debug("Security config file does not exist", path=str(security_file))
            return None

        try:
            with security_file.open("r") as f:
                data = json.load(f)
            config = cls(**data)
            logger.debug("Security config loaded", auth_method=config.auth_method)
            return config
        except Exception as e:
            logger.error(
                "Failed to load security config",
                path=str(security_file),
                error=str(e),
                exc_info=True,
            )
            return None

    def save(self) -> None:
        """Save security configuration to file."""
        security_file = self.security_file

        try:
            # Ensure config directory exists
            security_file.parent.mkdir(parents=True, exist_ok=True)

            with security_file.open("w") as f:
                json.dump(self.model_dump(), f, indent=2)

            logger.info(
                "Security config saved",
                path=str(security_file),
                auth_method=self.auth_method,
            )
        except Exception as e:
            logger.error(
                "Failed to save security config",
                path=str(security_file),
                error=str(e),
                exc_info=True,
            )
            raise

    def exists(self) -> bool:
        """Check if security configuration file exists."""
        return self.security_file.exists()

    def is_configured(self) -> bool:
        """Check if security is configured (file exists and has valid settings).

        Returns:
            True if auth_method is 'forms' and username/password_hash are set,
            or if auth_method is 'none'
        """
        if self.auth_method == "none":
            return True

        if self.auth_method == "forms":
            return self.username is not None and self.password_hash is not None

        return False
