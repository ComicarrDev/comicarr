"""Newznab-compatible indexer client."""

from __future__ import annotations

from typing import Any
from urllib import parse as urllib_parse
from xml.etree import ElementTree as ET

import httpx
import structlog

from comicarr.core.indexers.base import IndexerClient

logger = structlog.get_logger("comicarr.indexers.newznab")


class NewznabClient(IndexerClient):
    """Client for interacting with Newznab-compatible indexers."""

    def __init__(
        self,
        name: str,
        url: str,
        api_key: str | None = None,
        api_path: str = "/api",
        timeout: int = 30,
    ) -> None:
        """Initialize the Newznab client.

        Args:
            name: Name of the indexer (for logging)
            url: Base URL of the indexer (e.g., https://api.nzbgeek.info)
            api_key: API key for the indexer
            api_path: Path to the API endpoint (default: "/api")
            timeout: Request timeout in seconds
        """
        super().__init__(name)
        self.base_url = url.rstrip("/")
        self.api_path = api_path.strip("/") or "api"
        self.api_key = api_key
        self.timeout = timeout
        # Follow redirects (e.g., Prowlarr may redirect /1/api to /prowlarr/1/api)
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(timeout), follow_redirects=True)

    async def __aenter__(self) -> NewznabClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.client.aclose()

    def _build_url(self, params: dict[str, Any]) -> str:
        """Build a Newznab API URL."""
        all_params = params.copy()
        if self.api_key:
            all_params["apikey"] = self.api_key
        all_params["t"] = params.get("t", "search")  # Default to search if not specified

        # Construct URL: base_url/api_path
        api_path = self.api_path.strip("/")
        if not api_path:
            api_path = "api"
        base = self.base_url.rstrip("/")
        return f"{base}/{api_path}?{urllib_parse.urlencode(all_params)}"

    def _xml_to_dict(self, root: ET.Element) -> dict[str, Any]:
        """Convert XML Element to dictionary recursively."""
        result: dict[str, Any] = {}

        # Handle text content
        if root.text and root.text.strip():
            if len(root) == 0:  # Leaf node
                return {"#text": root.text.strip()}
            result["#text"] = root.text.strip()

        # Handle attributes
        if root.attrib:
            result.update(root.attrib)

        # Handle child elements
        children: dict[str, Any] = {}
        for child in root:
            child_tag = child.tag
            child_data = self._xml_to_dict(child)

            if child_tag in children:
                # Multiple children with same tag - convert to list
                if not isinstance(children[child_tag], list):
                    children[child_tag] = [children[child_tag]]
                children[child_tag].append(child_data)
            else:
                children[child_tag] = child_data

        if children:
            result.update(children)

        # If we have attributes or text, return the dict, otherwise return just the children
        if root.attrib or (root.text and root.text.strip()) or not children:
            return result if result else {}
        else:
            return children if children else {}

    async def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Make a GET request to the Newznab API."""
        url = self._build_url(params)
        # Mask API key in logged URL
        log_url = url.split("apikey=")[0] + "apikey=***" if "apikey=" in url else url

        try:
            self.logger.debug("Making Newznab API request", indexer=self.name, url=log_url)
            response = await self.client.get(url)
            response.raise_for_status()

            # Check if response has content
            if not response.content:
                raise ValueError(f"Empty response from indexer (status: {response.status_code})")

            # Check content type
            content_type = response.headers.get("content-type", "").lower()

            # Newznab APIs return XML (RSS/Atom format), try XML parsing first
            if (
                "xml" in content_type
                or not content_type
                or response.text.strip().startswith("<?xml")
                or response.text.strip().startswith("<")
            ):
                try:
                    root = ET.fromstring(response.text)
                    result = {root.tag: self._xml_to_dict(root)}
                    self.logger.debug(
                        "Parsed XML response successfully", indexer=self.name, root_tag=root.tag
                    )
                    return result
                except ET.ParseError as xml_error:
                    self.logger.error(
                        "Failed to parse XML response",
                        indexer=self.name,
                        xml_error=str(xml_error),
                    )
                    # Fall through to try JSON

            # Try JSON as fallback (some indexers may return JSON)
            if "json" in content_type:
                try:
                    return response.json()
                except Exception as json_error:
                    raise ValueError(
                        f"Invalid JSON response (status: {response.status_code})"
                    ) from json_error
            else:
                raise ValueError(
                    f"Unexpected content type: {content_type} (status: {response.status_code})"
                )

        except httpx.HTTPStatusError as e:
            self.logger.error(
                "Newznab API HTTP error",
                indexer=self.name,
                status_code=e.response.status_code,
            )
            raise ValueError(f"HTTP {e.response.status_code} error") from e
        except httpx.ConnectError as e:
            self.logger.error("Newznab API connection error", indexer=self.name, error=str(e))
            raise ValueError(f"Failed to connect to indexer: {str(e)}") from e
        except Exception as e:
            self.logger.error("Unexpected error in _get", indexer=self.name, error=str(e))
            raise ValueError(f"Unexpected error: {str(e)}") from e

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
            List of search results, each containing:
            - title: Result title
            - link: URL to NZB file
            - guid: Unique identifier
            - pubDate: Publication date
            - size: File size in bytes
            - description: Description text
        """
        params: dict[str, Any] = {"t": "search", "limit": max_results}

        # Build search query
        search_terms: list[str] = []
        if query:
            search_terms.append(query)
        if title:
            search_terms.append(title)
        if issue_number:
            # Add issue number with # prefix for better matching
            search_terms.append(f"#{issue_number}")
        if year:
            search_terms.append(str(year))

        if search_terms:
            params["q"] = " ".join(search_terms)

        # Category filter (default to comics category 7030 if not specified)
        if categories:
            params["cat"] = ",".join(str(cat) for cat in categories)
        else:
            params["cat"] = "7030"  # Default to comics category

        try:
            response = await self._get(params)
            items = response.get("channel", {}).get("item", [])
            if not isinstance(items, list):
                items = [items] if items else []

            results = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                results.append(
                    {
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "guid": (
                            item.get("guid", {}).get("#text", "")
                            if isinstance(item.get("guid"), dict)
                            else item.get("guid", "")
                        ),
                        "pubDate": item.get("pubDate", ""),
                        "size": int(item.get("size", 0)) if item.get("size") else 0,
                        "description": item.get("description", ""),
                    }
                )

            self.logger.info(
                "Newznab search completed",
                indexer=self.name,
                query=params.get("q", ""),
                results_count=len(results),
            )
            return results
        except Exception as e:
            self.logger.error("Newznab search failed", indexer=self.name, error=str(e))
            return []

    async def test_connection(self) -> bool:
        """Test the connection to the indexer.

        Returns:
            True if connection is successful, False otherwise
        """
        # Use caps endpoint to test connection
        params = {"t": "caps"}
        try:
            response = await self._get(params)
            # If we get a valid response, connection is good
            if isinstance(response, dict):
                if "server" in response or "categories" in response or "channel" in response:
                    return True
            raise ValueError("Unexpected response format from indexer")
        except Exception as e:
            self.logger.error("Connection test failed", indexer=self.name, error=str(e))
            return False
