"""GetComics download client for resolving redirects and downloading files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import structlog

from comicarr.core.clients.base import DownloadClient

logger = structlog.get_logger("comicarr.clients.getcomics")


class GetComicsDownloadClient(DownloadClient):
    """Download client for GetComics redirect links."""

    def __init__(
        self,
        name: str = "GetComics",
        timeout: int = 300,  # Longer timeout for downloads
    ) -> None:
        """Initialize GetComics download client.

        Args:
            name: Name of the client (for logging)
            timeout: Request timeout in seconds
        """
        super().__init__(name)
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(timeout), follow_redirects=True)

    async def __aenter__(self) -> GetComicsDownloadClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.client.aclose()

    async def resolve_redirect(self, url: str) -> str:
        """Resolve GetComics redirect to final download URL.

        Args:
            url: GetComics redirect URL

        Returns:
            Final download URL after following redirects
        """
        try:
            self.logger.debug("Resolving GetComics redirect", url=url)
            response = await self.client.get(url, follow_redirects=True)
            # The final URL after redirects
            final_url = str(response.url)
            self.logger.debug("Resolved redirect", original=url, final=final_url)
            return final_url
        except Exception as e:
            self.logger.error("Failed to resolve redirect", url=url, error=str(e))
            raise

    async def download(
        self,
        url: str,
        destination: Path,
        **kwargs: Any,
    ) -> Path:
        """Download a file from GetComics redirect URL.

        Args:
            url: GetComics redirect URL (will be resolved to final URL)
            destination: Destination path for the downloaded file
            **kwargs: Additional parameters (ignored for now)

        Returns:
            Path to the downloaded file
        """
        # Resolve redirect first
        final_url = await self.resolve_redirect(url)

        try:
            self.logger.info("Downloading file", url=final_url, destination=str(destination))

            # Ensure destination directory exists
            destination.parent.mkdir(parents=True, exist_ok=True)

            # Download file
            async with self.client.stream("GET", final_url) as response:
                response.raise_for_status()

                # Determine filename from Content-Disposition or URL
                filename = self._get_filename(response, final_url)
                if not destination.suffix and filename:
                    destination = destination.parent / filename

                # Write file
                with destination.open("wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)

            self.logger.info("Download completed", destination=str(destination))
            return destination

        except Exception as e:
            self.logger.error("Download failed", url=final_url, error=str(e))
            raise

    def _get_filename(self, response: httpx.Response, url: str) -> str | None:
        """Extract filename from response headers or URL.

        Args:
            response: HTTP response
            url: Original URL

        Returns:
            Filename if found, None otherwise
        """
        # Try Content-Disposition header
        content_disposition = response.headers.get("Content-Disposition", "")
        if content_disposition:
            import re

            match = re.search(r'filename="?([^";]+)"?', content_disposition)
            if match:
                return match.group(1)

        # Fall back to URL
        from urllib.parse import urlparse

        parsed = urlparse(url)
        filename = Path(parsed.path).name
        if filename:
            return filename

        return None
