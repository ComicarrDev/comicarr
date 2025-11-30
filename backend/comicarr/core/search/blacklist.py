"""Blacklist manager for tracking failed download sources."""

from __future__ import annotations

import time

import structlog

logger = structlog.get_logger("comicarr.search.blacklist")


class BlacklistManager:
    """Manages blacklist of failed download sources."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        """Initialize blacklist manager.

        Args:
            ttl_seconds: Time-to-live for blacklist entries in seconds (default: 1 hour)
        """
        self.ttl_seconds = ttl_seconds
        self.blacklist: dict[str, float] = {}  # key -> timestamp
        self.logger = structlog.get_logger("comicarr.search.blacklist")

    def add(self, indexer_id: str, guid: str) -> None:
        """Add an entry to the blacklist.

        Args:
            indexer_id: ID of the indexer
            guid: GUID of the failed result
        """
        key = f"{indexer_id}:{guid}"
        self.blacklist[key] = time.time()
        self.logger.debug("Added to blacklist", indexer_id=indexer_id, guid=guid[:50])

    def is_blacklisted(self, indexer_id: str, guid: str) -> bool:
        """Check if an entry is blacklisted.

        Args:
            indexer_id: ID of the indexer
            guid: GUID of the result

        Returns:
            True if blacklisted, False otherwise
        """
        key = f"{indexer_id}:{guid}"

        if key not in self.blacklist:
            return False

        # Check if entry has expired
        if time.time() - self.blacklist[key] > self.ttl_seconds:
            # Entry expired, remove it
            del self.blacklist[key]
            return False

        return True

    def remove(self, indexer_id: str, guid: str) -> None:
        """Remove an entry from the blacklist.

        Args:
            indexer_id: ID of the indexer
            guid: GUID of the result
        """
        key = f"{indexer_id}:{guid}"
        if key in self.blacklist:
            del self.blacklist[key]
            self.logger.debug("Removed from blacklist", indexer_id=indexer_id, guid=guid[:50])

    def clear_expired(self) -> None:
        """Remove expired entries from the blacklist."""
        current_time = time.time()
        expired_keys = [
            key
            for key, timestamp in self.blacklist.items()
            if current_time - timestamp > self.ttl_seconds
        ]
        for key in expired_keys:
            del self.blacklist[key]

        if expired_keys:
            self.logger.debug("Cleared expired blacklist entries", count=len(expired_keys))

    def clear_all(self) -> None:
        """Clear all blacklist entries."""
        count = len(self.blacklist)
        self.blacklist.clear()
        self.logger.debug("Cleared all blacklist entries", count=count)
