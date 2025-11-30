"""Application configuration using Pydantic Settings."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def json_config_settings_source(
    settings: BaseSettings | None = None,
) -> dict[str, Any]:  # noqa: ANN001
    """Load settings from settings.json file.

    This source has lowest priority - env vars will override JSON values.

    Args:
        settings: The Settings class (not instance) being constructed.
                  Can be used to determine data_dir if available.

    Returns:
        Dictionary with setting keys (lowercase) and values from JSON file.
        Uses Any for values because JSON deserialization can produce any
        JSON-serializable type (str, int, float, bool, dict, list, None).
        This is an acceptable exception per our design doc: "external library
        interfaces where we have no control" (in this case, JSON format).
    """
    # Determine config directory
    # First check if COMICARR_DATA_DIR env var is set (for tests)
    data_dir_env = Path(os.environ.get("COMICARR_DATA_DIR", ""))
    if data_dir_env and data_dir_env.exists():
        data_dir = data_dir_env
    elif Path("/config").exists():
        # Container environment
        data_dir = Path("/config")
    else:
        # Development - always use backend/data regardless of CWD
        # __file__ is backend/comicarr/core/config.py, so go up to backend/ and add data
        data_dir = Path(__file__).parent.parent.parent / "data"

    config_dir = data_dir / "config"
    settings_file = config_dir / "settings.json"

    if not settings_file.exists():
        return {}

    try:
        with settings_file.open("r") as f:
            data = json.load(f)

        # Handle nested structure: {"host": {"bind_address": "...", "port": ..., "base_url": "..."}}
        # This is the preferred format for settings.json
        flattened = {}
        if isinstance(data.get("host"), dict):
            # Nested format - extract and flatten
            host_dict = data["host"]
            flattened["host_bind_address"] = host_dict.get("bind_address", "127.0.0.1")
            port_value = host_dict.get("port", 8000)
            # Debug: Log what we're reading
            import structlog

            logger = structlog.get_logger("comicarr.config")
            logger.debug(
                "Loading port from settings.json",
                port_from_json=port_value,
                port_type=type(port_value).__name__,
            )
            flattened["host_port"] = port_value
            flattened["host_base_url"] = host_dict.get("base_url", "")
        else:
            # Flat format (old or migrated) - migrate to nested if needed
            if "host_bind_address" in data or "host_port" in data or "host_base_url" in data:
                # Already in flat prefixed format - keep as is for now, will be saved as nested
                flattened["host_bind_address"] = data.get("host_bind_address", "127.0.0.1")
                flattened["host_port"] = data.get("host_port", 8000)
                flattened["host_base_url"] = data.get("host_base_url", "")
            # Handle very old format: {"host": "...", "port": ..., "base_url": "..."}
            elif "host" in data and isinstance(data.get("host"), str):
                flattened["host_bind_address"] = data.pop("host", "127.0.0.1")
                flattened["host_port"] = data.pop("port", 8000)
                flattened["host_base_url"] = data.pop("base_url", "")

        # Copy other settings (non-host)
        for key, value in data.items():
            if key not in (
                "host",
                "host_bind_address",
                "host_port",
                "host_base_url",
                "port",
                "base_url",
            ):
                flattened[key] = value

        # Convert keys to lowercase to match field names
        return {k.lower(): v for k, v in flattened.items()}
    except Exception:
        return {}


class Settings(BaseSettings):
    """Application settings.

    Settings are loaded from:
    1. JSON file (settings.json in config directory) - lowest priority
    2. .env file
    3. Environment variables - highest priority (override JSON/.env)

    All settings can be prefixed with COMICARR_ (e.g., COMICARR_ENV=production),
    or used directly (e.g., ENV=production).

    See: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="COMICARR_",
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Customize settings sources - JSON file first, then env vars.

        Priority (lowest to highest):
        1. JSON file (settings.json)
        2. .env file
        3. Environment variables
        4. Init settings (values passed to Settings()) - highest priority
        """
        # Priority: JSON (lowest) -> .env -> env vars -> init_settings (highest)
        # Note: json_config_settings_source is a callable that returns dict, which is compatible
        # with PydanticBaseSettingsSource at runtime, but the type checker needs help
        return (  # type: ignore[return-value]
            json_config_settings_source,
            dotenv_settings,
            env_settings,
            init_settings,  # Highest priority - allows validation and test overrides
        )

    # Application
    env: Literal["development", "production", "testing"] = Field(
        default="development",
        description="Application environment (development, production, testing)",
    )

    # Host settings
    host_bind_address: str = Field(
        default="127.0.0.1",
        description="Host address to bind the server to",
    )

    host_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Port number to bind the server to",
    )

    host_base_url: str = Field(
        default="",
        description="Base URL path for reverse proxy setups (e.g., /comicarr)",
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level",
    )

    # Application paths
    # For LinuxServer.io, /config is typically the mounted volume
    # We check if /config exists first (container environment), otherwise use ./data
    data_dir: Path = Field(
        default_factory=lambda: (
            Path("/config")
            if Path("/config").exists()
            else (
                # Always use backend/data regardless of where script is run from
                # __file__ is backend/comicarr/core/config.py, so go up to backend/ and add data
                Path(__file__).parent.parent.parent
                / "data"
            ).resolve()
        ),
        description="Base directory for all application data (config, database, cache, etc.)",
    )

    # Subdirectories under data_dir
    @property
    def config_dir(self) -> Path:
        """Directory for configuration files (settings.json, etc.)."""
        return self.data_dir / "config"

    @property
    def database_dir(self) -> Path:
        """Directory for database files."""
        return self.data_dir / "database"

    @property
    def cache_dir(self) -> Path:
        """Directory for cache files."""
        return self.data_dir / "cache"

    @property
    def library_dir(self) -> Path:
        """Directory for comic library files."""
        return self.data_dir / "library"

    @property
    def logs_dir(self) -> Path:
        """Directory for log files (if file logging is enabled)."""
        return self.data_dir / "logs"

    # Database
    @property
    def database_url(self) -> str:
        """Database connection URL.

        Constructs SQLite URL pointing to database directory.
        SQLite URLs use format: sqlite+aiosqlite:///path/to/db.db
        (3 slashes total after colon: :///)
        """
        db_file = self.database_dir / "comicarr.db"
        # Convert to POSIX path and ensure it's absolute
        db_path = db_file.resolve().as_posix()
        # SQLite URLs format: sqlite:///absolute/path
        # db_path already includes leading / for absolute paths
        # So we use :/// (3 slashes) not ://// (4 slashes)
        # Remove leading slash if present to avoid double slash
        if db_path.startswith("/"):
            db_path_no_leading = db_path[1:]
            return f"sqlite+aiosqlite:///{db_path_no_leading}"
        # Relative path (shouldn't happen after resolve(), but handle it)
        return f"sqlite+aiosqlite:///{db_path}"

    @property
    def is_debug(self) -> bool:
        """Check if running in debug/development mode."""
        return self.env == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.env == "production"

    @property
    def is_testing(self) -> bool:
        """Check if running in testing mode."""
        return self.env == "testing"

    def model_post_init(self, __context: object) -> None:
        """Post-initialization: create data directories if they don't exist."""
        # Use resolve() to ensure absolute paths
        self.data_dir = self.data_dir.resolve()

        # Create all subdirectories
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.database_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get the cached settings instance.

    Creates and caches the settings instance on first call.
    Subsequent calls return the cached instance.

    The cache is cleared when reload_settings() is called.

    Returns:
        Settings instance
    """
    return Settings()


def reload_settings() -> Settings:
    """Reload settings from all sources (JSON, .env, env vars).

    Clears the cache and creates a new Settings instance.
    Useful for testing or when settings change.

    Returns:
        New Settings instance
    """
    get_settings.cache_clear()
    return get_settings()
