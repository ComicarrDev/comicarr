"""Search module for orchestrating searches across indexers."""

from comicarr.core.search.blacklist import BlacklistManager
from comicarr.core.search.cache import CacheManager
from comicarr.core.search.models import DownloadLink, SearchPreferences, SearchResult
from comicarr.core.search.normalizer import SearchResultNormalizer
from comicarr.core.search.service import SearchService

__all__ = [
    "BlacklistManager",
    "CacheManager",
    "DownloadLink",
    "SearchPreferences",
    "SearchResult",
    "SearchResultNormalizer",
    "SearchService",
]
