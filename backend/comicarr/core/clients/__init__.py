"""Download clients for downloading files from various sources."""

from comicarr.core.clients.base import DownloadClient
from comicarr.core.clients.getcomics import GetComicsDownloadClient
from comicarr.core.clients.readcomicsonline import ReadComicsOnlineDownloadClient

__all__ = [
    "DownloadClient",
    "GetComicsDownloadClient",
    "ReadComicsOnlineDownloadClient",
]
