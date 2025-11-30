"""Normalizer for converting raw indexer results to standardized SearchResult format."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from comicarr.core.search.models import DownloadLink, SearchResult
from comicarr.db.models import Indexer

logger = structlog.get_logger("comicarr.search.normalizer")


class SearchResultNormalizer:
    """Normalizes raw indexer results to standardized SearchResult format."""

    def __init__(self) -> None:
        """Initialize normalizer."""
        self.logger = structlog.get_logger("comicarr.search.normalizer")

    def normalize(
        self,
        raw_result: dict[str, Any],
        indexer: Indexer,
    ) -> SearchResult:
        """Normalize a raw search result to SearchResult format.

        Args:
            raw_result: Raw result from indexer (dict format)
            indexer: Indexer that returned this result

        Returns:
            Normalized SearchResult
        """
        # Determine source type
        source_type = (
            "http"
            if indexer.type == "builtin_http"
            else ("torrent" if indexer.type == "torrent" else "usenet")
        )

        # Parse publication date
        pub_date = None
        if pub_date_str := raw_result.get("pubDate"):
            pub_date = self._parse_date(pub_date_str)

        # Extract size
        size = raw_result.get("size")
        if size:
            try:
                size = int(size)
            except (ValueError, TypeError):
                size = None

        # Extract categories
        categories = raw_result.get("categories", [])
        if isinstance(categories, str):
            categories = [int(c.strip()) for c in categories.split(",") if c.strip().isdigit()]
        elif not isinstance(categories, list):
            categories = []

        # Build base result
        result = SearchResult(
            title=raw_result.get("title", ""),
            guid=raw_result.get("guid", raw_result.get("link", "")),
            link=raw_result.get("link", ""),
            pub_date=pub_date,
            size=size,
            categories=categories,
            indexer_id=indexer.id,
            indexer_name=indexer.name,
            source_type=source_type,
        )

        # Handle HTTP indexer-specific fields
        if indexer.type == "builtin_http":
            # GetComics returns multiple download links
            if download_links := raw_result.get("download_links"):
                result.download_links = [
                    DownloadLink(**link) if isinstance(link, dict) else link
                    for link in download_links
                ]

            # ReadComicsOnline requires scraping
            if indexer.id == "readcomicsonline":
                result.requires_scraping = True

        # Handle volume pack information
        if is_pack := raw_result.get("is_volume_pack", False):
            result.is_volume_pack = True
            result.covers_issues = raw_result.get("covers_issues", [])
            result.pack_issue_count = raw_result.get("pack_issue_count")

        return result

    def _parse_date(self, date_str: str) -> datetime | None:
        """Parse date string to datetime.

        Args:
            date_str: Date string in various formats

        Returns:
            Parsed datetime or None if parsing fails
        """
        if not date_str:
            return None

        # Try ISO format first
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

        # Try common formats
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",  # RFC 2822
            "%a, %d %b %Y %H:%M:%S %Z",  # RFC 2822 with timezone name
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except (ValueError, AttributeError):
                continue

        return None
