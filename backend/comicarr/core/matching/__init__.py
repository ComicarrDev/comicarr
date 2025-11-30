"""Modular matching system for ComicVine searches.

This module provides a clean, extensible system for matching comic files
to ComicVine data with configurable scoring weights and criteria.
"""

from .config import DEFAULT_CONFIG, MatchingConfig, get_matching_config, reload_matching_config
from .criteria import (
    match_issue_number,
    match_publisher,
    match_series_name,
    match_year,
)
from .evaluator import MatchResult, evaluate_issue_candidate, evaluate_volume_candidate
from .results import build_volume_picker_result, normalize_confidence

__all__ = [
    "MatchingConfig",
    "DEFAULT_CONFIG",
    "get_matching_config",
    "reload_matching_config",
    "match_issue_number",
    "match_series_name",
    "match_year",
    "match_publisher",
    "MatchResult",
    "evaluate_issue_candidate",
    "evaluate_volume_candidate",
    "build_volume_picker_result",
    "normalize_confidence",
]
