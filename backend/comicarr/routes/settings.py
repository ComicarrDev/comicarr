"""Settings API routes."""

from __future__ import annotations

import json
from typing import Any, Literal

import httpx
import structlog
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from comicarr.core.auth import hash_password
from comicarr.core.config import get_settings
from comicarr.core.security import SecurityConfig
from comicarr.core.settings_persistence import (
    get_effective_settings,
    get_settings_file_path,
    save_settings_to_file,
)
from comicarr.core.tracing import get_trace_id

router = APIRouter(prefix="/api")
logger = structlog.get_logger("comicarr.routes.settings")
settings = get_settings()


class SettingsUpdate(BaseModel):
    """Settings update model."""

    env: Literal["development", "production", "testing"] | None = Field(
        default=None,
        description="Application environment",
    )
    host: str | None = Field(
        default=None,
        description="Host address to bind the server to",
    )
    port: int | None = Field(
        default=None,
        ge=1,
        le=65535,
        description="Port number to bind the server to",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | None = Field(
        default=None,
        description="Logging level",
    )


@router.get("/settings")
async def get_settings_endpoint() -> JSONResponse:
    """Get application settings.

    Returns current application settings. Sensitive values (like passwords)
    are excluded.
    """
    trace_id = get_trace_id()
    logger.debug("Settings endpoint accessed", trace_id=trace_id)

    effective_settings = get_effective_settings()
    effective_settings["trace_id"] = trace_id

    return JSONResponse(effective_settings)


@router.put("/settings")
async def update_settings(update: SettingsUpdate) -> JSONResponse:
    """Update application settings.

    Updates are saved to settings.json file in the config directory.
    Note: Some settings (like host and port) require a restart to take effect.
    """
    trace_id = get_trace_id()
    logger.debug("Settings update requested", trace_id=trace_id)

    # Get current effective settings
    current = get_effective_settings()

    # Build update dict (only include fields that were provided)
    update_dict: dict[str, Any] = {}
    if update.env is not None:
        update_dict["env"] = update.env
    if update.host is not None:
        update_dict["host"] = update.host
    if update.port is not None:
        update_dict["port"] = update.port
    if update.log_level is not None:
        update_dict["log_level"] = update.log_level

    if not update_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No settings provided to update",
        )

    # Validate host if provided
    if update.host is not None and not update.host.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Host cannot be empty",
        )

    try:
        # Save to file
        save_settings_to_file(update_dict)

        # Return updated effective settings
        updated = get_effective_settings()
        updated["trace_id"] = trace_id

        logger.info(
            "Settings updated",
            trace_id=trace_id,
            updated_fields=list(update_dict.keys()),
        )

        return JSONResponse(updated)
    except Exception as e:
        logger.error(
            "Failed to update settings",
            trace_id=trace_id,
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update settings: {str(e)}",
        )


