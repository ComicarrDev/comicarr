"""Base abstract class for indexer clients."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog


class IndexerClient(ABC):
    """Abstract base class for indexer clients."""

    def __init__(self, name: str) -> None:
        """Initialize indexer client.

        Args:
            name: Name of the indexer (for logging)
        """
        self.name = name
        self.logger = structlog.get_logger(f"comicarr.indexers.{name.lower()}")

    @abstractmethod
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
            List of raw search results (will be normalized by SearchResultNormalizer)
            Each result should be a dict with at least: title, guid, link
        """
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test connection to the indexer.

        Returns:
            True if connection is successful, False otherwise
        """
        pass
