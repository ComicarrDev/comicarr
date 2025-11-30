"""Matching configuration - scoring weights and thresholds."""

from dataclasses import dataclass


@dataclass
class MatchingConfig:
    """Configuration for ComicVine matching.

    This class centralizes all scoring weights and thresholds,
    making it easy to adjust matching behavior.
    """

    # Scoring weights
    issue_number_exact_match: float = 5.0
    series_name_exact_match: float = 3.0
    series_name_prefix_match: float = 1.5
    series_name_substring_match: float = 1.0
    year_match: float = 0.5
    publisher_match: float = 1.0

    # Thresholds
    minimum_confidence: float = 0.3
    minimum_issue_match_score: float = 5.0  # Require issue match for issue search

    # Normalization
    max_volume_score: float = 3.5  # 3.0 (name) + 0.5 (year)
    max_issue_score: float = 8.5  # 5.0 (issue) + 3.0 (name) + 0.5 (year)

    # Validation
    minimum_series_name_length_for_rejection: int = 5  # Don't reject if series name is too short

    # Search limits
    issue_search_limit: int = 30  # Number of issues to fetch from ComicVine API
    volume_search_limit: int = 10  # Number of volumes to fetch from ComicVine API

    # Caching
    comicvine_cache_enabled: bool = True  # Enable/disable ComicVine API response caching


# Default config instance
DEFAULT_CONFIG = MatchingConfig()

# Cached config instance (loaded from settings file)
_cached_config: MatchingConfig | None = None


def get_matching_config() -> MatchingConfig:
    """Get the current matching configuration.

    Loads from settings.json if available, otherwise returns defaults.
    Caches the result for performance.

    Returns:
        MatchingConfig instance with current settings
    """
    global _cached_config

    # Try to load from settings file
    try:
        import json

        from comicarr.core.settings_persistence import get_settings_file_path

        settings_file = get_settings_file_path()
        if settings_file.exists():
            with settings_file.open("r") as f:
                all_settings = json.load(f)
                matching_settings = all_settings.get("matching")

                if matching_settings:
                    # Create config from saved settings
                    _cached_config = MatchingConfig(**matching_settings)
                    return _cached_config
    except Exception:
        # If loading fails, fall back to defaults
        pass

    # Return cached config or defaults
    if _cached_config is None:
        _cached_config = DEFAULT_CONFIG

    return _cached_config


def reload_matching_config() -> None:
    """Reload matching configuration from settings file.

    Call this after updating settings to ensure new values are used.
    """
    global _cached_config
    _cached_config = None
    get_matching_config()  # Force reload