# Helper functions for loading/saving nested settings
def _load_settings_data() -> dict[str, Any]:
    """Load all settings from settings.json file.

    Supports both nested format (preferred) and flat format (for migration).
    Returns data in the format it was stored (nested or flat).
    """
    settings_file = get_settings_file_path()
    if not settings_file.exists():
        return {}
    try:
        with settings_file.open("r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_settings_data(data: dict[str, Any]) -> None:
    """Save all settings to settings.json file.

    Converts flat prefixed format (host_bind_address, etc.) to nested format
    (host: {bind_address, port, base_url}) for better organization.
    """
    settings_file = get_settings_file_path()
    settings_file.parent.mkdir(parents=True, exist_ok=True)

    # Convert to nested structure for better organization
    nested_data: dict[str, Any] = {}

    # Extract host settings into nested structure
    if "host_bind_address" in data or "host_port" in data or "host_base_url" in data:
        nested_data["host"] = {
            "bind_address": data.pop("host_bind_address", "127.0.0.1"),
            "port": data.pop("host_port", 8000),
            "base_url": data.pop("host_base_url", ""),
        }
    # If already in nested format, keep it
    elif "host" in data and isinstance(data.get("host"), dict):
        nested_data["host"] = data.pop("host")

    # Copy all other settings
    for key, value in data.items():
        if key not in ("host_bind_address", "host_port", "host_base_url"):
            nested_data[key] = value

    with settings_file.open("w") as f:
        json.dump(nested_data, f, indent=2)

    # Reload settings
    from comicarr.core.config import reload_settings

    reload_settings()


# Host Settings Endpoints
@router.get("/settings/host")
async def get_host_settings() -> JSONResponse:
    """Get host settings (bind_address, port, base_url)."""
    trace_id = get_trace_id()
    logger.debug("Host settings endpoint accessed", trace_id=trace_id)

    settings = get_settings()
    settings_data = _load_settings_data()

    # Get host settings from settings.json (supports both nested and flat format)
    if "host" in settings_data and isinstance(settings_data.get("host"), dict):
        # Nested format
        host = settings_data["host"]
        bind_address = host.get("bind_address", settings.host_bind_address)
        port = host.get("port", settings.host_port)
        base_url = host.get("base_url", settings.host_base_url)
    else:
        # Flat format (for migration)
        bind_address = settings_data.get("host_bind_address", settings.host_bind_address)
        port = settings_data.get("host_port", settings.host_port)
        base_url = settings_data.get("host_base_url", settings.host_base_url)

    return JSONResponse(
        {
            "bind_address": bind_address,
            "port": port,
            "base_url": base_url,
        }
    )


@router.get("/settings/weekly-releases")
async def get_weekly_releases_settings() -> JSONResponse:
    """Get weekly releases settings."""
    effective_settings = get_effective_settings()
    weekly_releases = effective_settings.get(
        "weekly_releases",
        {
            "auto_fetch_enabled": False,
            "auto_fetch_interval_hours": 12,
            "sources": {
                "previewsworld": {"enabled": True},
                "comicgeeks": {"enabled": True},
                "readcomicsonline": {"enabled": True},
            },
        },
    )
    return JSONResponse(weekly_releases)


@router.put("/settings/weekly-releases")
async def update_weekly_releases_settings(
    payload: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Update weekly releases settings."""
    trace_id = get_trace_id()
    logger.debug("Weekly releases settings update requested", trace_id=trace_id)

    # Validate payload
    auto_fetch_enabled = payload.get("auto_fetch_enabled", False)
    auto_fetch_interval_hours = payload.get("auto_fetch_interval_hours", 12)
    sources = payload.get("sources", {})

    # Validate interval
    if not isinstance(auto_fetch_interval_hours, int) or auto_fetch_interval_hours < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="auto_fetch_interval_hours must be a positive integer",
        )

    # Validate sources
    valid_sources = ["previewsworld", "comicgeeks", "readcomicsonline"]
    for source_name, source_config in sources.items():
        if source_name not in valid_sources:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid source: {source_name}. Valid sources: {', '.join(valid_sources)}",
            )
        if not isinstance(source_config, dict) or "enabled" not in source_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Source {source_name} must have 'enabled' boolean field",
            )

    # Save to settings.json
    settings_data = _load_settings_data()
    settings_data["weekly_releases"] = {
        "auto_fetch_enabled": auto_fetch_enabled,
        "auto_fetch_interval_hours": auto_fetch_interval_hours,
        "sources": sources,
    }
    _save_settings_data(settings_data)

    logger.info(
        "Weekly releases settings updated",
        trace_id=trace_id,
        auto_fetch_enabled=auto_fetch_enabled,
        interval_hours=auto_fetch_interval_hours,
    )

    return JSONResponse(
        {
            "success": True,
            "message": "Settings saved. Scheduler will be updated on next restart.",
        }
    )


@router.put("/settings/host")
async def update_host_settings(
    payload: dict[str, Any] = Body(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> JSONResponse:
    """Update host settings (bind_address, port, base_url)."""
    trace_id = get_trace_id()
    logger.debug("Host settings update requested", trace_id=trace_id)

    # Validate bind_address
    bind_address = str(payload.get("bind_address", "")).strip() or "127.0.0.1"

    # Validate port
    try:
        port = int(payload.get("port", 8000))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Port must be an integer.",
        )
    if port < 1 or port > 65535:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Port must be between 1 and 65535.",
        )

    # Validate base_url
    base_url = str(payload.get("base_url", "")).strip()
    if base_url and not base_url.startswith("/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Base URL must start with '/'.",
        )
    if base_url != "/" and base_url.endswith("/"):
        base_url = base_url.rstrip("/")
    if base_url == "/":
        base_url = ""

    # Save to settings.json (will be saved in nested format)
    settings_data = _load_settings_data()
    # Store in flat format temporarily - _save_settings_data will convert to nested
    # Remove any existing nested host structure first
    if "host" in settings_data and isinstance(settings_data.get("host"), dict):
        del settings_data["host"]
    settings_data["host_bind_address"] = bind_address
    settings_data["host_port"] = port
    settings_data["host_base_url"] = base_url
    _save_settings_data(settings_data)

    logger.info(
        "Host settings updated",
        trace_id=trace_id,
        bind_address=bind_address,
        port=port,
        base_url=base_url,
    )

    # Check if host or port changed - these require restart
    current_settings = get_settings()
    host_changed = bind_address != current_settings.host_bind_address
    port_changed = port != current_settings.host_port
    base_url_changed = base_url != current_settings.host_base_url

    restart_required = host_changed or port_changed or base_url_changed

    if restart_required:
        if settings.is_debug:
            # Development: manual restart required
            message = (
                "Settings saved. Please restart the server manually to apply changes "
                "(e.g., stop with Ctrl+C and run 'make dev-back' again)."
            )
        else:
            # Production: trigger restart via SIGTERM (process manager will handle it)
            import os
            import signal

            def _trigger_restart() -> None:
                """Trigger server restart by sending SIGTERM to current process."""
                logger.info("Triggering server restart to apply host settings", trace_id=trace_id)
                os.kill(os.getpid(), signal.SIGTERM)

            background_tasks.add_task(_trigger_restart)
            message = "Settings saved. Server will restart to apply changes."
    else:
        message = "Settings saved."

    return JSONResponse(
        {
            "bind_address": bind_address,
            "port": port,
            "base_url": base_url,
            "restart_required": restart_required,
            "message": message,
        }
    )


# Security Settings Endpoints
@router.get("/settings/security")
async def get_security_settings() -> JSONResponse:
    """Get security settings (auth_method, username, has_password)."""
    trace_id = get_trace_id()
    logger.debug("Security settings endpoint accessed", trace_id=trace_id)

    security_config = SecurityConfig.load()
    if security_config is None:
        return JSONResponse(
            {
                "auth_method": "none",
                "username": None,
                "has_password": False,
                "api_key": None,
                "has_api_key": False,
            }
        )

    return JSONResponse(
        {
            "auth_method": security_config.auth_method,
            "username": security_config.username,
            "has_password": security_config.password_hash is not None,
            "api_key": security_config.api_key,
            "has_api_key": security_config.api_key is not None,
        }
    )


@router.put("/settings/security")
async def update_security_settings(
    payload: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Update security settings (auth_method, username, password)."""
    trace_id = get_trace_id()
    logger.debug("Security settings update requested", trace_id=trace_id)

    # Get current security config
    current_config = SecurityConfig.load()

    # Validate auth_method
    auth_method = str(
        payload.get("auth_method", current_config.auth_method if current_config else "none")
    ).lower()
    if auth_method not in {"none", "forms"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported authentication method.",
        )

    # Get username
    username = (
        str(payload.get("username", current_config.username if current_config else "admin")).strip()
        or "admin"
    )

    # Handle password
    password = payload.get("password")
    new_password_hash = current_config.password_hash if current_config else None

    if password:
        if not isinstance(password, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be a string.",
            )
        new_password_hash = hash_password(password)

    # Validate: if enabling forms auth, must have password
    if auth_method == "forms" and not new_password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A password must be set before enabling Forms authentication.",
        )

    # Handle API key
    api_key = payload.get("api_key")
    new_api_key = current_config.api_key if current_config else None

    if api_key is not None:
        if not isinstance(api_key, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API key must be a string.",
            )
        api_key = api_key.strip()
        # Allow empty string to clear the API key
        new_api_key = api_key if api_key else None

    # Create/update security config
    security_config = SecurityConfig(
        auth_method=auth_method,
        username=username if auth_method == "forms" else None,
        password_hash=new_password_hash if auth_method == "forms" else None,
        api_key=new_api_key,
    )

    # Save to file
    security_config.save()

    logger.info(
        "Security settings updated",
        trace_id=trace_id,
        auth_method=auth_method,
        username=username if auth_method == "forms" else None,
    )

    return JSONResponse(
        {
            "auth_method": security_config.auth_method,
            "username": security_config.username,
            "has_password": security_config.password_hash is not None,
            "api_key": security_config.api_key,
            "has_api_key": security_config.api_key is not None,
        }
    )


# External APIs Settings Endpoints
DEFAULT_EXTERNAL_APIS = {
    "comicvine": {
        "api_key": None,
        "base_url": "https://comicvine.gamespot.com/api",
        "enabled": False,
        "rate_limit": 40,  # requests per period
        "rate_limit_period": 60,  # seconds
        "max_retries": 3,  # retry attempts on rate limit errors
        "cache_enabled": True,  # enable response caching
        "burst_prevention_enabled": True,  # enable burst prevention during slow start
        "min_gap_seconds": None,  # minimum gap between requests during burst prevention (None = auto-calculate)
    }
}


def _get_external_apis() -> dict[str, Any]:
    """Get external APIs settings from settings.json or defaults."""
    settings_data = _load_settings_data()
    external_apis = settings_data.get("external_apis", DEFAULT_EXTERNAL_APIS.copy())

    # Ensure comicvine exists with defaults
    if "comicvine" not in external_apis:
        external_apis["comicvine"] = DEFAULT_EXTERNAL_APIS["comicvine"].copy()
    else:
        # Merge with defaults to ensure all fields exist
        comicvine = external_apis["comicvine"]
        default_comicvine = DEFAULT_EXTERNAL_APIS["comicvine"]
        external_apis["comicvine"] = {
            "api_key": comicvine.get("api_key", default_comicvine["api_key"]),
            "base_url": comicvine.get("base_url", default_comicvine["base_url"]),
            "enabled": comicvine.get("enabled", default_comicvine["enabled"]),
            "rate_limit": comicvine.get("rate_limit", default_comicvine["rate_limit"]),
            "rate_limit_period": comicvine.get(
                "rate_limit_period", default_comicvine["rate_limit_period"]
            ),
            "max_retries": comicvine.get("max_retries", default_comicvine["max_retries"]),
            "cache_enabled": comicvine.get("cache_enabled", default_comicvine["cache_enabled"]),
            "burst_prevention_enabled": comicvine.get(
                "burst_prevention_enabled", default_comicvine["burst_prevention_enabled"]
            ),
            "min_gap_seconds": comicvine.get(
                "min_gap_seconds", default_comicvine["min_gap_seconds"]
            ),
        }

    return external_apis


@router.get("/settings/external-apis")
async def get_external_apis() -> JSONResponse:
    """Get external APIs settings."""
    trace_id = get_trace_id()
    logger.debug("External APIs settings endpoint accessed", trace_id=trace_id)

    external_apis = _get_external_apis()

    return JSONResponse(
        {
            "comicvine": external_apis["comicvine"],
        }
    )


@router.put("/settings/external-apis")
async def update_external_apis(
    payload: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Update external APIs settings."""
    trace_id = get_trace_id()
    logger.debug("External APIs settings update requested", trace_id=trace_id)

    comicvine_payload = payload.get("comicvine", {})

    # Normalize comicvine settings
    default_comicvine = DEFAULT_EXTERNAL_APIS["comicvine"]

    # Handle min_gap_seconds: can be None (auto-calculate) or a positive number
    min_gap_seconds = comicvine_payload.get("min_gap_seconds")
    if min_gap_seconds is not None:
        try:
            min_gap_seconds = float(min_gap_seconds)
            if min_gap_seconds < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="min_gap_seconds must be non-negative or null (for auto-calculate)",
                )
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="min_gap_seconds must be a number or null",
            )

    comicvine = {
        "api_key": comicvine_payload.get("api_key") if comicvine_payload.get("api_key") else None,
        "base_url": str(comicvine_payload.get("base_url", default_comicvine["base_url"])).strip(),
        "enabled": bool(comicvine_payload.get("enabled", False)),
        "rate_limit": int(comicvine_payload.get("rate_limit", default_comicvine["rate_limit"])),
        "rate_limit_period": int(
            comicvine_payload.get("rate_limit_period", default_comicvine["rate_limit_period"])
        ),
        "max_retries": int(comicvine_payload.get("max_retries", default_comicvine["max_retries"])),
        "cache_enabled": bool(
            comicvine_payload.get("cache_enabled", default_comicvine["cache_enabled"])
        ),
        "burst_prevention_enabled": bool(
            comicvine_payload.get(
                "burst_prevention_enabled", default_comicvine["burst_prevention_enabled"]
            )
        ),
        "min_gap_seconds": min_gap_seconds,
    }

    # Save to settings.json
    settings_data = _load_settings_data()
    if "external_apis" not in settings_data:
        settings_data["external_apis"] = DEFAULT_EXTERNAL_APIS.copy()
    settings_data["external_apis"]["comicvine"] = comicvine
    _save_settings_data(settings_data)

    logger.info(
        "External APIs settings updated",
        trace_id=trace_id,
        comicvine_enabled=comicvine["enabled"],
    )

    return JSONResponse(
        {
            "comicvine": comicvine,
        }
    )


@router.post("/settings/external-apis/test")
async def test_external_apis(
    payload: dict[str, Any] | None = Body(None),
) -> JSONResponse:
    """Test external APIs connection (currently only Comicvine)."""
    trace_id = get_trace_id()
    logger.debug("External APIs test requested", trace_id=trace_id)

    # Get saved comicvine config from settings (as fallback)
    external_apis = _get_external_apis()
    saved_config = external_apis["comicvine"]

    # Use payload values if provided, otherwise fall back to saved settings
    # This allows testing new values before saving, but uses saved values if form fields are empty
    if payload and isinstance(payload, dict) and "comicvine" in payload:
        payload_config = payload["comicvine"]
        # Use payload values if they exist and are non-empty, otherwise use saved values
        payload_api_key = payload_config.get("api_key")
        payload_base_url = payload_config.get("base_url")

        comicvine_config = {
            "api_key": payload_api_key if payload_api_key else saved_config.get("api_key"),
            "base_url": payload_base_url if payload_base_url else saved_config.get("base_url"),
            "enabled": (
                payload_config.get("enabled")
                if "enabled" in payload_config
                else saved_config.get("enabled")
            ),
        }
    else:
        comicvine_config = saved_config

    # Normalize config
    api_key_raw = comicvine_config.get("api_key")
    api_key: str | None = None
    if api_key_raw and isinstance(api_key_raw, str):
        api_key = api_key_raw

    base_url_raw = comicvine_config.get("base_url", "https://comicvine.gamespot.com/api")
    base_url: str = (
        str(base_url_raw).strip()
        if base_url_raw and not isinstance(base_url_raw, bool)
        else "https://comicvine.gamespot.com/api"
    )

    enabled = bool(comicvine_config.get("enabled", False))

    normalized = {
        "api_key": api_key,
        "base_url": base_url,
        "enabled": enabled,
    }

    logger.debug(
        "Comicvine test config",
        trace_id=trace_id,
        enabled=normalized["enabled"],
        has_api_key=bool(normalized["api_key"]),
        api_key_length=(
            len(normalized["api_key"])
            if normalized["api_key"] and isinstance(normalized["api_key"], str)
            else 0
        ),
        base_url=normalized["base_url"],
    )

    # Test Comicvine connection
    if not normalized["enabled"]:
        status_message = "Comicvine integration is disabled."
        ok = False
    elif not normalized["api_key"]:
        status_message = "Comicvine API key is missing."
        ok = False
    else:
        try:
            # Make a simple test request to Comicvine API
            # Ensure base_url doesn't have trailing slash, then add endpoint
            base_url_val = normalized["base_url"]
            base_url_clean = (
                str(base_url_val).rstrip("/")
                if base_url_val and isinstance(base_url_val, str)
                else "https://comicvine.gamespot.com/api"
            )
            url = f"{base_url_clean}/issues/"

            # Build params - only include api_key if it exists
            params = {
                "format": "json",
                "limit": 1,
                "sort": "date_added:desc",
            }
            if normalized["api_key"]:
                params["api_key"] = normalized["api_key"]

            logger.debug(
                "Testing Comicvine connection",
                trace_id=trace_id,
                url=url,
                has_api_key=bool(normalized["api_key"]),
                api_key_preview=(
                    normalized["api_key"][:10] + "..."
                    if normalized["api_key"]
                    and isinstance(normalized["api_key"], str)
                    and len(normalized["api_key"]) > 10
                    else None
                ),
            )

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers={
                        "User-Agent": "Comicarr/0.1 (+https://github.com/agnlopes/comicarr)",
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()

                status_code = data.get("status_code")
                error_msg = data.get("error")

                logger.debug(
                    "Comicvine API response",
                    trace_id=trace_id,
                    status_code=status_code,
                    error=error_msg,
                    http_status=response.status_code,
                )

                if status_code == 1 and (error_msg in (None, "OK")):
                    ok = True
                    status_message = "Comicvine API connection successful."
                else:
                    ok = False
                    status_message = (
                        f"Comicvine API error: {error_msg or f'Status code {status_code}'}"
                    )
        except httpx.HTTPStatusError as e:
            ok = False
            error_detail = f"HTTP {e.response.status_code}"
            try:
                error_data = e.response.json()
                if isinstance(error_data, dict) and "error" in error_data:
                    error_detail = error_data["error"]
            except:
                pass
            status_message = f"Comicvine request failed: {error_detail}"
            logger.warning(
                "Comicvine HTTP error",
                trace_id=trace_id,
                status_code=e.response.status_code,
                error=error_detail,
            )
        except httpx.RequestError as e:
            ok = False
            status_message = f"Comicvine connection failed: {str(e)}"
            logger.warning(
                "Comicvine request error",
                trace_id=trace_id,
                error=str(e),
            )
        except Exception as e:
            ok = False
            status_message = f"Comicvine test failed: {str(e)}"
            logger.error(
                "Comicvine test exception",
                trace_id=trace_id,
                error=str(e),
                exc_info=True,
            )

    logger.info(
        "External APIs test completed",
        trace_id=trace_id,
        comicvine_ok=ok,
        status=status_message,
    )

    return JSONResponse(
        {
            "comicvine": {
                "status": status_message,
                "ok": ok,
            },
        }
    )


# Root Folders Management Endpoints
DEFAULT_ROOT_FOLDERS: list[dict[str, Any]] = []


def _get_root_folders() -> list[dict[str, Any]]:
    """Get root folders from settings.json or defaults."""
    settings_data = _load_settings_data()
    root_folders = settings_data.get("media_root_folders", DEFAULT_ROOT_FOLDERS.copy())

    if not isinstance(root_folders, list):
        root_folders = DEFAULT_ROOT_FOLDERS.copy()

    # Ensure each entry has required fields
    validated_folders: list[dict[str, Any]] = []
    for folder in root_folders:
        if isinstance(folder, dict) and "id" in folder and "folder" in folder:
            validated_folders.append(
                {
                    "id": str(folder["id"]),
                    "folder": str(folder["folder"]),
                }
            )

    return validated_folders


def _save_root_folders(root_folders: list[dict[str, Any]]) -> None:
    """Save root folders to settings.json."""
    settings_data = _load_settings_data()
    settings_data["media_root_folders"] = root_folders
    _save_settings_data(settings_data)


@router.get("/media/root-folders")
async def list_root_folders() -> JSONResponse:
    """List all root folders with disk usage stats."""
    trace_id = get_trace_id()
    logger.debug("Root folders list requested", trace_id=trace_id)

    import shutil

    def compute_disk_usage(path: str) -> dict[str, int]:
        try:
            usage = shutil.disk_usage(path)
            return {
                "total_bytes": usage.total,
                "free_bytes": usage.free,
                "used_bytes": usage.used,
            }
        except (FileNotFoundError, PermissionError, OSError):
            return {
                "total_bytes": 0,
                "free_bytes": 0,
                "used_bytes": 0,
            }

    root_folders = _get_root_folders()
    folders_with_stats: list[dict[str, Any]] = []

    for entry in root_folders:
        folder_path = entry.get("folder", "")
        stats = compute_disk_usage(folder_path)
        folders_with_stats.append(
            {
                "id": entry.get("id"),
                "folder": folder_path,
                "stats": stats,
            }
        )

    return JSONResponse({"root_folders": folders_with_stats})


@router.post("/media/root-folders", status_code=status.HTTP_201_CREATED)
async def add_root_folder(
    payload: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Add a new root folder."""
    trace_id = get_trace_id()
    logger.debug("Root folder add requested", trace_id=trace_id)

    import os
    import uuid

    folder = str(payload.get("folder", "")).strip()
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Folder path is required.",
        )

    if not os.path.exists(folder):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder does not exist.",
        )

    if not os.path.isdir(folder):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a directory.",
        )

    normalized_folder = os.path.abspath(folder)
    root_folders = _get_root_folders()

    # Check for duplicates (case-insensitive)
    existing = {os.path.abspath(entry["folder"]).lower() for entry in root_folders}
    if normalized_folder.lower() in existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Folder already added.",
        )

    entry = {
        "id": uuid.uuid4().hex,
        "folder": normalized_folder,
    }
    root_folders.append(entry)
    _save_root_folders(root_folders)

    logger.info(
        "Root folder added",
        trace_id=trace_id,
        folder_id=entry["id"],
        folder=normalized_folder,
    )

    return JSONResponse(
        {
            "id": entry["id"],
            "folder": entry["folder"],
        }
    )


