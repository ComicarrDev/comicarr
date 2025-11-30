"""Base abstract class for download clients."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import structlog


class DownloadClient(ABC):
    """Abstract base class for download clients."""

    def __init__(self, name: str) -> None:
        """Initialize download client.

        Args:
            name: Name of the client (for logging)
        """
        self.name = name
        self.logger = structlog.get_logger(f"comicarr.clients.{name.lower()}")

    @abstractmethod
    async def download(
        self,
        url: str,
        destination: Path,
        **kwargs: Any,
    ) -> Path:
        """Download a file from the given URL.

        Args:
            url: URL to download from
            destination: Destination path for the downloaded file
            **kwargs: Additional client-specific parameters

        Returns:
            Path to the downloaded file
        """
        pass
