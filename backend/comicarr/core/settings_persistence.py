"""Settings persistence to JSON file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from comicarr.core.config import get_settings, reload_settings

logger = structlog.get_logger("comicarr.settings_persistence")


def get_settings_file_path() -> Path:
    """Get path to settings.json file."""
    settings = get_settings()
    return settings.config_dir / "settings.json"


def save_settings_to_file(settings_dict: dict[str, Any]) -> None:  # noqa: ANN001
    """Save settings to settings.json file and reload settings.

    Args:
        settings_dict: Dictionary with settings to save.
            Uses Any for values because settings can be any JSON-serializable
            type (str, int, float, bool, dict, list, None). This is acceptable
            since we're dealing with JSON serialization.
    """
    settings = get_settings()
    settings_file = settings.config_dir / "settings.json"

    try:
        # Ensure config directory exists
        settings_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing settings if file exists
        existing = {}
        if settings_file.exists():
            with settings_file.open("r") as f:
                existing = json.load(f)

        # Merge new settings
        existing.update(settings_dict)

        # Save merged settings
        with settings_file.open("w") as f:
            json.dump(existing, f, indent=2)

        logger.info(
            "Settings saved to file",
            path=str(settings_file),
            settings=list(settings_dict.keys()),
        )

        # Reload settings so changes take effect immediately
        reload_settings()

    except Exception as e:
        logger.error(
            "Failed to save settings to file",
            path=str(settings_file),
            error=str(e),
            exc_info=True,
        )
        raise


def get_effective_settings() -> dict[str, Any]:  # noqa: ANN001
    """Get current effective settings as dictionary.

    Returns:
        Dictionary with setting keys and values. Uses Any for values because
        settings can be any JSON-serializable type (str, int, float, bool, dict, list, None).
        This is acceptable since we're dealing with JSON-serializable values.
    """
    settings = get_settings()

    # Load settings.json to get custom settings
    settings_file = settings.config_dir / "settings.json"
    custom_settings = {}
    if settings_file.exists():
        try:
            with settings_file.open("r") as f:
                import json

                custom_settings = json.load(f)
        except Exception:
            pass

    # Merge with defaults
    result = {
        "env": settings.env,
        "host_bind_address": settings.host_bind_address,
        "host_port": settings.host_port,
        "host_base_url": settings.host_base_url,
        "log_level": settings.log_level,
        "data_dir": str(settings.data_dir),
        "config_dir": str(settings.config_dir),
        "database_dir": str(settings.database_dir),
        "cache_dir": str(settings.cache_dir),
        "library_dir": str(settings.library_dir),
        "logs_dir": str(settings.logs_dir),
        "database_url": settings.database_url,
        # Weekly releases settings with defaults
        "weekly_releases": custom_settings.get(
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
        ),
    }

    return result
