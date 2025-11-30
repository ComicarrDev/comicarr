"""GetComics indexer client for searching getcomics.info."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from comicarr.core.indexers.base import IndexerClient

logger = structlog.get_logger("comicarr.indexers.getcomics")


class GetComicsIndexer(IndexerClient):
    """Indexer client for GetComics website."""

    def __init__(
        self,
        name: str,
        base_url: str = "https://getcomics.info",
        timeout: int = 30,
    ) -> None:
        """Initialize GetComics indexer.

        Args:
            name: Name of the indexer (for logging)
            base_url: Base URL of GetComics website
            timeout: Request timeout in seconds
        """
        super().__init__(name)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(timeout), follow_redirects=True)

    async def __aenter__(self) -> GetComicsIndexer:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.client.aclose()

    async def search(
        self,
        query: str | None = None,
        title: str | None = None,
        issue_number: str | None = None,
        year: int | None = None,
        categories: list[int] | None = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """Search GetComics for content.

        Args:
            query: General search query
            title: Series/volume title
            issue_number: Issue number (e.g., "1", "1.5")
            year: Publication year
            categories: Not used for GetComics (ignored)
            max_results: Maximum number of results to return

        Returns:
            List of search results, each containing:
            - title: Post title
            - link: URL to GetComics post
            - guid: Same as link (post URL)
            - pubDate: Publication date (if available)
            - size: Not available (None)
            - description: Post description/excerpt
        """
        # Build search query
        search_terms: list[str] = []
        if query:
            search_terms.append(query)
        if title:
            search_terms.append(title)
        if issue_number:
            search_terms.append(f"#{issue_number}")
        if year:
            search_terms.append(str(year))

        if not search_terms:
            self.logger.warning("No search terms provided")
            return []

        search_query = " ".join(search_terms)

        # GetComics search URL
        search_url = f"{self.base_url}/?s={search_query.replace(' ', '+')}"

        try:
            self.logger.debug("Searching GetComics", query=search_query, url=search_url)
            response = await self.client.get(search_url)
            response.raise_for_status()

            # TODO: Parse HTML response to extract post links
            # For now, return placeholder structure
            # This will be implemented when we add HTML parsing

            results = []
            # Placeholder: Parse HTML and extract posts
            # Each post should be returned as:
            # {
            #     "title": "Post title",
            #     "link": "https://getcomics.info/...",
            #     "guid": "https://getcomics.info/...",
            #     "pubDate": "",
            #     "size": None,
            #     "description": "Post excerpt"
            # }

            self.logger.info(
                "GetComics search completed",
                query=search_query,
                results_count=len(results),
            )
            return results

        except Exception as e:
            self.logger.error("GetComics search failed", error=str(e))
            return []

    async def test_connection(self) -> bool:
        """Test connection to GetComics.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            response = await self.client.get(self.base_url, timeout=self.timeout)
            response.raise_for_status()
            return True
        except Exception as e:
            self.logger.error("GetComics connection test failed", error=str(e))
            return False
