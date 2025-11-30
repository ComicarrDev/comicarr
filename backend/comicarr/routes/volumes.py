"""Volume routes for managing library volumes."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.config import get_settings
from comicarr.core.dependencies import require_auth
from comicarr.core.search.cache import CacheManager
from comicarr.db.models import Library, LibraryIssue, LibraryVolume
from comicarr.routes.comicvine import (
    build_comicvine_volume_result,
    fetch_comicvine,
    normalize_comicvine_payload,
)
from comicarr.routes.settings import _get_external_apis

logger = structlog.get_logger("comicarr.routes.volumes")


# Request/Response Models
class IssueResponse(BaseModel):
    """Issue response model."""

    id: str
    title: str | None
    number: str | None
    release_date: str | None
    monitored: bool | None
    site_url: str | None
    image: str | None
    status: str | None
    file_path: str | None
    file_size: int | None


class VolumeResponse(BaseModel):
    """Volume response model."""

    id: str
    library_id: str
    comicvine_id: int | None
    title: str
    year: int | None
    publisher: str | None
    publisher_country: str | None
    description: str | None
    site_url: str | None
    count_of_issues: int | None
    image: str | None
    monitored: bool
    monitor_new_issues: bool
    folder_name: str | None
    custom_folder: bool
    date_last_updated: str | None
    is_ended: bool
    created_at: int
    updated_at: int
    progress: dict[str, int] = Field(default_factory=lambda: {"downloaded": 0, "total": 0})


class VolumeCreate(BaseModel):
    """Request model for creating a volume."""

    comicvine_id: int = Field(..., description="ComicVine volume ID")
    library_id: str = Field(..., description="Library ID to add volume to")


class VolumeListResponse(BaseModel):
    """Response model for listing volumes."""

    volumes: list[VolumeResponse]


async def fetch_comicvine_issues(
    settings: dict[str, Any],
    volume_id: int,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Fetch issues for a ComicVine volume.

    Args:
        settings: Normalized ComicVine settings
        volume_id: ComicVine volume ID
        limit: Maximum number of issues to fetch per request
        offset: Offset for pagination

    Returns:
        List of issue dictionaries from ComicVine API
    """
    issues = []
    current_offset = offset

    while True:
        payload = await fetch_comicvine(
            settings,
            "issues",
            {
                "filter": f"volume:{volume_id}",
                "limit": limit,
                "offset": current_offset,
                "field_list": "id,issue_number,name,description,site_detail_url,image,cover_date,date_added,date_last_updated",
                "sort": "issue_number:asc",
            },
        )

        results = payload.get("results", [])
        if not results:
            break

        issues.extend(results)

        # Check if there are more results
        number_of_page_results = payload.get("number_of_page_results", 0)
        if number_of_page_results < limit:
            break

        current_offset += limit

    return issues


def _is_comicvine_cache_enabled() -> bool:
    """Check if ComicVine caching is enabled.

    TODO: This should check a setting from external_apis["comicvine"]
    when the caching toggle is added to settings UI.
    For now, defaults to True (caching enabled).

    Returns:
        True if caching is enabled, False otherwise
    """
    # TODO: Get from settings when caching toggle is implemented
    # external_apis = _get_external_apis()
    # comicvine_settings = external_apis.get("comicvine", {})
    # return comicvine_settings.get("cache_enabled", True)
    return True


