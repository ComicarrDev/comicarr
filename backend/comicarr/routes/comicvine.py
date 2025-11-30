"""ComicVine routes for searching volumes."""

from __future__ import annotations

import re
from typing import Any
from urllib import parse as urllib_parse

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from comicarr.core.dependencies import require_auth
from comicarr.routes.settings import _get_external_apis

logger = structlog.get_logger("comicarr.routes.comicvine")


def build_comicvine_url(settings: dict[str, Any], endpoint: str, params: dict[str, Any]) -> str:
    """Build a ComicVine API URL."""
    endpoint_path = endpoint.strip("/")
    base_url = settings["base_url"].rstrip("/")
    url = f"{base_url}/{endpoint_path}/"
    request_params = {"format": "json", **params}
    api_key = settings.get("api_key")
    if api_key:
        request_params["api_key"] = api_key
    query = urllib_parse.urlencode(request_params)
    return f"{url}?{query}"


async def fetch_comicvine(
    settings: dict[str, Any], endpoint: str, params: dict[str, Any]
) -> dict[str, Any]:
    """Fetch data from the ComicVine API using the shared client.

    This function now uses the shared ComicVineClient which provides:
    - Rate limiting
    - Retry logic with exponential backoff
    - Response caching
    """
    from comicarr.core.comicvine.client import get_comicvine_client

    try:
        client = get_comicvine_client(settings)
        return await client.fetch(endpoint, params)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Comicvine request failed: HTTP {e.response.status_code}",
        ) from e
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Comicvine request failed: {str(e)}"
        ) from e


def normalize_comicvine_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate ComicVine settings payload."""
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="comicvine settings must be an object."
        )

    api_key_raw = payload.get("api_key")
    if api_key_raw is not None and not isinstance(api_key_raw, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="API key must be a string."
        )

    base_url_raw = payload.get("base_url", "https://comicvine.gamespot.com/api")
    if not isinstance(base_url_raw, str) or not base_url_raw.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Base URL must be a non-empty string."
        )

    normalized = {
        "api_key": (
            api_key_raw.strip() if isinstance(api_key_raw, str) and api_key_raw.strip() else None
        ),
        "base_url": base_url_raw.strip(),
        "enabled": bool(payload.get("enabled", False)),
    }
    return normalized


async def build_comicvine_volume_result(
    settings: dict[str, Any], volume_data: dict[str, Any]
) -> dict[str, Any]:
    """Build a normalized volume result from ComicVine API data."""
    # Extract publisher info
    publisher = volume_data.get("publisher")
    publisher_name = None
    publisher_country = None
    if isinstance(publisher, dict):
        publisher_name = publisher.get("name")
        publisher_country = publisher.get("location_country") or publisher.get("country")
    elif isinstance(publisher, str):
        publisher_name = publisher

    # Extract language
    language = volume_data.get("language")
    language_name = None
    if isinstance(language, dict):
        language_name = language.get("name")
    elif isinstance(language, str):
        language_name = language

    # Extract image URL
    image = volume_data.get("image")
    image_url = None
    if isinstance(image, dict):
        image_url = image.get("medium_url") or image.get("original_url") or image.get("icon_url")
    elif isinstance(image, str):
        image_url = image

    # Extract volume tag (if available)
    volume_tag = volume_data.get("volume_tag")

    return {
        "id": volume_data.get("id"),
        "name": volume_data.get("name"),
        "start_year": volume_data.get("start_year"),
        "publisher": publisher_name,
        "publisher_country": publisher_country,
        "description": volume_data.get("description") or volume_data.get("deck"),
        "site_url": volume_data.get("site_detail_url"),
        "image": image_url,
        "count_of_issues": volume_data.get("count_of_issues"),
        "language": language_name,
        "volume_tag": volume_tag,
    }


def create_comicvine_router() -> APIRouter:
    """Create ComicVine router.

    Returns:
        Configured APIRouter instance
    """
    router = APIRouter(prefix="/api", tags=["comicvine"])

    @router.get("/comicvine/volumes/search")
    async def search_comicvine_volumes(
        query: str = Query(..., description="Search query or ComicVine volume ID"),
        limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
        page: int = Query(1, ge=1, description="Page number"),
        _: bool = Depends(require_auth),
    ) -> dict[str, Any]:
        """Search ComicVine for volumes.

        Supports both ID lookup (e.g., "cv:4050-12345" or "12345") and text search.
        """
        clean_query = query.strip()
        if not clean_query:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Query cannot be empty."
            )

        external_apis = _get_external_apis()
        normalized = normalize_comicvine_payload(external_apis["comicvine"])
        if not normalized["enabled"]:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Comicvine integration is disabled.",
            )
        if not normalized["api_key"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Comicvine API key is missing."
            )

        # Check if query is an ID format (cv:4050-12345, cvid:4050-12345, or 4050-12345)
        id_match = re.fullmatch(r"(?:cvid?:)?(?:(\d+)-)?(\d+)", clean_query, flags=re.IGNORECASE)
        if id_match:
            resource_prefix = id_match.group(1) or "4050"
            volume_identifier = id_match.group(2)
            endpoint = f"volume/{resource_prefix}-{volume_identifier}"

            try:
                payload = await fetch_comicvine(
                    normalized,
                    endpoint,
                    {
                        "field_list": "id,name,start_year,publisher,description,site_detail_url,image,count_of_issues,language,volume_tag",
                    },
                )
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Comicvine request failed: {exc}",
                ) from exc

            volume_payload = payload.get("results")
            if not volume_payload:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Comicvine volume not found."
                )

            result = await build_comicvine_volume_result(normalized, volume_payload)
            return {
                "query": clean_query,
                "results": [result],
                "limit": 1,
                "page": 1,
                "total": 1,
            }

        # Text search
        limit = max(1, min(limit, 100))
        offset = max(page - 1, 0) * limit

        try:
            payload = await fetch_comicvine(
                normalized,
                "search",
                {
                    "resources": "volume",
                    "query": clean_query,
                    "limit": limit,
                    "offset": offset,
                    "field_list": "id,name,start_year,publisher,count_of_issues,description,deck,site_detail_url,image,language,volume_tag",
                },
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Comicvine request failed: {exc}"
            ) from exc

        results = []
        for item in payload.get("results", []):
            if item.get("resource_type") != "volume":
                continue
            result = await build_comicvine_volume_result(normalized, item)
            results.append(result)

        return {
            "query": clean_query,
            "results": results,
            "limit": limit,
            "page": page,
            "total": payload.get("number_of_total_results", len(results)),
        }

    return router
