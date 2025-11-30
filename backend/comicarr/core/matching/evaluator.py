"""Match evaluator - orchestrates all criteria.

This module provides high-level evaluation functions that combine
all individual criteria to produce a final match score.
"""

from typing import Any

import structlog

from comicarr.core.utils import _simplify_label

from .config import MatchingConfig, get_matching_config
from .criteria import (
    match_issue_number,
    match_publisher,
    match_series_name,
    match_year,
)

logger = structlog.get_logger("comicarr.matching")


class MatchResult:
    """Result of a match evaluation.

    Attributes:
        score: Raw score (sum of all criteria scores)
        details: List of strings explaining each match criterion
        rejected: Whether this candidate should be rejected
    """

    def __init__(self, score: float, details: list[str], rejected: bool = False):
        self.score = score
        self.details = details
        self.rejected = rejected

    def __repr__(self) -> str:
        status = "REJECTED" if self.rejected else "ACCEPTED"
        return f"MatchResult(score={self.score}, status={status}, details={len(self.details)})"


def evaluate_issue_candidate(
    issue_item: dict[str, Any],
    volume_info: dict[str, Any],
    search_params: dict[str, Any],
    config: MatchingConfig | None = None,
) -> MatchResult:
    """Evaluate an issue candidate against search parameters.

    Args:
        issue_item: Issue data from ComicVine (must have "issue_number")
        volume_info: Full volume data (must have "name", "start_year", "publisher")
        search_params: Dict with keys:
            - series_name: str (required)
            - issue_number: Optional[float] (normalized)
            - year: Optional[int]
            - publisher: Optional[str]
        config: Matching configuration (if None, loads from settings file)

    Returns:
        MatchResult with score and details
    """
    if config is None:
        config = get_matching_config()

    score = 0.0
    details: list[str] = []

    # Issue number match (critical - can reject)
    issue_score, issue_reason = match_issue_number(
        issue_item.get("issue_number"),
        search_params.get("issue_number"),
        config,
    )
    if issue_score < 0:
        return MatchResult(-1.0, [issue_reason], rejected=True)
    if issue_score > 0:
        score += issue_score
        details.append(issue_reason)

    # Series name match
    volume_name = volume_info.get("name", "")
    name_score, name_reason = match_series_name(
        volume_name,
        search_params["series_name"],
        config,
    )
    score += name_score
    details.append(name_reason)

    # Require series name match when we have issue number
    # This prevents matching "Alien vs. Captain America #001" to "Comix Kiss Comix #001"
    if search_params.get("issue_number") and name_score == 0.0:
        series_key = _simplify_label(search_params["series_name"])
        if len(series_key) > config.minimum_series_name_length_for_rejection:
            logger.debug(
                "Rejecting candidate - issue number matches but series name doesn't",
                search_series=search_params["series_name"],
                candidate_volume=volume_name,
                issue_number=search_params.get("issue_number"),
            )
            return MatchResult(
                -1.0,
                [f"Series name mismatch: {name_reason}"],
                rejected=True,
            )

    # Year match
    year_score, year_reason = match_year(
        volume_info.get("start_year"),
        search_params.get("year"),
        config,
    )
    score += year_score
    details.append(year_reason)

    # Publisher match (optional - only adds to score if matches)
    publisher_name = None
    pub_data = volume_info.get("publisher")
    if isinstance(pub_data, dict):
        publisher_name = pub_data.get("name")
    elif pub_data:
        publisher_name = str(pub_data)

    pub_score, pub_reason = match_publisher(
        publisher_name,
        search_params.get("publisher"),
        config,
    )
    score += pub_score
    if pub_score > 0:
        details.append(pub_reason)

    return MatchResult(score, details, rejected=False)


def evaluate_volume_candidate(
    volume_item: dict[str, Any],
    search_params: dict[str, Any],
    config: MatchingConfig | None = None,
) -> MatchResult:
    """Evaluate a volume candidate against search parameters.

    This is used when searching volumes directly (not through issues).

    Args:
        volume_item: Volume data from ComicVine (must have "name", "start_year", "publisher")
        search_params: Dict with keys:
            - series_name: str (required)
            - year: Optional[int]
            - publisher: Optional[str]
        config: Matching configuration (if None, loads from settings file)

    Returns:
        MatchResult with score and details
    """
    if config is None:
        config = get_matching_config()

    score = 0.0
    details: list[str] = []

    # Series name match
    volume_name = volume_item.get("name", "")
    name_score, name_reason = match_series_name(
        volume_name,
        search_params["series_name"],
        config,
    )
    score += name_score
    details.append(name_reason)

    # Year match
    year_score, year_reason = match_year(
        volume_item.get("start_year"),
        search_params.get("year"),
        config,
    )
    score += year_score
    details.append(year_reason)

    # Publisher match (optional)
    publisher_name = None
    pub_data = volume_item.get("publisher")
    if isinstance(pub_data, dict):
        publisher_name = pub_data.get("name")
    elif pub_data:
        publisher_name = str(pub_data)

    pub_score, pub_reason = match_publisher(
        publisher_name,
        search_params.get("publisher"),
        config,
    )
    score += pub_score
    if pub_score > 0:
        details.append(pub_reason)

    return MatchResult(score, details, rejected=False)