@router.put("/media/root-folders/{folder_id}")
async def update_root_folder(
    folder_id: str,
    payload: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Update an existing root folder."""
    trace_id = get_trace_id()
    logger.debug("Root folder update requested", trace_id=trace_id, folder_id=folder_id)

    import os

    folder = str(payload.get("folder", "")).strip()
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Folder path is required.",
        )

    if not os.path.exists(folder):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder does not exist.",
        )

    if not os.path.isdir(folder):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a directory.",
        )

    normalized_folder = os.path.abspath(folder)
    root_folders = _get_root_folders()

    for entry in root_folders:
        if entry.get("id") == folder_id:
            # Check for duplicates (excluding current entry)
            existing = {
                os.path.abspath(other["folder"]).lower()
                for other in root_folders
                if other.get("id") != folder_id
            }
            if normalized_folder.lower() in existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Folder already added.",
                )

            entry["folder"] = normalized_folder
            _save_root_folders(root_folders)

            logger.info(
                "Root folder updated",
                trace_id=trace_id,
                folder_id=folder_id,
                folder=normalized_folder,
            )

            return JSONResponse(
                {
                    "id": entry["id"],
                    "folder": entry["folder"],
                }
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Root folder not found.",
    )


@router.delete("/media/root-folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_root_folder(
    folder_id: str,
) -> Response:
    """Delete a root folder."""
    trace_id = get_trace_id()
    logger.debug("Root folder delete requested", trace_id=trace_id, folder_id=folder_id)

    root_folders = _get_root_folders()

    for index, entry in enumerate(root_folders):
        if entry.get("id") == folder_id:
            root_folders.pop(index)
            _save_root_folders(root_folders)

            logger.info(
                "Root folder deleted",
                trace_id=trace_id,
                folder_id=folder_id,
            )

            return Response(status_code=status.HTTP_204_NO_CONTENT)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Root folder not found.",
    )


@router.get("/media/browse")
async def browse_directories(
    path: str | None = Query(None),
) -> JSONResponse:
    """Browse directories for folder selection."""
    trace_id = get_trace_id()
    logger.debug("Directory browse requested", trace_id=trace_id, path=path)

    import os
    from pathlib import Path

    if path:
        target = Path(path).expanduser()
        if not target.is_absolute():
            target = (Path.cwd() / target).resolve()
        else:
            target = target.resolve()
    else:
        target = Path.home()

    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Path does not exist.",
        )

    if not target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a directory.",
        )

    try:
        entries_iter = sorted(os.scandir(target), key=lambda entry: entry.name.lower())
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied.",
        ) from exc

    entries: list[dict[str, Any]] = []
    for entry in entries_iter:
        if not entry.is_dir(follow_symlinks=False):
            continue
        entry_path = Path(entry.path)
        entries.append(
            {
                "name": entry.name,
                "path": str(entry_path),
                "readable": os.access(entry_path, os.R_OK),
                "is_symlink": entry.is_symlink(),
            }
        )

    parent = str(target.parent) if target.parent != target else None

    return JSONResponse(
        {
            "path": str(target),
            "parent": parent,
            "entries": entries,
        }
    )


# Media format options
MEDIA_FORMAT_OPTIONS = ["No Conversion", "CBZ", "CBR", "CB7", "PDF"]


# Reading settings
def _get_reading_settings() -> dict[str, Any]:
    """Get reading settings from settings.json or return defaults."""
    settings_file = get_settings_file_path()
    default_settings = {
        "enabled": True,
        "reading_mode": "single",  # "single", "double"
        "double_page_gap": 0,  # Gap between pages in 2-page mode (in pixels, 0 = pages touch)
        # Future settings (prepared for later implementation)
        # "zoom_mode": "fit_width",  # "fit_width", "fit_height", "fit_both", "original"
        # "track_progress": True,
        # "auto_mark_read": False,
    }

    if settings_file.exists():
        try:
            with settings_file.open("r") as f:
                all_settings = json.load(f)
                reading_settings = all_settings.get("reading", {})
                # Merge with defaults
                result = default_settings.copy()
                result.update(reading_settings)
                return result
        except Exception as e:
            logger.warning("Failed to load reading settings from file", error=str(e))

    return default_settings


def _save_reading_settings(reading_settings: dict[str, Any]) -> None:
    """Save reading settings to settings.json."""
    settings_file = get_settings_file_path()

    # Load existing settings
    all_settings = {}
    if settings_file.exists():
        try:
            with settings_file.open("r") as f:
                all_settings = json.load(f)
        except Exception as e:
            logger.warning("Failed to load existing settings", error=str(e))

    # Update reading section
    all_settings["reading"] = reading_settings

    # Save back to file
    try:
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        with settings_file.open("w") as f:
            json.dump(all_settings, f, indent=2)
        logger.info("Reading settings saved")
    except Exception as e:
        logger.error("Failed to save reading settings", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save settings: {str(e)}",
        )


@router.get("/settings/reading")
async def get_reading_settings() -> JSONResponse:
    """Get reading settings."""
    settings = _get_reading_settings()
    return JSONResponse(
        {
            "settings": settings,
        }
    )


@router.put("/settings/reading")
async def update_reading_settings(
    settings_update: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Update reading settings."""
    current_settings = _get_reading_settings()

    # Merge with current settings
    updated_settings = current_settings.copy()
    updated_settings.update(settings_update)

    # Validate enabled is boolean
    if "enabled" in settings_update:
        if not isinstance(settings_update["enabled"], bool):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="enabled must be a boolean",
            )

    # Validate reading_mode
    if "reading_mode" in settings_update:
        if settings_update["reading_mode"] not in ("single", "double"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="reading_mode must be 'single' or 'double'",
            )

    # Validate double_page_gap
    if "double_page_gap" in settings_update:
        gap = settings_update["double_page_gap"]
        if not isinstance(gap, (int, float)) or gap < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="double_page_gap must be a non-negative number",
            )

    # Save updated settings
    _save_reading_settings(updated_settings)

    logger.info("Reading settings updated", updated_fields=list(settings_update.keys()))

    return JSONResponse(
        {
            "settings": updated_settings,
        }
    )


