"""Individual match criteria evaluators.

Each function evaluates a single aspect of a match (issue number, series name, year, etc.)
and returns a score and reason. This modular approach makes it easy to:
- Test each criterion independently
- Adjust scoring weights
- Add new criteria
"""

from comicarr.core.utils import _simplify_label, normalize_issue_number

from .config import MatchingConfig, get_matching_config


def match_issue_number(
    candidate_issue_number: str | None,
    search_issue_number: float | None,
    config: MatchingConfig | None = None,
) -> tuple[float, str]:
    """Evaluate issue number match.

    Args:
        candidate_issue_number: Issue number from candidate (string, e.g., "127", "1.5")
        search_issue_number: Normalized issue number we're searching for (float)
        config: Matching configuration (if None, loads from settings file)

    Returns:
        Tuple of (score, reason)
        Returns (-1.0, reason) if candidate should be rejected
        Returns (0.0, reason) if no match but not rejected
        Returns (positive_score, reason) if match found
    """
    if config is None:
        config = get_matching_config()

    if search_issue_number is None:
        return 0.0, "No issue number in search"

    candidate_normalized = normalize_issue_number(candidate_issue_number)
    if candidate_normalized is None:
        return -1.0, "No issue number in candidate"

    if abs(candidate_normalized - search_issue_number) >= 0.01:
        return -1.0, f"Issue number mismatch: {candidate_normalized} vs {search_issue_number}"

    return (
        config.issue_number_exact_match,
        f"Issue number match: {candidate_normalized} (+{config.issue_number_exact_match})",
    )


def match_series_name(
    candidate_volume_name: str,
    search_series_name: str,
    config: MatchingConfig | None = None,
) -> tuple[float, str]:
    """Evaluate series name match.

    Args:
        candidate_volume_name: Volume name from candidate
        search_series_name: Series name we're searching for
        config: Matching configuration (if None, loads from settings file)

    Returns:
        Tuple of (score, reason)
    """
    if config is None:
        config = get_matching_config()

    series_key = _simplify_label(search_series_name)
    volume_key = _simplify_label(candidate_volume_name)

    if volume_key == series_key:
        return (
            config.series_name_exact_match,
            f"Exact match: '{series_key}' == '{volume_key}' (+{config.series_name_exact_match})",
        )

    if not (volume_key and series_key):
        return 0.0, f"Empty key: series='{series_key}', volume='{volume_key}'"

    prefix_len = max(3, len(series_key) // 2)
    if volume_key.startswith(series_key[:prefix_len]):
        return (
            config.series_name_prefix_match,
            f"Prefix match: '{volume_key}' starts with '{series_key[:prefix_len]}' (+{config.series_name_prefix_match})",
        )

    if series_key in volume_key:
        return (
            config.series_name_substring_match,
            f"Substring match: '{series_key}' found in '{volume_key}' (+{config.series_name_substring_match})",
        )

    if volume_key in series_key:
        return (
            config.series_name_substring_match,
            f"Substring match: '{volume_key}' found in '{series_key}' (+{config.series_name_substring_match})",
        )

    return 0.0, f"No match: '{series_key}' vs '{volume_key}'"


def match_year(
    candidate_volume_year: str | None,
    search_year: int | None,
    config: MatchingConfig | None = None,
) -> tuple[float, str]:
    """Evaluate year match.

    Args:
        candidate_volume_year: Start year from candidate volume (string or None)
        search_year: Year we're searching for (int or None)
        config: Matching configuration (if None, loads from settings file)

    Returns:
        Tuple of (score, reason)
    """
    if config is None:
        config = get_matching_config()

    if search_year is None:
        return 0.0, "No year in search"

    if not candidate_volume_year:
        return 0.0, "No year in candidate"

    try:
        candidate_year = int(candidate_volume_year)
        if candidate_year == search_year:
            return (
                config.year_match,
                f"Year match: {search_year} (+{config.year_match})",
            )
        return 0.0, f"No match: {candidate_year} vs {search_year}"
    except (ValueError, TypeError):
        return 0.0, f"Invalid year in candidate: {candidate_volume_year}"


def match_publisher(
    candidate_publisher: str | None,
    search_publisher: str | None,
    config: MatchingConfig | None = None,
) -> tuple[float, str]:
    """Evaluate publisher match.

    Args:
        candidate_publisher: Publisher name from candidate
        search_publisher: Publisher name we're searching for
        config: Matching configuration (if None, loads from settings file)

    Returns:
        Tuple of (score, reason)
    """
    if config is None:
        config = get_matching_config()

    if search_publisher is None:
        return 0.0, "No publisher in search"

    if not candidate_publisher:
        return 0.0, "No publisher in candidate"

    search_key = _simplify_label(search_publisher)
    candidate_key = _simplify_label(candidate_publisher)

    if search_key == candidate_key:
        return (
            config.publisher_match,
            f"Publisher match: '{search_key}' == '{candidate_key}' (+{config.publisher_match})",
        )

    return 0.0, f"No match: '{search_key}' vs '{candidate_key}'"
