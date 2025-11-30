"""Cache manager for search results and metadata."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger("comicarr.search.cache")


class CacheManager:
    """Manages caching for search results and metadata."""

    def __init__(
        self,
        cache_dir: Path,
        indexer_results_ttl: int = 3600,  # 1 hour
        comicvine_ttl: int = 86400 * 7,  # 7 days
        downloaded_files_ttl: int = 0,  # Permanent (0 = no expiration)
    ) -> None:
        """Initialize cache manager.

        Args:
            cache_dir: Directory for cache files
            indexer_results_ttl: TTL for indexer search results in seconds
            comicvine_ttl: TTL for ComicVine metadata in seconds
            downloaded_files_ttl: TTL for downloaded file cache (0 = permanent)
        """
        self.cache_dir = cache_dir
        self.indexer_results_ttl = indexer_results_ttl
        self.comicvine_ttl = comicvine_ttl
        self.downloaded_files_ttl = downloaded_files_ttl

        # Create cache subdirectories
        (cache_dir / "indexer_results").mkdir(parents=True, exist_ok=True)
        (cache_dir / "comicvine").mkdir(parents=True, exist_ok=True)
        (cache_dir / "downloaded_files").mkdir(parents=True, exist_ok=True)

        self.logger = structlog.get_logger("comicarr.search.cache")

    def _get_cache_key(self, prefix: str, key: str) -> str:
        """Generate cache key hash.

        Args:
            prefix: Cache prefix (e.g., "indexer_results")
            key: Cache key

        Returns:
            Hashed cache key
        """
        key_str = f"{prefix}:{key}"
        return hashlib.sha256(key_str.encode()).hexdigest()

    def _get_cache_path(self, prefix: str, key: str) -> Path:
        """Get cache file path.

        Args:
            prefix: Cache prefix
            key: Cache key

        Returns:
            Path to cache file
        """
        cache_key = self._get_cache_key(prefix, key)
        return self.cache_dir / prefix / f"{cache_key}.json"

    async def get_indexer_results(self, indexer_id: str, query: str) -> list[dict[str, Any]] | None:
        """Get cached indexer search results.

        Args:
            indexer_id: ID of the indexer
            query: Search query

        Returns:
            Cached results or None if not found/expired
        """
        cache_key = f"{indexer_id}:{query}"
        cache_path = self._get_cache_path("indexer_results", cache_key)

        if not cache_path.exists():
            return None

        try:
            # Check if expired
            if time.time() - cache_path.stat().st_mtime > self.indexer_results_ttl:
                cache_path.unlink()
                return None

            with cache_path.open("r") as f:
                data = json.load(f)
                self.logger.debug("Cache hit", indexer_id=indexer_id, query=query[:50])
                return data.get("results", [])
        except Exception as e:
            self.logger.warning("Failed to read cache", error=str(e))
            return None

    async def store_indexer_results(
        self,
        indexer_id: str,
        query: str,
        results: list[dict[str, Any]],
    ) -> None:
        """Store indexer search results in cache.

        Args:
            indexer_id: ID of the indexer
            query: Search query
            results: Search results to cache
        """
        cache_key = f"{indexer_id}:{query}"
        cache_path = self._get_cache_path("indexer_results", cache_key)

        try:
            with cache_path.open("w") as f:
                json.dump({"results": results, "timestamp": time.time()}, f)
            self.logger.debug(
                "Cached results", indexer_id=indexer_id, query=query[:50], count=len(results)
            )
        except Exception as e:
            self.logger.warning("Failed to write cache", error=str(e))

    async def get_comicvine_metadata(self, comicvine_id: str) -> dict[str, Any] | None:
        """Get cached ComicVine metadata.

        Args:
            comicvine_id: ComicVine ID (e.g., "4050-91273")

        Returns:
            Cached metadata or None if not found/expired
        """
        cache_path = self._get_cache_path("comicvine", comicvine_id)

        if not cache_path.exists():
            return None

        try:
            # Check if expired
            if time.time() - cache_path.stat().st_mtime > self.comicvine_ttl:
                cache_path.unlink()
                return None

            with cache_path.open("r") as f:
                data = json.load(f)
                self.logger.debug("ComicVine cache hit", comicvine_id=comicvine_id)
                return data
        except Exception as e:
            self.logger.warning("Failed to read ComicVine cache", error=str(e))
            return None

    async def store_comicvine_metadata(
        self,
        comicvine_id: str,
        metadata: dict[str, Any],
    ) -> None:
        """Store ComicVine metadata in cache.

        Args:
            comicvine_id: ComicVine ID
            metadata: Metadata to cache
        """
        cache_path = self._get_cache_path("comicvine", comicvine_id)

        try:
            with cache_path.open("w") as f:
                json.dump(metadata, f)
            self.logger.debug("Cached ComicVine metadata", comicvine_id=comicvine_id)
        except Exception as e:
            self.logger.warning("Failed to write ComicVine cache", error=str(e))

    def is_file_cached(self, indexer_id: str, guid: str) -> bool:
        """Check if a file is in the download cache.

        Args:
            indexer_id: ID of the indexer
            guid: GUID of the result

        Returns:
            True if cached, False otherwise
        """
        cache_key = f"{indexer_id}:{guid}"
        cache_path = self._get_cache_path("downloaded_files", cache_key)

        if not cache_path.exists():
            return False

        # If TTL is 0, cache is permanent
        if self.downloaded_files_ttl == 0:
            return True

        # Check if expired
        if time.time() - cache_path.stat().st_mtime > self.downloaded_files_ttl:
            cache_path.unlink()
            return False

        return True

    def mark_file_cached(self, indexer_id: str, guid: str) -> None:
        """Mark a file as cached.

        Args:
            indexer_id: ID of the indexer
            guid: GUID of the result
        """
        cache_key = f"{indexer_id}:{guid}"
        cache_path = self._get_cache_path("downloaded_files", cache_key)

        try:
            cache_path.write_text(json.dumps({"cached": True, "timestamp": time.time()}))
            self.logger.debug("Marked file as cached", indexer_id=indexer_id, guid=guid[:50])
        except Exception as e:
            self.logger.warning("Failed to mark file as cached", error=str(e))

    async def get_comicvine_search(
        self,
        resource_type: str,  # "issue" or "volume"
        query: str,
        limit: int,
    ) -> dict[str, Any] | None:
        """Get cached ComicVine search results.

        Args:
            resource_type: Resource type ("issue" or "volume")
            query: Search query
            limit: Search limit

        Returns:
            Cached search results or None if not found/expired
        """
        cache_key = f"{resource_type}:{query}:{limit}"
        cache_path = self._get_cache_path("comicvine", f"search:{cache_key}")

        if not cache_path.exists():
            return None

        try:
            # Check if expired (use same TTL as metadata)
            if time.time() - cache_path.stat().st_mtime > self.comicvine_ttl:
                cache_path.unlink()
                return None

            with cache_path.open("r") as f:
                data = json.load(f)
                self.logger.debug(
                    "ComicVine search cache hit", resource_type=resource_type, query=query[:50]
                )
                return data.get("payload", {})
        except Exception as e:
            self.logger.warning("Failed to read ComicVine search cache", error=str(e))
            return None

    async def store_comicvine_search(
        self,
        resource_type: str,
        query: str,
        limit: int,
        payload: dict[str, Any],
    ) -> None:
        """Store ComicVine search results in cache.

        Args:
            resource_type: Resource type ("issue" or "volume")
            query: Search query
            limit: Search limit
            payload: API response payload to cache
        """
        cache_key = f"{resource_type}:{query}:{limit}"
        cache_path = self._get_cache_path("comicvine", f"search:{cache_key}")

        try:
            with cache_path.open("w") as f:
                json.dump({"payload": payload, "timestamp": time.time()}, f)
            self.logger.debug(
                "Cached ComicVine search",
                resource_type=resource_type,
                query=query[:50],
                limit=limit,
            )
        except Exception as e:
            self.logger.warning("Failed to write ComicVine search cache", error=str(e))
