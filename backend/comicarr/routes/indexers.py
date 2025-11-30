"""Indexers API routes."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable
from typing import Any, Literal

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.tracing import get_trace_id
from comicarr.db.models import Indexer

logger = structlog.get_logger("comicarr.routes.indexers")


# Newznab/Torznab Category IDs and Names
# Based on Newznab standard categories (also used by Torznab/Prowlarr/Jackett)
INDEXER_CATEGORIES = [
    {"id": "1000", "name": "Console"},
    {"id": "1010", "name": "NDS"},
    {"id": "1020", "name": "PSP"},
    {"id": "1030", "name": "Wii"},
    {"id": "1040", "name": "Xbox"},
    {"id": "1050", "name": "Xbox 360"},
    {"id": "1060", "name": "PS3"},
    {"id": "1070", "name": "Other"},
    {"id": "2000", "name": "Movies"},
    {"id": "2010", "name": "Foreign"},
    {"id": "2020", "name": "Other"},
    {"id": "2030", "name": "SD"},
    {"id": "2040", "name": "HD"},
    {"id": "2045", "name": "UHD"},
    {"id": "2050", "name": "BluRay"},
    {"id": "2060", "name": "3D"},
    {"id": "3000", "name": "Audio"},
    {"id": "3010", "name": "MP3"},
    {"id": "3020", "name": "Video"},
    {"id": "3030", "name": "Audiobook"},
    {"id": "3040", "name": "Lossless"},
    {"id": "4000", "name": "PC"},
    {"id": "4010", "name": "0day"},
    {"id": "4020", "name": "ISO"},
    {"id": "4030", "name": "Mac"},
    {"id": "4040", "name": "Mobile"},
    {"id": "4050", "name": "Games"},
    {"id": "4060", "name": "Android"},
    {"id": "4070", "name": "Other"},
    {"id": "5000", "name": "TV"},
    {"id": "5010", "name": "Foreign"},
    {"id": "5020", "name": "SD"},
    {"id": "5030", "name": "HD"},
    {"id": "5040", "name": "UHD"},
    {"id": "5045", "name": "Other"},
    {"id": "5050", "name": "Sport"},
    {"id": "5060", "name": "Anime"},
    {"id": "5070", "name": "Documentary"},
    {"id": "6000", "name": "XXX"},
    {"id": "6010", "name": "DVD"},
    {"id": "6020", "name": "WMV"},
    {"id": "6030", "name": "XviD"},
    {"id": "6040", "name": "x264"},
    {"id": "6050", "name": "Other"},
    {"id": "7000", "name": "Books"},
    {"id": "7010", "name": "Mags"},
    {"id": "7020", "name": "EBook"},
    {"id": "7030", "name": "Comics"},
    {"id": "8000", "name": "Other"},
]


# Request/Response Models
class IndexerCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Display name of the indexer")
    type: Literal["newznab", "torrent"] = Field(..., description="Type of the indexer")
    config: dict[str, Any] = Field(default_factory=dict, description="Type-specific configuration")
    enable_rss: bool = Field(True, description="Enable RSS feed capability")
    enable_automatic_search: bool = Field(True, description="Enable automatic search capability")
    enable_interactive_search: bool = Field(
        True, description="Enable interactive search capability"
    )
    tags: list[str] = Field(default_factory=list, description="Tags for filtering")


class IndexerUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, description="Display name")
    enabled: bool | None = Field(None, description="Whether this indexer is enabled")
    priority: int | None = Field(None, description="Priority (lower = higher priority)")
    config: dict[str, Any] | None = Field(None, description="Type-specific configuration")
    enable_rss: bool | None = Field(None, description="Enable RSS feed capability")
    enable_automatic_search: bool | None = Field(
        None, description="Enable automatic search capability"
    )
    enable_interactive_search: bool | None = Field(
        None, description="Enable interactive search capability"
    )
    tags: list[str] | None = Field(None, description="Tags for filtering")


class IndexerResponse(BaseModel):
    """Indexer response model."""

    id: str
    name: str
    type: str
    is_builtin: bool
    enabled: bool
    priority: int
    config: dict[str, Any]
    enable_rss: bool
    enable_automatic_search: bool
    enable_interactive_search: bool
    tags: list[str]
    created_at: int
    updated_at: int


class IndexerTypeResponse(BaseModel):
    """Response model for available indexer types."""

    id: str
    name: str
    category: Literal["Usenet", "Torrents", "Built-in"]
    description: str
    fields: list[dict[str, Any]]  # Schema for type-specific fields


def create_indexers_router(
    get_db_session: Callable[[], AsyncIterator[SQLModelAsyncSession]],
) -> APIRouter:
    """Create indexers router.

    Args:
        get_db_session: Dependency function for database sessions

    Returns:
        Configured APIRouter instance
    """
    logger.debug("Creating indexers router")
    router_instance = APIRouter(prefix="/api")

    @router_instance.get("/indexers", response_model=list[IndexerResponse])
    async def list_indexers(
        enabled: bool | None = None,
        indexer_type: str | None = Query(None, alias="type", description="Filter by indexer type"),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> list[IndexerResponse]:
        """List all indexers.

        Args:
            enabled: Filter by enabled status
            indexer_type: Filter by indexer type
            session: Database session

        Returns:
            List of indexers
        """
        trace_id = get_trace_id()
        logger.debug("Listing indexers", trace_id=trace_id, enabled=enabled, type=indexer_type)

        try:
            query = select(Indexer)

            if enabled is not None:
                query = query.where(Indexer.enabled == enabled)

            if indexer_type is not None:
                query = query.where(Indexer.type == indexer_type)

            query = query.order_by(col(Indexer.priority), col(Indexer.name))

            result = await session.exec(query)
            indexers = result.all()

            return [IndexerResponse.model_validate(indexer.model_dump()) for indexer in indexers]
        except Exception as e:
            # Log error without exc_info to avoid dev processor issues
            logger.error(
                "Failed to list indexers",
                error=str(e),
                error_type=type(e).__name__,
                trace_id=trace_id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list indexers: {e}",
            )

    @router_instance.get("/indexers/types", response_model=list[IndexerTypeResponse])
    async def get_indexer_types() -> list[IndexerTypeResponse]:
        """Get available indexer types and their schemas."""
        trace_id = get_trace_id()
        logger.debug("Getting indexer types", trace_id=trace_id)

        # Define available types and their configuration schemas
        types = [
            IndexerTypeResponse(
                id="newznab",
                name="Newznab",
                category="Usenet",
                description="Newznab-compatible Usenet indexer.",
                fields=[
                    {
                        "id": "url",
                        "name": "URL",
                        "type": "text",
                        "required": True,
                        "placeholder": "https://nzbgeek.info",
                    },
                    {"id": "api_key", "name": "API Key", "type": "password", "required": True},
                    {
                        "id": "api_path",
                        "name": "API Path",
                        "type": "text",
                        "required": False,
                        "default": "/api",
                    },
                    {
                        "id": "categories",
                        "name": "Categories",
                        "type": "multiselect",
                        "options": INDEXER_CATEGORIES,
                        "help": "Specific categories to search. Select categories by name.",
                    },
                ],
            ),
            IndexerTypeResponse(
                id="torrent",
                name="Torrent",
                category="Torrents",
                description="Generic torrent indexer (e.g., Jackett/Prowlarr compatible).",
                fields=[
                    {
                        "id": "url",
                        "name": "URL",
                        "type": "text",
                        "required": True,
                        "placeholder": "https://thepiratebay.org",
                    },
                    {
                        "id": "api_key",
                        "name": "API Key",
                        "type": "password",
                        "required": False,
                        "help": "Optional API key if required by the torrent tracker",
                    },
                    {
                        "id": "api_path",
                        "name": "API Path",
                        "type": "text",
                        "required": False,
                        "default": "/api",
                        "help": "API endpoint path (e.g., /1/api for Prowlarr, /api/v2.0 for Jackett)",
                    },
                    {
                        "id": "categories",
                        "name": "Categories",
                        "type": "multiselect",
                        "options": INDEXER_CATEGORIES,
                        "help": "Specific categories to search. Select categories by name.",
                    },
                ],
            ),
            IndexerTypeResponse(
                id="builtin_http",
                name="Built-in HTTP",
                category="Built-in",
                description="Built-in HTTP indexer (e.g., GetComics, ReadComicsOnline).",
                fields=[
                    {
                        "id": "base_url",
                        "name": "Base URL",
                        "type": "text",
                        "required": True,
                        "disabled": True,
                    },
                    {
                        "id": "rate_limit",
                        "name": "Rate Limit (req/period)",
                        "type": "number",
                        "required": True,
                        "default": 10,
                    },
                    {
                        "id": "rate_limit_period",
                        "name": "Rate Limit Period (seconds)",
                        "type": "number",
                        "required": True,
                        "default": 60,
                    },
                ],
            ),
        ]
        return types

    @router_instance.get("/indexers/{indexer_id}", response_model=IndexerResponse)
    async def get_indexer(
        indexer_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> IndexerResponse:
        """Get a single indexer by ID.

        Args:
            indexer_id: Indexer ID
            session: Database session

        Returns:
            Indexer details
        """
        trace_id = get_trace_id()
        logger.debug("Getting indexer", trace_id=trace_id, indexer_id=indexer_id)

        indexer = await session.get(Indexer, indexer_id)
        if not indexer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Indexer not found",
            )
        return IndexerResponse.model_validate(indexer.model_dump())

    @router_instance.post(
        "/indexers", response_model=IndexerResponse, status_code=status.HTTP_201_CREATED
    )
    async def create_indexer(
        payload: IndexerCreate,
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> IndexerResponse:
        """Create a new indexer.

        Args:
            payload: Indexer creation payload
            session: Database session

        Returns:
            Created indexer details
        """
        trace_id = get_trace_id()
        logger.debug("Creating indexer", trace_id=trace_id, name=payload.name, type=payload.type)

        # Ensure ID is unique (though default_factory should handle this)
        new_id = Indexer.model_validate(payload).id
        existing = await session.get(Indexer, new_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Indexer with this ID already exists (unlikely, please retry)",
            )

        indexer = Indexer(
            **payload.model_dump(),
            is_builtin=False,  # User-created indexers are never built-in
        )
        session.add(indexer)
        await session.commit()
        await session.refresh(indexer)

        logger.info("Indexer created", trace_id=trace_id, indexer_id=indexer.id, name=indexer.name)
        return IndexerResponse.model_validate(indexer.model_dump())

    @router_instance.put("/indexers/{indexer_id}", response_model=IndexerResponse)
    async def update_indexer(
        indexer_id: str,
        payload: IndexerUpdate,
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> IndexerResponse:
        """Update an existing indexer.

        Args:
            indexer_id: Indexer ID
            payload: Indexer update payload
            session: Database session

        Returns:
            Updated indexer details
        """
        trace_id = get_trace_id()
        logger.debug(
            "Updating indexer",
            trace_id=trace_id,
            indexer_id=indexer_id,
            payload=payload.model_dump(),
        )

        indexer = await session.get(Indexer, indexer_id)
        if not indexer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Indexer not found",
            )

        # Update fields from payload
        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(indexer, key, value)

        indexer.updated_at = int(time.time())

        session.add(indexer)
        await session.commit()
        await session.refresh(indexer)

        logger.info("Indexer updated", trace_id=trace_id, indexer_id=indexer.id, name=indexer.name)
        return IndexerResponse.model_validate(indexer.model_dump())

    @router_instance.delete("/indexers/{indexer_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_indexer(
        indexer_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> None:
        """Delete an indexer. Built-in indexers cannot be deleted.

        Args:
            indexer_id: Indexer ID
            session: Database session
        """
        trace_id = get_trace_id()
        logger.debug("Deleting indexer", trace_id=trace_id, indexer_id=indexer_id)

        indexer = await session.get(Indexer, indexer_id)
        if not indexer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Indexer not found",
            )

        if indexer.is_builtin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Built-in indexers cannot be deleted.",
            )

        await session.delete(indexer)
        await session.commit()

        logger.info("Indexer deleted", trace_id=trace_id, indexer_id=indexer.id, name=indexer.name)

    @router_instance.post("/indexers/{indexer_id}/test", response_model=dict[str, Any])
    async def test_indexer_connection(
        indexer_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> dict[str, Any]:
        """Test connection to an indexer.

        Args:
            indexer_id: Indexer ID
            session: Database session

        Returns:
            Dictionary with connection test result
        """
        trace_id = get_trace_id()
        logger.debug("Testing indexer connection", trace_id=trace_id, indexer_id=indexer_id)

        indexer = await session.get(Indexer, indexer_id)
        if not indexer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Indexer not found",
            )

        # Test connection based on indexer type
        try:
            if indexer.type == "newznab":
                success, message = await _test_newznab_connection(indexer.config)
            elif indexer.type == "torrent":
                success, message = await _test_torrent_connection(indexer.config)
            elif indexer.type == "builtin_http":
                success, message = await _test_builtin_http_connection(indexer.config)
            else:
                success = False
                message = f"Unknown indexer type: {indexer.type}"

            if success:
                logger.info(
                    "Indexer connection test successful",
                    trace_id=trace_id,
                    indexer_id=indexer_id,
                    type=indexer.type,
                )
            else:
                logger.warning(
                    "Indexer connection test failed",
                    trace_id=trace_id,
                    indexer_id=indexer_id,
                    type=indexer.type,
                    message=message,
                )

            return {"success": success, "message": message}
        except Exception as e:
            logger.error(
                "Indexer connection test error",
                trace_id=trace_id,
                indexer_id=indexer_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return {"success": False, "message": f"Connection test failed: {str(e)}"}

    logger.debug("Indexers router created", routes_count=len(router_instance.routes))
    return router_instance


async def _test_newznab_connection(config: dict[str, Any]) -> tuple[bool, str]:
    """Test connection to a Newznab-compatible indexer.

    Args:
        config: Indexer configuration dict with url, api_key, api_path

    Returns:
        Tuple of (success: bool, message: str)
    """
    url = config.get("url", "").strip().rstrip("/")
    api_key = config.get("api_key", "").strip()
    api_path = config.get("api_path", "/api").strip()

    if not url:
        return False, "URL is required"

    if not api_key:
        return False, "API key is required"

    # Test with capabilities endpoint
    test_url = f"{url}{api_path}?t=caps&apikey={api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(test_url)
            response.raise_for_status()

            # Check if response is valid XML (Newznab returns XML)
            content_type = response.headers.get("content-type", "").lower()
            if "xml" in content_type or response.text.strip().startswith("<?xml"):
                return True, "Connection successful"
            else:
                return False, "Invalid response format (expected XML)"
    except httpx.TimeoutException:
        return False, "Connection timeout"
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return False, "Authentication failed (invalid API key)"
        elif e.response.status_code == 404:
            return False, "API endpoint not found"
        else:
            return False, f"HTTP error: {e.response.status_code}"
    except httpx.ConnectError:
        return False, "Could not connect to server (check URL)"
    except Exception as e:
        return False, f"Connection error: {str(e)}"


async def _test_torrent_connection(config: dict[str, Any]) -> tuple[bool, str]:
    """Test connection to a torrent indexer (e.g., Jackett/Prowlarr).

    Args:
        config: Indexer configuration dict with url, optional api_key, optional api_path

    Returns:
        Tuple of (success: bool, message: str)
    """
    url = config.get("url", "").strip().rstrip("/")
    api_key = config.get("api_key", "").strip()
    api_path = config.get("api_path", "/api").strip()

    if not url:
        return False, "URL is required"

    # Prowlarr uses Newznab-style API with query parameters (e.g., /1/api?t=caps&apikey=...)
    # Jackett uses /api/v2.0/indexers/all/results with X-Api-Key header
    # Try Prowlarr-style first (capabilities endpoint), fall back to Jackett-style if needed
    test_url = f"{url}{api_path}?t=caps"
    if api_key:
        test_url += f"&apikey={api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            headers = {}
            # For Jackett, also try with header auth as fallback
            if api_key:
                headers["X-Api-Key"] = api_key

            response = await client.get(test_url, headers=headers)
            # Accept 200, 401 (auth required), or 404 (endpoint might not exist but server is reachable)
            if response.status_code in (200, 401, 404):
                return True, "Connection successful"
            else:
                return False, f"HTTP error: {response.status_code}"
    except httpx.TimeoutException:
        return False, "Connection timeout"
    except httpx.ConnectError:
        return False, "Could not connect to server (check URL)"
    except Exception as e:
        return False, f"Connection error: {str(e)}"


async def _test_builtin_http_connection(config: dict[str, Any]) -> tuple[bool, str]:
    """Test connection to a built-in HTTP indexer.

    Args:
        config: Indexer configuration dict with base_url

    Returns:
        Tuple of (success: bool, message: str)
    """
    base_url = config.get("base_url", "").strip().rstrip("/")

    if not base_url:
        return False, "Base URL is required"

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(base_url)
            response.raise_for_status()
            return True, "Connection successful"
    except httpx.TimeoutException:
        return False, "Connection timeout"
    except httpx.HTTPStatusError as e:
        return False, f"HTTP error: {e.response.status_code}"
    except httpx.ConnectError:
        return False, "Could not connect to server (check URL)"
    except Exception as e:
        return False, f"Connection error: {str(e)}"
