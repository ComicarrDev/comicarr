"""Indexer clients for searching content across different sources."""

from comicarr.core.indexers.base import IndexerClient
from comicarr.core.indexers.getcomics import GetComicsIndexer
from comicarr.core.indexers.newznab import NewznabClient
from comicarr.core.indexers.readcomicsonline import ReadComicsOnlineIndexer
from comicarr.core.indexers.torznab import TorznabClient

# Built-in indexer definitions
BUILTIN_INDEXERS = [
    {
        "id": "getcomics",
        "name": "GetComics",
        "type": "builtin_http",
        "is_builtin": True,
        "enabled": True,
        "priority": 0,
        "config": {
            "base_url": "https://getcomics.info",
            "rate_limit": 10,  # requests per period
            "rate_limit_period": 60,  # seconds
        },
        "enable_rss": True,
        "enable_automatic_search": True,
        "enable_interactive_search": True,
        "tags": [],
    },
    {
        "id": "readcomicsonline",
        "name": "ReadComicsOnline",
        "type": "builtin_http",
        "is_builtin": True,
        "enabled": True,
        "priority": 1,
        "config": {
            "base_url": "https://readcomicsonline.ru",
            "rate_limit": 10,
            "rate_limit_period": 60,
        },
        "enable_rss": True,
        "enable_automatic_search": True,
        "enable_interactive_search": True,
        "tags": [],
    },
]

__all__ = [
    "IndexerClient",
    "NewznabClient",
    "TorznabClient",
    "GetComicsIndexer",
    "ReadComicsOnlineIndexer",
    "BUILTIN_INDEXERS",
]
