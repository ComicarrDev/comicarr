"""Shared utility functions for Comicarr."""

from __future__ import annotations

import re

# Type stub for ImportPendingFile to avoid circular imports
from typing import TYPE_CHECKING, Any
from urllib import parse as urllib_parse

if TYPE_CHECKING:
    from comicarr.db.models import ImportPendingFile


# File extension constants
SCANNABLE_EXTENSIONS = {".cbz", ".cbr", ".zip", ".cb7", ".rar", ".7z"}
DOWNLOAD_DIRECT_EXTENSIONS = {".cbz", ".cbr", ".cb7", ".zip", ".rar", ".7z"}
CONVERTIBLE_EXTENSIONS = {".zip", ".rar", ".7z", ".cbr", ".cb7"}  # Can be converted to CBZ
PREFERRED_EXTENSIONS = {".cbz": "CBZ", ".cbr": "CBR", ".cb7": "CB7", ".pdf": "PDF"}

# File size validation
MIN_COMIC_FILE_SIZE = (
    1 * 1024 * 1024
)  # 1 MB in bytes - files smaller than this are likely corrupted


def _decode_filename_fragment(value: str) -> str:
    """Decode URL-encoded filename fragment.

    Args:
        value: Filename fragment to decode

    Returns:
        Decoded filename fragment
    """

    def repl(match: re.Match[str]) -> str:
        return "%" + match.group(1)

    candidate = re.sub(r"_(\d{2})", repl, value)
    decoded = urllib_parse.unquote(candidate)
    decoded = decoded.replace("_", " ")
    return decoded


def _extract_year(value: str | None) -> str | None:
    """Extract a 4-digit year from a string.

    Args:
        value: String to extract year from

    Returns:
        Year as string (e.g., "2025") or None if not found
    """
    if not value:
        return None
    match = re.search(r"(19|20)\d{2}", value)
    if match:
        return match.group(0)
    return None


def compute_issue_status(monitored: bool) -> str:
    """Compute issue status based on monitoring setting.

    Args:
        monitored: Whether the issue is monitored

    Returns:
        "wanted" if monitored, "ignored" otherwise
    """
    return "wanted" if monitored else "ignored"


def normalize_issue_number(value: str | None) -> float | None:
    """Normalize an issue number string to a float.

    Handles fractional issue numbers (½, ¼, ¾) and various formats.

    Args:
        value: Issue number string (e.g., "001", "1.5", "½")

    Returns:
        Normalized issue number as float, or None if invalid
    """
    if not value:
        return None
    text = _decode_filename_fragment(value.strip()).lower()
    if not text:
        return None
    replacements = {
        "½": ".5",
        "¼": ".25",
        "¾": ".75",
    }
    for token, replacement in replacements.items():
        text = text.replace(token, replacement)
    text = text.replace(",", ".").replace("_", ".").replace("#", " ")
    text = re.sub(r"(?<=\d)[a-z]+", "", text)
    text = re.sub(r"[^0-9.\-]", " ", text)
    text = text.strip()
    if not text:
        return None
    # Some filenames include multiple numbers; take first segment that parses.
    for candidate in text.split():
        if candidate.count(".") > 1:
            continue
        if candidate in {"-", "--", "-.", "."}:
            continue
        try:
            return float(candidate)
        except ValueError:
            continue
    return None


def _extract_numeric_id(value: Any) -> int | None:
    """Extract a numeric ID from a value (usually from ComicVine API response).

    Args:
        value: Value that may contain an ID (e.g., "4050-123456", 123456, "volume/4050-123456")

    Returns:
        Numeric ID as int, or None if not found
    """
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


def _simplify_label(value: str | None) -> str:
    """Simplify a label by removing special characters (except word-connected hyphens) and lowercasing.

    Preserves hyphens connected to words (e.g., "Spider-Man" → "spider-man").
    Strips hyphens with spaces around them (e.g., "Star Wars - Union" → "starwarsunion").
    Removes colons, spaces, and other punctuation to handle subtitles.
    Normalizes "&" to "and" and removes "and" as a connector word.

    Args:
        value: Label to simplify

    Returns:
        Simplified label (lowercase, alphanumeric and word-connected hyphens only)
    """
    if not value:
        return ""
    # Lowercase first
    normalized = value.lower()
    # Replace "&" with "and" to normalize both forms
    normalized = normalized.replace("&", "and")
    # Remove "and" as a connector word (with spaces around it or at word boundaries)
    # This handles "Iron and Frost" → "iron frost" and "Iron & Frost" → "iron frost"
    normalized = re.sub(r"\s+and\s+", " ", normalized)
    normalized = re.sub(r"^and\s+", "", normalized)  # "and" at start
    normalized = re.sub(r"\s+and$", "", normalized)  # "and" at end
    # Remove space-hyphen-space patterns (used as separators)
    normalized = re.sub(r"\s+-\s+", "", normalized)
    # Remove all spaces
    normalized = re.sub(r"\s+", "", normalized)
    # Keep alphanumeric and hyphens, remove everything else (colons, etc.)
    normalized = re.sub(r"[^a-z0-9-]+", "", normalized)
    # Normalize multiple consecutive hyphens to single hyphen
    normalized = re.sub(r"-+", "-", normalized)
    # Remove leading/trailing hyphens
    normalized = normalized.strip("-")
    return normalized