def create_volumes_router(
    get_db_session: Callable[[], AsyncIterator[SQLModelAsyncSession]],
) -> APIRouter:
    """Create volumes router.

    Args:
        get_db_session: Dependency function for database sessions

    Returns:
        Configured APIRouter instance
    """
    router = APIRouter(prefix="/api", tags=["volumes"])

    @router.get("/volumes", response_model=VolumeListResponse)
    async def list_volumes(
        request: Request,
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> VolumeListResponse:
        """List all volumes with progress calculation."""
        result = await session.exec(select(LibraryVolume))
        volumes = result.all()

        volumes_list: list[VolumeResponse] = []

        for volume in volumes:
            # Calculate progress
            issues_result = await session.exec(
                select(LibraryIssue).where(LibraryIssue.volume_id == volume.id)
            )
            issues = issues_result.all()

            total_issues = len(issues)
            downloaded_issues = sum(
                1 for issue in issues if issue.status == "ready" or issue.status == "processed"
            )

            volume_dict = VolumeResponse(
                id=volume.id,
                library_id=volume.library_id,
                comicvine_id=volume.comicvine_id,
                title=volume.title,
                year=volume.year,
                publisher=volume.publisher,
                publisher_country=volume.publisher_country,
                description=volume.description,
                site_url=volume.site_url,
                count_of_issues=volume.count_of_issues,
                image=volume.image,
                monitored=volume.monitored,
                monitor_new_issues=volume.monitor_new_issues,
                folder_name=volume.folder_name,
                custom_folder=volume.custom_folder,
                date_last_updated=volume.date_last_updated,
                is_ended=volume.is_ended,
                created_at=volume.created_at,
                updated_at=volume.updated_at,
                progress={"downloaded": downloaded_issues, "total": total_issues},
            )
            volumes_list.append(volume_dict)

        return VolumeListResponse(volumes=volumes_list)

    @router.post("/volumes", status_code=status.HTTP_201_CREATED, response_model=VolumeResponse)
    async def create_volume(
        payload: VolumeCreate,
        request: Request,
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> VolumeResponse:
        """Create a new volume from ComicVine ID.

        Fetches volume details and issues from ComicVine API, with optional caching.
        """
        # Check if library exists
        library = await session.get(Library, payload.library_id)
        if not library:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Library {payload.library_id} not found",
            )

        # Check if volume already exists
        existing = await session.exec(
            select(LibraryVolume).where(LibraryVolume.comicvine_id == payload.comicvine_id)
        )
        if existing.one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Volume with ComicVine ID {payload.comicvine_id} already exists",
            )

        # Get ComicVine settings
        external_apis = _get_external_apis()
        normalized_settings = normalize_comicvine_payload(external_apis["comicvine"])
        if not normalized_settings["enabled"]:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ComicVine integration is disabled",
            )
        if not normalized_settings["api_key"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ComicVine API key is missing",
            )

        # Check if caching is enabled
        cache_enabled = _is_comicvine_cache_enabled()

        # Initialize cache manager if caching is enabled
        cache_manager = None
        if cache_enabled:
            settings = get_settings()
            cache_manager = CacheManager(settings.cache_dir)

        # Format ComicVine ID (e.g., 4050-91273)
        comicvine_id_str = f"4050-{payload.comicvine_id}"

        # Check cache first (if enabled)
        cached_volume_data = None
        if cache_enabled and cache_manager:
            cached_volume_data = await cache_manager.get_comicvine_metadata(comicvine_id_str)

        if cached_volume_data:
            logger.info("Using cached ComicVine volume data", comicvine_id=payload.comicvine_id)
            volume_data = cached_volume_data.get("volume")
            issues_data = cached_volume_data.get("issues", [])
            if not volume_data:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Cached volume data is missing volume information",
                )
        else:
            # Fetch volume details from ComicVine
            try:
                volume_payload = await fetch_comicvine(
                    normalized_settings,
                    f"volume/4050-{payload.comicvine_id}",
                    {
                        "field_list": "id,name,start_year,publisher,description,site_detail_url,image,count_of_issues,language,volume_tag,date_added,date_last_updated",
                    },
                )
                volume_result = volume_payload.get("results")
                if not volume_result:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"ComicVine volume {payload.comicvine_id} not found",
                    )

                # Build normalized volume data
                volume_data = await build_comicvine_volume_result(
                    normalized_settings, volume_result
                )

                # Fetch issues
                logger.info("Fetching issues for volume", comicvine_id=payload.comicvine_id)
                issues_data = await fetch_comicvine_issues(
                    normalized_settings, payload.comicvine_id
                )

                # Cache the data (if enabled)
                if cache_enabled and cache_manager:
                    await cache_manager.store_comicvine_metadata(
                        comicvine_id_str,
                        {"volume": volume_data, "issues": issues_data},
                    )
                    logger.info(
                        "Cached ComicVine data",
                        comicvine_id=payload.comicvine_id,
                        issues_count=len(issues_data),
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(
                    "Failed to fetch ComicVine data",
                    comicvine_id=payload.comicvine_id,
                    error=str(e),
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to fetch volume data from ComicVine: {str(e)}",
                ) from e

        # Extract image URL
        image_url = volume_data.get("image")

        # Create LibraryVolume
        volume = LibraryVolume(
            library_id=payload.library_id,
            comicvine_id=payload.comicvine_id,
            title=volume_data.get("name") or f"Volume {payload.comicvine_id}",
            year=volume_data.get("start_year"),
            publisher=volume_data.get("publisher"),
            publisher_country=volume_data.get("publisher_country"),
            description=volume_data.get("description"),
            site_url=volume_data.get("site_url"),
            count_of_issues=volume_data.get("count_of_issues"),
            image=image_url,
            monitored=True,  # Default to monitored
            monitor_new_issues=True,  # Default to monitoring new issues
        )

        session.add(volume)
        await session.flush()  # Flush to get volume.id

        # Create LibraryIssue records
        for issue_data in issues_data:
            issue_image = None
            if isinstance(issue_data.get("image"), dict):
                issue_image = (
                    issue_data["image"].get("medium_url")
                    or issue_data["image"].get("original_url")
                    or issue_data["image"].get("icon_url")
                )
            elif isinstance(issue_data.get("image"), str):
                issue_image = issue_data["image"]

            issue = LibraryIssue(
                volume_id=volume.id,
                comicvine_id=issue_data.get("id"),
                number=str(issue_data.get("issue_number", "?")),
                title=issue_data.get("name"),
                release_date=issue_data.get("cover_date"),
                description=issue_data.get("description"),
                site_url=issue_data.get("site_detail_url"),
                image=issue_image,
                monitored=True,  # Default to monitored
                status="missing",  # New issues start as missing
            )
            session.add(issue)

        await session.commit()
        await session.refresh(volume)

        logger.info(
            "Volume created with issues",
            volume_id=volume.id,
            comicvine_id=payload.comicvine_id,
            issues_count=len(issues_data),
        )

        # Calculate progress
        issues_result = await session.exec(
            select(LibraryIssue).where(LibraryIssue.volume_id == volume.id)
        )
        issues = issues_result.all()
        total_issues = len(issues)
        downloaded_issues = sum(
            1 for issue in issues if issue.status == "ready" or issue.status == "processed"
        )

        return VolumeResponse(
            id=volume.id,
            library_id=volume.library_id,
            comicvine_id=volume.comicvine_id,
            title=volume.title,
            year=volume.year,
            publisher=volume.publisher,
            publisher_country=volume.publisher_country,
            description=volume.description,
            site_url=volume.site_url,
            count_of_issues=volume.count_of_issues,
            image=volume.image,
            monitored=volume.monitored,
            monitor_new_issues=volume.monitor_new_issues,
            folder_name=volume.folder_name,
            custom_folder=volume.custom_folder,
            date_last_updated=volume.date_last_updated,
            is_ended=volume.is_ended,
            created_at=volume.created_at,
            updated_at=volume.updated_at,
            progress={"downloaded": downloaded_issues, "total": total_issues},
        )

    @router.get("/volumes/{volume_id}")
    async def get_volume(
        volume_id: str,
        request: Request,
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> dict[str, Any]:
        """Get a single volume by ID with issues."""
        volume = await session.get(LibraryVolume, volume_id)
        if not volume:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Volume {volume_id} not found",
            )

        # Get issues
        issues_result = await session.exec(
            select(LibraryIssue).where(LibraryIssue.volume_id == volume.id)
        )
        issues = issues_result.all()

        total_issues = len(issues)
        downloaded_issues = sum(
            1 for issue in issues if issue.status == "ready" or issue.status == "processed"
        )

        # Convert issues to response format
        issues_list = [
            IssueResponse(
                id=issue.id,
                title=issue.title,
                number=issue.number,
                release_date=issue.release_date,
                monitored=issue.monitored,
                site_url=issue.site_url,
                image=issue.image,
                status=issue.status,
                file_path=issue.file_path,
                file_size=issue.file_size,
            )
            for issue in issues
        ]

        return {
            "volume": VolumeResponse(
                id=volume.id,
                library_id=volume.library_id,
                comicvine_id=volume.comicvine_id,
                title=volume.title,
                year=volume.year,
                publisher=volume.publisher,
                publisher_country=volume.publisher_country,
                description=volume.description,
                site_url=volume.site_url,
                count_of_issues=volume.count_of_issues,
                image=volume.image,
                monitored=volume.monitored,
                monitor_new_issues=volume.monitor_new_issues,
                folder_name=volume.folder_name,
                custom_folder=volume.custom_folder,
                date_last_updated=volume.date_last_updated,
                is_ended=volume.is_ended,
                created_at=volume.created_at,
                updated_at=volume.updated_at,
                progress={"downloaded": downloaded_issues, "total": total_issues},
            ),
            "issues": issues_list,
        }

    @router.delete("/volumes/{volume_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_volume(
        volume_id: str,
        request: Request,
        delete_files: bool = Query(False, description="Whether to delete files from disk"),
        _: bool = Depends(require_auth),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> None:
        """Delete a volume and all its issues.

        Args:
            volume_id: ID of the volume to delete
            delete_files: If True, also delete files from disk
        """

        volume = await session.get(LibraryVolume, volume_id)
        if not volume:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Volume {volume_id} not found",
            )

        # Delete all issues first
        issues_result = await session.exec(
            select(LibraryIssue).where(LibraryIssue.volume_id == volume_id)
        )
        issues = issues_result.all()
        for issue in issues:
            await session.delete(issue)

        # TODO: If delete_files is True, delete files from disk
        # This will be implemented when file management is added

        # Delete volume
        await session.delete(volume)
        await session.commit()

        logger.info(
            "Volume deleted",
            volume_id=volume_id,
            delete_files=delete_files,
        )

    return router
