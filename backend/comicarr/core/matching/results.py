"""Result builders for matching system.

Functions to build and format results for the volume picker
and normalize scores to confidence values.
"""

from typing import Any

from .config import MatchingConfig, get_matching_config


def normalize_confidence(
    raw_score: float,
    max_score: float,
    config: MatchingConfig | None = None,
) -> float:
    """Normalize raw score to confidence (0.0-1.0).

    Args:
        raw_score: Raw match score
        max_score: Maximum possible score for this match type
        config: Matching configuration (unused but kept for consistency)

    Returns:
        Confidence value between 0.0 and 1.0
    """
    if raw_score <= 0:
        return 0.0
    return min(raw_score / max_score, 1.0)


def build_volume_picker_result(
    volume_info: dict[str, Any],
    raw_score: float,
    match_details: list[str],
    config: MatchingConfig | None = None,
    rank: int | None = None,
    issue_image_url: str | None = None,
) -> dict[str, Any]:
    """Build a volume result for the volume picker UI.

    Args:
        volume_info: Volume data from ComicVine
        raw_score: Raw match score
        match_details: List of match detail strings
        config: Matching configuration (if None, loads from settings file)
        rank: Optional rank/position in results
        issue_image_url: Optional issue image URL for this volume (for cover comparison)

    Returns:
        Dict with volume data formatted for UI
    """
    if config is None:
        config = get_matching_config()

    # Extract image URL
    image_url = None
    image_data = volume_info.get("image")
    if isinstance(image_data, dict):
        image_url = (
            image_data.get("super_url")
            or image_data.get("medium_url")
            or image_data.get("small_url")
            or image_data.get("thumb_url")
        )
    elif image_data:
        image_url = str(image_data)

    # Extract publisher
    publisher_name = None
    pub_data = volume_info.get("publisher")
    if isinstance(pub_data, dict):
        publisher_name = pub_data.get("name")
    elif pub_data:
        publisher_name = str(pub_data)

    # Extract volume ID
    import re

    def _extract_numeric_id(value: Any) -> int | None:
        """Extract numeric ID from ComicVine ID format."""
        if value is None:
            return None
        text = str(value).strip()
        match = re.search(r"(\d+)$", text)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    volume_id = _extract_numeric_id(volume_info.get("id"))
    if not volume_id:
        raise ValueError("Volume info missing ID")

    # Normalize confidence
    confidence = normalize_confidence(raw_score, config.max_volume_score, config)

    # Determine match classification
    match_classification = "no_match"
    if confidence >= 1.0:
        match_classification = "exact"
    elif confidence >= 0.7:
        match_classification = "substring"
    elif confidence >= 0.5:
        match_classification = "word_overlap"
    elif confidence > 0.0:
        match_classification = "partial"

    result = {
        "id": volume_info.get("id"),
        "name": volume_info.get("name", ""),
        "start_year": volume_info.get("start_year"),
        "publisher": publisher_name,
        "site_detail_url": volume_info.get("site_detail_url"),
        "image_url": image_url,
        "cv_volume_id": volume_id,
        "count_of_issues": volume_info.get("count_of_issues"),
        "rank": rank,
        "confidence": confidence,
        "raw_score": raw_score,
        "match_classification": match_classification,
        "match_details": match_details,
        "is_best_match": False,  # Will be set by caller
    }

    # Add issue image URL if provided (for cover comparison in volume picker)
    if issue_image_url:
        result["issue_image_url"] = issue_image_url

    return result