def _normalized_strings_match(str1: str, str2: str) -> bool:
    """Check if two normalized strings match, treating common words as optional.

    Common words like "the", "a", "an" are made optional in the comparison,
    but only when they appear as complete words (not substrings of other words).
    For example, "spidergwentheghostspider" matches "spidergwenghostspider",
    but "the" in "there" or "theater" is NOT treated as optional.

    Args:
        str1: First normalized string
        str2: Second normalized string

    Returns:
        True if strings match (with common words treated as optional)
    """
    if not str1 or not str2:
        return str1 == str2

    # Exact match first
    if str1 == str2:
        return True

    # Common words to make optional (only as whole words)
    common_words = ["the", "a", "an"]

    # Try matching str1 against str2 (with common words optional in str1)
    pattern1 = _make_common_words_optional(str1, common_words)
    if re.fullmatch(pattern1, str2):
        return True

    # Try matching str2 against str1 (with common words optional in str2)
    pattern2 = _make_common_words_optional(str2, common_words)
    if re.fullmatch(pattern2, str1):
        return True

    # Fall back to exact match
    return str1 == str2


def _make_common_words_optional(text: str, common_words: list[str]) -> str:
    """Make common words optional in a normalized string, but only as whole words.

    A word is considered "whole" if it appears:
    - At the start of the string (followed by letter/digit/hyphen)
    - At the end of the string (preceded by letter/digit/hyphen)
    - In the middle (preceded and followed by letter/digit/hyphen)

    This prevents matching "the" inside "there" or "theater".

    Args:
        text: Normalized string (no spaces, only letters, numbers, hyphens)
        common_words: List of common words to make optional

    Returns:
        Regex pattern with common words made optional
    """
    pattern = text

    # Process longer words first to avoid partial matches (e.g., "an" before "a")
    sorted_words = sorted(common_words, key=len, reverse=True)

    # Handle common words at the start - find all consecutive common words
    start_match = ""
    remaining = text
    while remaining:
        matched = False
        for word in sorted_words:
            if (
                remaining.startswith(word)
                and len(remaining) > len(word)
                and remaining[len(word)] in "abcdefghijklmnopqrstuvwxyz0123456789-"
            ):
                start_match += f"({word})?"
                remaining = remaining[len(word) :]
                matched = True
                break
        if not matched:
            break

    if start_match:
        pattern = start_match + remaining
        # Also need to handle middle/end positions in the remaining part
        remaining = pattern[len(start_match) :]
    else:
        remaining = pattern

    # Handle common words at the end - work backwards
    end_match = ""
    remaining_end = remaining
    while remaining_end:
        matched = False
        for word in sorted_words:
            if (
                remaining_end.endswith(word)
                and len(remaining_end) > len(word)
                and remaining_end[-len(word) - 1] in "abcdefghijklmnopqrstuvwxyz0123456789-"
            ):
                end_match = f"({word})?" + end_match
                remaining_end = remaining_end[: -len(word)]
                matched = True
                break
        if not matched:
            break

    if end_match:
        pattern = start_match + remaining_end + end_match

    # Handle common words in the middle (not at start/end)
    # Only process the middle part (between start and end matches)
    middle_part = remaining_end if start_match or end_match else pattern
    for word in sorted_words:
        # Skip if word is at start or end (already handled)
        if start_match and middle_part.startswith(word):
            continue
        if end_match and middle_part.endswith(word):
            continue

        # Escape the word for regex
        escaped_word = re.escape(word)

        # Pattern: word in middle (preceded and followed by letter/digit/hyphen)
        middle_part = re.sub(
            rf"(?<=[a-z0-9-]){escaped_word}(?=[a-z0-9-])", f"({word})?", middle_part
        )

    if start_match or end_match:
        pattern = start_match + middle_part + end_match

    return pattern


def calculate_pending_file_counts(pending_files: list[ImportPendingFile]) -> dict[str, int]:
    """Calculate counts for pending files using consistent logic.

    This function ensures that counts are calculated the same way everywhere,
    preventing mismatches between job summary and pending files filter.

    Matching is determined by fields (matched_volume_id, comicvine_volume_id), not status.
    Status is for workflow: pending, import, skipped, processed.
    Note: "processed" files are historical records and are not included in workflow counts.

    Args:
        pending_files: List of ImportPendingFile objects to count

    Returns:
        Dictionary with keys: library_match, comicvine_match, pending, import, skipped, total
    """
    # Import here to avoid circular imports

    # Count matches based on fields, not status
    library_match = sum(1 for pf in pending_files if pf.matched_volume_id or pf.matched_issue_id)
    comicvine_match = sum(
        1 for pf in pending_files if pf.comicvine_volume_id or pf.comicvine_issue_id
    )

    # Count statuses (workflow state)
    pending = sum(1 for pf in pending_files if pf.status == "pending")
    import_count = sum(1 for pf in pending_files if pf.status == "import")
    # Count skipped: status is "skipped" OR action is "skip" (for backwards compatibility)
    skipped = sum(1 for pf in pending_files if pf.status == "skipped" or pf.action == "skip")
    total = len(pending_files)

    return {
        "library_match": library_match,
        "comicvine_match": comicvine_match,
        "pending": pending,
        "import": import_count,
        "skipped": skipped,
        "total": total,
    }