def _get_media_settings() -> dict[str, Any]:
    """Get media management settings from settings.json or return defaults."""
    settings_file = get_settings_file_path()
    default_settings = {
        "rename_downloaded_files": True,
        "replace_illegal_characters": True,
        "volume_folder_naming": "{Series Title} ({Year})",
        "file_naming": "{Series Title} ({Year}) - {Issue:000}.{ext}",
        "file_naming_empty": "{Series Title} ({Year}) - {Issue:000}.{ext}",
        "file_naming_special_version": "{Series Title} ({Year}) - {Issue:000} - {Special}.{ext}",
        "file_naming_vai": "{Series Title} ({Year}) - {Issue:000}.{ext}",
        "long_special_version": False,
        "create_empty_volume_folders": False,
        "delete_empty_folders": False,
        "unmonitor_deleted_issues": False,
        "convert": False,
        "extract_issue_ranges": False,
        "format_preference": ["No Conversion"],
    }

    if settings_file.exists():
        try:
            with settings_file.open("r") as f:
                all_settings = json.load(f)
                media_settings = all_settings.get("media_management", {})
                # Merge with defaults
                result = default_settings.copy()
                result.update(media_settings)
                return result
        except Exception as e:
            logger.warning("Failed to load media settings from file", error=str(e))

    return default_settings


