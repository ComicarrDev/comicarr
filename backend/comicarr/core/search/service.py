"""Search service for orchestrating searches across multiple indexers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.indexers.base import IndexerClient
from comicarr.core.indexers.getcomics import GetComicsIndexer
from comicarr.core.indexers.newznab import NewznabClient
from comicarr.core.indexers.readcomicsonline import ReadComicsOnlineIndexer
from comicarr.core.indexers.torznab import TorznabClient
from comicarr.core.search.blacklist import BlacklistManager
from comicarr.core.search.cache import CacheManager
from comicarr.core.search.models import SearchPreferences, SearchResult
from comicarr.core.search.normalizer import SearchResultNormalizer
from comicarr.db.models import Indexer

if TYPE_CHECKING:
    from comicarr.db.models import LibraryIssue

logger = structlog.get_logger("comicarr.search.service")


class SearchService:
    """Service for orchestrating searches across multiple indexers."""

    def __init__(
        self,
        cache_manager: CacheManager,
        blacklist_manager: BlacklistManager,
        normalizer: SearchResultNormalizer,
        preferences: SearchPreferences | None = None,
    ) -> None:
        """Initialize search service.

        Args:
            cache_manager: Cache manager for results
            blacklist_manager: Blacklist manager for failed sources
            normalizer: Normalizer for converting raw results
            preferences: Search preferences (uses defaults if None)
        """
        self.cache_manager = cache_manager
        self.blacklist_manager = blacklist_manager
        self.normalizer = normalizer
        self.preferences = preferences or SearchPreferences()
        self.logger = structlog.get_logger("comicarr.search.service")

    async def search(
        self,
        session: SQLModelAsyncSession,
        title: str | None = None,
        issue_number: str | None = None,
        year: int | None = None,
        volume_id: str | None = None,
        issue_id: str | None = None,
        wanted_issues: list[LibraryIssue] | None = None,
    ) -> list[SearchResult]:
        """Search across all enabled indexers.

        Args:
            session: Database session
            title: Series/volume title
            issue_number: Issue number
            year: Publication year
            volume_id: Volume ID (for volume health calculation)
            issue_id: Issue ID (for volume health calculation)
            wanted_issues: List of wanted issues (for pack preference calculation)

        Returns:
            List of normalized, ranked search results
        """
        # Get enabled indexers
        query = select(Indexer).where(Indexer.enabled == True)
        result = await session.exec(query)
        indexers = result.all()

        if not indexers:
            self.logger.warning("No enabled indexers found")
            return []

        # Build search query
        search_query = self._build_search_query(title, issue_number, year)

        # Search all indexers in parallel
        all_results: list[SearchResult] = []

        for indexer in indexers:
            try:
                # Check cache first
                cached_results = await self.cache_manager.get_indexer_results(
                    indexer.id, search_query
                )

                if cached_results:
                    self.logger.debug("Using cached results", indexer_id=indexer.id)
                    raw_results = cached_results
                else:
                    # Create indexer client
                    client = self._create_indexer_client(indexer)

                    # Perform search
                    raw_results = await client.search(
                        query=search_query,
                        title=title,
                        issue_number=issue_number,
                        year=year,
                        categories=indexer.config.get("categories", []),
                    )

                    # Cache results
                    await self.cache_manager.store_indexer_results(
                        indexer.id,
                        search_query,
                        raw_results,
                    )

                # Normalize results
                for raw_result in raw_results:
                    # Skip blacklisted results
                    guid = raw_result.get("guid", raw_result.get("link", ""))
                    if (
                        guid
                        and isinstance(guid, str)
                        and self.blacklist_manager.is_blacklisted(indexer.id, guid)
                    ):
                        continue

                    normalized = self.normalizer.normalize(raw_result, indexer)
                    all_results.append(normalized)

            except Exception as e:
                self.logger.error(
                    "Indexer search failed",
                    indexer_id=indexer.id,
                    error=str(e),
                )
                continue

        # Rank results
        ranked_results = self._rank_results(
            all_results,
            volume_id,
            wanted_issues,
        )

        self.logger.info(
            "Search completed",
            total_results=len(ranked_results),
            indexers_searched=len(indexers),
        )

        return ranked_results

    def _create_indexer_client(self, indexer: Indexer) -> IndexerClient:
        """Create an indexer client from an Indexer model.

        Args:
            indexer: Indexer model

        Returns:
            IndexerClient instance
        """
        config = indexer.config

        if indexer.type == "newznab":
            return NewznabClient(
                name=indexer.name,
                url=config.get("url", ""),
                api_key=config.get("api_key"),
                api_path=config.get("api_path", "/api"),
            )
        elif indexer.type == "torrent":
            return TorznabClient(
                name=indexer.name,
                url=config.get("url", ""),
                api_key=config.get("api_key"),
                api_path=config.get("api_path", "/api"),
            )
        elif indexer.type == "builtin_http":
            if indexer.id == "getcomics":
                return GetComicsIndexer(
                    name=indexer.name,
                    base_url=config.get("base_url", "https://getcomics.info"),
                )
            elif indexer.id == "readcomicsonline":
                return ReadComicsOnlineIndexer(
                    name=indexer.name,
                    base_url=config.get("base_url", "https://readcomicsonline.ru"),
                )

        raise ValueError(f"Unknown indexer type: {indexer.type}")

    def _build_search_query(
        self,
        title: str | None,
        issue_number: str | None,
        year: int | None,
    ) -> str:
        """Build search query from components.

        Args:
            title: Series/volume title
            issue_number: Issue number
            year: Publication year

        Returns:
            Search query string
        """
        terms: list[str] = []
        if title:
            terms.append(title)
        if issue_number:
            terms.append(f"#{issue_number}")
        if year:
            terms.append(str(year))
        return " ".join(terms)

    def _rank_results(
        self,
        results: list[SearchResult],
        volume_id: str | None = None,
        wanted_issues: list[LibraryIssue] | None = None,
    ) -> list[SearchResult]:
        """Rank search results based on preferences.

        Args:
            results: List of search results to rank
            volume_id: Volume ID (for volume health calculation)
            wanted_issues: List of wanted issues (for pack preference)

        Returns:
            Ranked list of results (best first)
        """
        # Calculate score for each result
        scored_results: list[tuple[SearchResult, float]] = []

        for result in results:
            score = self._calculate_score(result, volume_id, wanted_issues)
            scored_results.append((result, score))

        # Sort by score (descending)
        scored_results.sort(key=lambda x: x[1], reverse=True)

        # Return just the results (without scores)
        return [result for result, _ in scored_results]

    def _calculate_score(
        self,
        result: SearchResult,
        volume_id: str | None = None,
        wanted_issues: list[LibraryIssue] | None = None,
    ) -> float:
        """Calculate ranking score for a result.

        Args:
            result: Search result to score
            volume_id: Volume ID (for volume health)
            wanted_issues: List of wanted issues

        Returns:
            Ranking score (higher = better)
        """
        base_score = 100.0

        # Indexer priority (lower priority number = higher priority)
        # We'll need to get this from the indexer, but for now use a default
        indexer_priority = 0  # TODO: Get from indexer model
        base_score -= indexer_priority * self.preferences.indexer_priority_weight

        # Source type preference
        if self.preferences.prefer_source_type != "none":
            if result.source_type == self.preferences.prefer_source_type:
                base_score += 10.0

        # Volume pack handling
        if result.is_volume_pack:
            if self.preferences.prefer_volume_packs == "never":
                base_score *= 0.1  # Heavily penalize
            elif self.preferences.prefer_volume_packs == "always":
                base_score *= 1.5  # Boost
            elif self.preferences.prefer_volume_packs == "when_multiple":
                if wanted_issues and len(wanted_issues) > 1:
                    base_score *= 1.3  # Moderate boost
            elif self.preferences.prefer_volume_packs == "if_missing_threshold":
                # TODO: Calculate coverage percentage when volume/issue models exist
                # For now, use a default boost
                base_score *= 1.2

        # Size preference (larger files might be better quality)
        if result.size:
            # Normalize size to 0-1 range (assuming max 500MB)
            size_score = min(result.size / (500 * 1024 * 1024), 1.0)
            base_score += size_score * 5.0

        # Date preference (newer is better)
        if result.pub_date:
            # TODO: Calculate age and boost recent results
            pass

        return base_score
