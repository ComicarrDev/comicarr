"""Processing weekly releases - creates/updates library issues for added items."""

from __future__ import annotations

from typing import Any

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.database import retry_db_operation
from comicarr.db.models import LibraryIssue, LibraryVolume
from comicarr.routes.comicvine import (
    build_comicvine_volume_result,
    fetch_comicvine,
    normalize_comicvine_payload,
)
from comicarr.routes.settings import _get_external_apis
from comicarr.routes.volumes import fetch_comicvine_issues

logger = structlog.get_logger("comicarr.weekly_releases.processing")


async def _create_volume_from_comicvine(
    session: SQLModelAsyncSession,
    comicvine_id: int,
    library_id: str,
    normalized_comicvine: dict[str, Any] | None = None,
    monitored: bool = True,
    monitor_new_issues: bool = True,
) -> LibraryVolume:
    """Create a volume from ComicVine ID.

    Args:
        session: Database session
        comicvine_id: ComicVine volume ID
        library_id: Library ID to add volume to
        normalized_comicvine: Normalized ComicVine settings (if None, will fetch)
        monitored: Whether to monitor the volume
        monitor_new_issues: Whether to monitor new issues

    Returns:
        Created or existing LibraryVolume
    """
    # Check if volume already exists in this library
    existing = await session.exec(
        select(LibraryVolume).where(
            LibraryVolume.comicvine_id == comicvine_id, LibraryVolume.library_id == library_id
        )
    )
    existing_volume = existing.one_or_none()
    if existing_volume:
        return existing_volume

    # Get ComicVine settings if not provided
    if not normalized_comicvine:
        external_apis = _get_external_apis()
        comicvine_settings = external_apis.get("comicvine", {})
        if not comicvine_settings.get("api_key"):
            raise ValueError("ComicVine integration is not available")
        normalized_comicvine = normalize_comicvine_payload(comicvine_settings)

    if not normalized_comicvine.get("enabled") or not normalized_comicvine.get("api_key"):
        raise ValueError("ComicVine integration is not available")

    # Format ComicVine ID
    comicvine_id_str = f"4050-{comicvine_id}"

    # Fetch volume details from ComicVine
    volume_payload = await fetch_comicvine(
        normalized_comicvine,
        f"volume/4050-{comicvine_id}",
        {
            "field_list": "id,name,start_year,publisher,description,site_detail_url,image,count_of_issues,language,volume_tag,date_added,date_last_updated",
        },
    )
    volume_result = volume_payload.get("results")
    if not volume_result:
        raise ValueError(f"ComicVine volume {comicvine_id} not found")

    # Build normalized volume data
    volume_data = await build_comicvine_volume_result(normalized_comicvine, volume_result)

    # Fetch issues for this volume
    issues_data = await fetch_comicvine_issues(normalized_comicvine, comicvine_id)

    # Extract image URL
    image_url = volume_data.get("image")

    # Create LibraryVolume
    import uuid

    volume = LibraryVolume(
        id=uuid.uuid4().hex,
        library_id=library_id,
        comicvine_id=comicvine_id,
        title=volume_data.get("name") or f"Volume {comicvine_id}",
        year=volume_data.get("start_year"),
        publisher=volume_data.get("publisher"),
        publisher_country=volume_data.get("publisher_country"),
        description=volume_data.get("description"),
        site_url=volume_data.get("site_url"),
        count_of_issues=volume_data.get("count_of_issues"),
        image=image_url,
        monitored=monitored,
        monitor_new_issues=monitor_new_issues,
    )

    session.add(volume)
    # Use retry logic for flush to handle lock errors
    await retry_db_operation(
        lambda: session.flush(),
        session=session,
        operation_type="flush_volume",
    )
    await session.refresh(volume)

    # Create LibraryIssue records for all issues
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
            monitored=True,
            status="missing",
        )
        session.add(issue)

    await session.flush()
    await session.refresh(volume)

    logger.info(
        "Created volume with issues from ComicVine",
        volume_id=volume.id,
        comicvine_id=comicvine_id,
        issues_count=len(issues_data),
    )

    return volume
