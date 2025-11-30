"""Torznab-compatible indexer client (same as Newznab, different default category)."""

from __future__ import annotations

from typing import Any

from comicarr.core.indexers.newznab import NewznabClient


class TorznabClient(NewznabClient):
    """Client for interacting with Torznab-compatible indexers (Prowlarr/Jackett).

    Torznab uses the same API structure as Newznab, so we inherit from NewznabClient.
    The main difference is the default category (torrents use different categories).
    """

    async def search(
        self,
        query: str | None = None,
        title: str | None = None,
        issue_number: str | None = None,
        year: int | None = None,
        categories: list[int] | None = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """Search for content.

        Args:
            query: General search query
            title: Series/volume title
            issue_number: Issue number (e.g., "1", "1.5")
            year: Publication year
            categories: List of category IDs to filter by
            max_results: Maximum number of results to return

        Returns:
            List of search results (same format as Newznab)
        """
        # Call parent search, but with different default category if not specified
        # Torznab uses the same category structure, so we can reuse Newznab logic
        return await super().search(
            query=query,
            title=title,
            issue_number=issue_number,
            year=year,
            categories=categories or [7030],  # Default to comics category
            max_results=max_results,
        )