def _save_media_settings(media_settings: dict[str, Any]) -> None:
    """Save media management settings to settings.json."""
    settings_file = get_settings_file_path()

    # Load existing settings
    all_settings = {}
    if settings_file.exists():
        try:
            with settings_file.open("r") as f:
                all_settings = json.load(f)
        except Exception as e:
            logger.warning("Failed to load existing settings", error=str(e))

    # Update media_management section
    all_settings["media_management"] = media_settings

    # Save back to file
    try:
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        with settings_file.open("w") as f:
            json.dump(all_settings, f, indent=2)
        logger.info("Media management settings saved")
    except Exception as e:
        logger.error("Failed to save media settings", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save settings: {str(e)}",
        )


@router.get("/settings/media-management")
async def get_media_management() -> JSONResponse:
    """Get media management settings."""
    settings = _get_media_settings()
    return JSONResponse(
        {
            "settings": settings,
            "format_options": MEDIA_FORMAT_OPTIONS,
        }
    )


@router.put("/settings/media-management")
async def update_media_management(
    payload: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Update media management settings."""

    # Get current settings
    current = _get_media_settings()

    # Validate and update fields
    updated = current.copy()

    # Boolean fields
    bool_fields = [
        "rename_downloaded_files",
        "replace_illegal_characters",
        "long_special_version",
        "create_empty_volume_folders",
        "delete_empty_folders",
        "unmonitor_deleted_issues",
        "convert",
        "extract_issue_ranges",
    ]
    for field in bool_fields:
        if field in payload:
            updated[field] = bool(payload[field])

    # String fields
    string_fields = [
        "volume_folder_naming",
        "file_naming",
        "file_naming_empty",
        "file_naming_special_version",
        "file_naming_vai",
    ]
    for field in string_fields:
        if field in payload:
            updated[field] = str(payload[field])

    # Format preference
    if "format_preference" in payload:
        if not isinstance(payload["format_preference"], list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Format preference must be a list"
            )
        clean_preference = []
        for item in payload["format_preference"]:
            if item in MEDIA_FORMAT_OPTIONS and item not in clean_preference:
                clean_preference.append(item)
        if not clean_preference:
            clean_preference = ["No Conversion"]
        updated["format_preference"] = clean_preference

    # Save updated settings
    _save_media_settings(updated)

    return JSONResponse(updated)


# Matching/Advanced Settings Endpoints
def _get_matching_settings() -> dict[str, Any]:
    """Get matching settings from settings.json or return defaults."""
    from comicarr.core.matching.config import DEFAULT_CONFIG

    settings_file = get_settings_file_path()
    default_settings = {
        "issue_number_exact_match": DEFAULT_CONFIG.issue_number_exact_match,
        "series_name_exact_match": DEFAULT_CONFIG.series_name_exact_match,
        "series_name_prefix_match": DEFAULT_CONFIG.series_name_prefix_match,
        "series_name_substring_match": DEFAULT_CONFIG.series_name_substring_match,
        "year_match": DEFAULT_CONFIG.year_match,
        "publisher_match": DEFAULT_CONFIG.publisher_match,
        "minimum_confidence": DEFAULT_CONFIG.minimum_confidence,
        "minimum_issue_match_score": DEFAULT_CONFIG.minimum_issue_match_score,
        "max_volume_score": DEFAULT_CONFIG.max_volume_score,
        "max_issue_score": DEFAULT_CONFIG.max_issue_score,
        "minimum_series_name_length_for_rejection": DEFAULT_CONFIG.minimum_series_name_length_for_rejection,
        "issue_search_limit": DEFAULT_CONFIG.issue_search_limit,
        "volume_search_limit": DEFAULT_CONFIG.volume_search_limit,
        "comicvine_cache_enabled": DEFAULT_CONFIG.comicvine_cache_enabled,
    }

    if settings_file.exists():
        try:
            with settings_file.open("r") as f:
                all_settings = json.load(f)
                matching_settings = all_settings.get("matching", {})
                # Merge with defaults
                result = default_settings.copy()
                result.update(matching_settings)
                return result
        except Exception as e:
            logger.warning("Failed to load matching settings from file", error=str(e))

    return default_settings


def _save_matching_settings(matching_settings: dict[str, Any]) -> None:
    """Save matching settings to settings.json."""
    settings_file = get_settings_file_path()

    # Load existing settings
    all_settings = {}
    if settings_file.exists():
        try:
            with settings_file.open("r") as f:
                all_settings = json.load(f)
        except Exception as e:
            logger.warning("Failed to load existing settings", error=str(e))

    # Update matching section
    all_settings["matching"] = matching_settings

    # Save back to file
    try:
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        with settings_file.open("w") as f:
            json.dump(all_settings, f, indent=2)
        logger.info("Matching settings saved")

        # Reload matching config to pick up new settings
        from comicarr.core.matching.config import reload_matching_config

        reload_matching_config()
    except Exception as e:
        logger.error("Failed to save matching settings", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save settings: {str(e)}",
        )


@router.get("/settings/advanced")
async def get_advanced_settings() -> JSONResponse:
    """Get advanced/matching settings."""
    settings = _get_matching_settings()
    return JSONResponse(
        {
            "settings": settings,
        }
    )


@router.put("/settings/advanced")
async def update_advanced_settings(
    settings_update: dict[str, Any] = Body(...),
) -> JSONResponse:
    """Update advanced/matching settings."""
    current_settings = _get_matching_settings()

    # Merge with current settings
    updated_settings = current_settings.copy()
    updated_settings.update(settings_update)

    # Validate all fields are numbers and within reasonable ranges
    float_fields = [
        "issue_number_exact_match",
        "series_name_exact_match",
        "series_name_prefix_match",
        "series_name_substring_match",
        "year_match",
        "publisher_match",
        "minimum_confidence",
        "minimum_issue_match_score",
        "max_volume_score",
        "max_issue_score",
    ]

    for field in float_fields:
        if field in settings_update:
            try:
                value = float(settings_update[field])
                if value < 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"{field} must be non-negative",
                    )
                updated_settings[field] = value
            except (TypeError, ValueError) as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {field}: {str(e)}"
                )

    # Validate integer fields
    integer_fields = [
        ("minimum_series_name_length_for_rejection", 0, 100),
        ("issue_search_limit", 1, 100),
        ("volume_search_limit", 1, 100),
    ]

    for field_name, min_val, max_val in integer_fields:
        if field_name in settings_update:
            try:
                value = int(settings_update[field_name])
                if value < min_val or value > max_val:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"{field_name} must be between {min_val} and {max_val}",
                    )
                updated_settings[field_name] = value
            except (TypeError, ValueError) as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid {field_name}: {str(e)}",
                )

    # Validate boolean fields
    boolean_fields = [
        "comicvine_cache_enabled",
    ]

    for field_name in boolean_fields:
        if field_name in settings_update:
            value = settings_update[field_name]
            if not isinstance(value, bool):
                # Try to convert string to boolean
                if isinstance(value, str):
                    value_lower = value.lower()
                    if value_lower in ("true", "1", "yes", "on"):
                        value = True
                    elif value_lower in ("false", "0", "no", "off"):
                        value = False
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"{field_name} must be a boolean value",
                        )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"{field_name} must be a boolean value",
                    )
            updated_settings[field_name] = value

    # Save updated settings
    _save_matching_settings(updated_settings)

    logger.info("Advanced/matching settings updated", updated_fields=list(settings_update.keys()))

    return JSONResponse(
        {
            "settings": updated_settings,
        }
    )
