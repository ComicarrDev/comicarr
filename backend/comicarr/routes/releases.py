"""Weekly releases routes."""

from __future__ import annotations

import asyncio
import datetime
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.database import get_global_session_factory
from comicarr.core.dependencies import require_auth
from comicarr.core.weekly_releases import (
    fetch_comicgeeks_releases,
    fetch_previewsworld_releases,
    fetch_readcomicsonline_releases,
    get_or_create_week,
    match_week_to_comicvine,
    match_week_to_library,
    store_releases,
)
from comicarr.core.weekly_releases.job_processor import (
    process_weekly_release_job,
    start_weekly_release_job,
)
from comicarr.core.weekly_releases.matching_job_processor import (
    process_matching_job,
    start_matching_job,
)
from comicarr.db.models import (
    LibraryIssue,
    LibraryVolume,
    WeeklyReleaseItem,
    WeeklyReleaseMatchingJob,
    WeeklyReleaseProcessingJob,
    WeeklyReleaseWeek,
)

logger = structlog.get_logger("comicarr.routes.releases")


# Request/Response Models (defined at module level to avoid forward reference issues)
class WeeklyReleaseWeekResponse(BaseModel):
    """Weekly release week response model."""

    id: str
    week_start: str
    fetched_at: int
    status: str
    counts: dict[str, int]


class WeeklyReleaseItemResponse(BaseModel):
    """Weekly release item response model."""

    id: str
    week_id: str
    week_start: str | None
    source: str
    issue_key: str | None
    title: str
    publisher: str | None
    release_date: str | None
    url: str | None
    status: str
    notes: str | None
    matched_volume_id: str | None
    matched_issue_id: str | None
    comicvine_volume_id: int | None
    comicvine_issue_id: int | None
    comicvine_volume_name: str | None
    comicvine_issue_name: str | None
    comicvine_issue_number: str | None
    comicvine_site_url: str | None
    comicvine_cover_date: str | None
    comicvine_confidence: float | None
    metadata: dict[str, Any]
    library_volume: dict[str, Any] | None
    library_issue: dict[str, Any] | None


class UpdateEntryRequest(BaseModel):
    """Request model for updating an entry."""

    status: str | None = Field(None, description="New status: pending, import, skipped, processed")
    notes: str | None = Field(None, description="Notes")
    comicvine_volume_id: int | None = Field(None, description="ComicVine volume ID")


class FetchReleasesRequest(BaseModel):
    """Request model for fetching releases."""

    week_start: str | None = Field(
        None, description="Week start date (YYYY-MM-DD), defaults to current week"
    )
    source: str = Field(..., description="Source: previewsworld, comicgeeks, readcomicsonline")


def create_releases_router(
    get_db_session: Callable[[], AsyncIterator[SQLModelAsyncSession]],
) -> APIRouter:
    """Create releases router.

    Args:
        get_db_session: Dependency function for database sessions

    Returns:
        Configured APIRouter instance
    """
    router = APIRouter(prefix="/api/releases", tags=["releases"])

    # Request/Response Models
    class WeeklyReleaseWeekResponse(BaseModel):
        """Weekly release week response model."""

        id: str
        week_start: str
        fetched_at: int
        status: str
        counts: dict[str, int]

    class WeeklyReleaseItemResponse(BaseModel):
        """Weekly release item response model."""

        id: str
        week_id: str
        week_start: str | None
        source: str
        issue_key: str | None
        title: str
        publisher: str | None
        release_date: str | None
        url: str | None
        status: str
        notes: str | None
        matched_volume_id: str | None
        matched_issue_id: str | None
        comicvine_volume_id: int | None
        comicvine_issue_id: int | None
        comicvine_volume_name: str | None
        comicvine_issue_name: str | None
        comicvine_issue_number: str | None
        comicvine_site_url: str | None
        comicvine_cover_date: str | None
        comicvine_confidence: float | None
        metadata: dict[str, Any]
        library_volume: dict[str, Any] | None
        library_issue: dict[str, Any] | None

    class UpdateEntryRequest(BaseModel):
        """Request model for updating an entry."""

        status: str | None = Field(
            None, description="New status: pending, import, skipped, processed"
        )
        notes: str | None = Field(None, description="Notes")

    class FetchReleasesRequest(BaseModel):
        """Request model for fetching releases."""

        week_start: str | None = Field(
            None, description="Week start date (YYYY-MM-DD), defaults to current week"
        )
        source: str = Field(..., description="Source: previewsworld, comicgeeks, readcomicsonline")

    # Helper function to serialize items
    async def serialize_item(
        session: SQLModelAsyncSession, item: WeeklyReleaseItem
    ) -> dict[str, Any]:
        """Serialize a weekly release item for API response."""
        data = item.model_dump()

        # Parse metadata
        if item.metadata_json:
            try:
                data["metadata"] = json.loads(item.metadata_json)
            except (json.JSONDecodeError, TypeError):
                data["metadata"] = {}
        else:
            data["metadata"] = {}

        # Include library volume/issue if matched
        data["library_volume"] = None
        data["library_issue"] = None

        if item.matched_volume_id:
            volume_result = await session.exec(
                select(LibraryVolume).where(LibraryVolume.id == item.matched_volume_id)
            )
            volume = volume_result.first()
            if volume:
                data["library_volume"] = {
                    "id": volume.id,
                    "title": volume.title,
                    "comicvine_id": volume.comicvine_id,
                    "publisher": volume.publisher,
                    "year": volume.year,
                }

        if item.matched_issue_id:
            issue_result = await session.exec(
                select(LibraryIssue).where(LibraryIssue.id == item.matched_issue_id)
            )
            issue = issue_result.first()
            if issue:
                data["library_issue"] = {
                    "id": issue.id,
                    "number": issue.number,
                    "title": issue.title,
                    "status": issue.status,
                    "release_date": issue.release_date,
                    "file_path": issue.file_path,
                }

        return data

    @router.get("", response_model=dict[str, list[WeeklyReleaseWeekResponse]])
    async def list_weeks(
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, list[dict[str, Any]]]:
        """List all weekly release weeks."""
        logger.debug("Listing weekly release weeks")

        weeks_result = await session.exec(
            select(WeeklyReleaseWeek).order_by(col(WeeklyReleaseWeek.week_start).desc())
        )
        weeks = weeks_result.all()

        response = []
        for week in weeks:
            # Count entries by status
            items_result = await session.exec(
                select(WeeklyReleaseItem).where(WeeklyReleaseItem.week_id == week.id)
            )
            items = items_result.all()

            counts = {
                "total": len(items),
                "pending": sum(1 for item in items if item.status == "pending"),
                "import": sum(1 for item in items if item.status == "import"),
                "skipped": sum(1 for item in items if item.status == "skipped"),
                "processed": sum(1 for item in items if item.status == "processed"),
            }

            response.append(
                {
                    "id": week.id,
                    "week_start": week.week_start,
                    "fetched_at": week.fetched_at,
                    "status": week.status,
                    "counts": counts,
                }
            )

        return {"weeks": response}

    @router.delete("/{week_id}", response_model=dict[str, Any])
    async def delete_week(
        week_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Delete a weekly release week and all its entries."""
        logger.info("Deleting weekly release week", week_id=week_id)

        # Verify week exists
        week = await session.get(WeeklyReleaseWeek, week_id)
        if week is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Weekly release week not found"
            )

        # Delete all entries for this week
        items_result = await session.exec(
            select(WeeklyReleaseItem).where(WeeklyReleaseItem.week_id == week_id)
        )
        items = items_result.all()

        for item in items:
            await session.delete(item)

        # Delete the week
        await session.delete(week)
        await session.commit()

        logger.info("Deleted weekly release week", week_id=week_id, items_deleted=len(items))

        return {
            "success": True,
            "message": f"Deleted week and {len(items)} entries",
            "items_deleted": len(items),
        }

    # More specific routes must be defined before less specific ones
    # (e.g., /{week_id}/match-library before /{week_id})
    @router.post("/{week_id}/match-comicvine", response_model=dict[str, Any])
    async def match_week_comicvine(
        week_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Match all items in a week to ComicVine."""
        logger.info("Matching week to ComicVine", week_id=week_id)

        # Verify week exists
        week = await session.get(WeeklyReleaseWeek, week_id)
        if week is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Weekly release week not found"
            )

        try:
            result = await match_week_to_comicvine(week_id, session)
            return {
                "success": True,
                "message": f"Matched {result['matched']} items to ComicVine",
                **result,
            }
        except Exception as exc:
            logger.exception("Failed to match week to ComicVine", week_id=week_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to match week to ComicVine: {exc}",
            )

    @router.post("/{week_id}/match-library", response_model=dict[str, Any])
    async def match_week_library(
        week_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Match all items in a week to library."""
        logger.info("Matching week to library", week_id=week_id)

        # Verify week exists
        week = await session.get(WeeklyReleaseWeek, week_id)
        if week is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Weekly release week not found"
            )

        try:
            result = await match_week_to_library(week_id, session)
            return {
                "success": True,
                "message": f"Matched {result['matched']} items to library",
                **result,
            }
        except Exception as exc:
            logger.exception("Failed to match week to library", week_id=week_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to match week to library: {exc}",
            )

    @router.post("/{week_id}/entries/{entry_id}/identify", response_model=dict[str, Any])
    async def identify_entry(
        week_id: str,
        entry_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Re-run ComicVine matching for a weekly release entry and return diagnostic information.

        Returns detailed information about what was tried and what failed.
        """
        from comicarr.core.weekly_releases.matching import match_weekly_release_to_comicvine

        # Verify week exists
        week = await session.get(WeeklyReleaseWeek, week_id)
        if week is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Weekly release week not found"
            )

        # Get entry
        entry = await session.get(WeeklyReleaseItem, entry_id)
        if entry is None or entry.week_id != week_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

        diagnostic_info: dict[str, Any] = {
            "entry_id": entry.id,
            "title": entry.title,
            "publisher": entry.publisher,
            "steps": [],
            "errors": [],
            "warnings": [],
        }

        try:
            # Step 1: Parse metadata
            step1: dict[str, Any] = {
                "step": "parse_metadata",
                "description": "Parse series name and issue number from title and metadata",
            }
            try:
                metadata = json.loads(entry.metadata_json or "{}")
                series = metadata.get("series") or entry.title
                issue_number = metadata.get("issue_number")

                # Extract year from release_date if available
                year = None
                if entry.release_date:
                    try:
                        from datetime import datetime

                        release_date = datetime.fromisoformat(
                            entry.release_date.replace("Z", "+00:00")
                        )
                        year = release_date.year
                    except (ValueError, AttributeError):
                        pass

                # If no year from release_date, try to extract from title
                if not year:
                    from comicarr.core.utils import _extract_year

                    year = _extract_year(entry.title)

                step1["result"] = {
                    "series": series,
                    "issue_number": issue_number,
                    "year": year,
                    "publisher": entry.publisher,
                    "release_date": entry.release_date,
                }
                step1["success"] = True
            except Exception as exc:
                step1["success"] = False
                step1["error"] = str(exc)
                diagnostic_info["errors"].append(f"Failed to parse metadata: {exc}")
            diagnostic_info["steps"].append(step1)

            # Step 2: Search ComicVine
            step2: dict[str, Any] = {
                "step": "search_comicvine",
                "description": "Search ComicVine for volume/issue match",
            }
            if step1.get("success") and step1.get("result", {}).get("series"):
                try:
                    # Re-run matching
                    comicvine_data = await match_weekly_release_to_comicvine(entry, session)

                    if comicvine_data:
                        # Parse results_sample if it's a JSON string
                        results_sample = comicvine_data.get("results_sample")
                        if isinstance(results_sample, str):
                            try:
                                results_sample = json.loads(results_sample)
                            except (json.JSONDecodeError, TypeError):
                                results_sample = None

                        step2["result"] = {
                            "volume_id": comicvine_data.get("volume_id"),
                            "volume_name": comicvine_data.get("volume_name"),
                            "issue_id": comicvine_data.get("issue_id"),
                            "issue_name": comicvine_data.get("issue_name"),
                            "issue_number": comicvine_data.get("issue_number"),
                            "confidence": comicvine_data.get("confidence"),
                            "search_query": comicvine_data.get("search_query"),
                            "api_query": comicvine_data.get("api_query"),
                            "results_count": comicvine_data.get("results_count"),
                            "has_results_sample": bool(results_sample),
                            "results_sample": results_sample,
                        }
                        step2["success"] = comicvine_data.get("volume_id") is not None
                        if not step2["success"]:
                            step2["reason"] = (
                                "ComicVine search returned results but no good match found"
                            )
                            diagnostic_info["warnings"].append(
                                "ComicVine search found results but no match"
                            )
                    else:
                        step2["success"] = False
                        step2["reason"] = "ComicVine search returned no results"
                        diagnostic_info["warnings"].append("No ComicVine results found")
                except Exception as exc:
                    step2["success"] = False
                    step2["error"] = str(exc)
                    diagnostic_info["errors"].append(f"ComicVine search failed: {exc}")
            else:
                step2["success"] = False
                step2["reason"] = "Cannot search ComicVine: missing series name"
                diagnostic_info["warnings"].append(
                    "Skipped ComicVine search: insufficient metadata"
                )
            diagnostic_info["steps"].append(step2)

            # Commit any changes made during matching
            await session.commit()

            # Summary
            diagnostic_info["summary"] = {
                "metadata_extracted": step1.get("success", False),
                "comicvine_match_found": step2.get("result", {}).get("volume_id") is not None,
                "has_errors": len(diagnostic_info["errors"]) > 0,
                "has_warnings": len(diagnostic_info["warnings"]) > 0,
            }

        except Exception as exc:
            diagnostic_info["errors"].append(f"Unexpected error during identification: {exc}")
            logger.exception("Failed to identify entry", entry_id=entry_id, error=str(exc))

        return diagnostic_info

    # Bulk operations must be defined before GET /{week_id} to avoid route conflicts
    @router.post("/{week_id}/entries/bulk-reset-matches", response_model=dict[str, Any])
    async def bulk_reset_entry_matches(
        week_id: str,
        request: dict[str, Any] = Body(...),
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Reset ComicVine and library matches for multiple entries."""
        entry_ids = request.get("entry_ids", [])
        if not entry_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="entry_ids is required"
            )

        logger.info("Bulk resetting matches for entries", week_id=week_id, count=len(entry_ids))

        # Verify week exists
        week = await session.get(WeeklyReleaseWeek, week_id)
        if week is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Weekly release week not found"
            )

        # Get all entries
        items_result = await session.exec(
            select(WeeklyReleaseItem).where(
                WeeklyReleaseItem.week_id == week_id, col(WeeklyReleaseItem.id).in_(entry_ids)
            )
        )
        items = list(items_result.all())

        if len(items) != len(entry_ids):
            logger.warning("Some entries not found", requested=len(entry_ids), found=len(items))

        import time

        updated_count = 0
        for item in items:
            # Reset all match fields
            item.matched_volume_id = None
            item.matched_issue_id = None
            item.comicvine_volume_id = None
            item.comicvine_issue_id = None
            item.comicvine_volume_name = None
            item.comicvine_issue_name = None
            item.comicvine_issue_number = None
            item.comicvine_site_url = None
            item.comicvine_cover_date = None
            item.comicvine_confidence = None
            item.cv_search_query = None
            item.cv_results_count = None
            item.cv_results_sample = None
            item.updated_at = int(time.time())
            updated_count += 1

        await session.commit()

        logger.info("Bulk reset matches for entries", week_id=week_id, count=updated_count)

        return {
            "success": True,
            "message": f"Reset matches for {updated_count} entry(ies)",
            "count": updated_count,
        }

    @router.post("/{week_id}/entries/bulk-update-status", response_model=dict[str, Any])
    async def bulk_update_entry_status(
        week_id: str,
        request: dict[str, Any] = Body(...),
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Update status for multiple entries."""
        entry_ids = request.get("entry_ids", [])
        status_value = request.get("status")

        if not entry_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="entry_ids is required"
            )

        if status_value not in ["pending", "import", "skipped", "processed"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="status must be one of: pending, import, skipped, processed",
            )

        logger.info(
            "Bulk updating entry status", week_id=week_id, count=len(entry_ids), status=status_value
        )

        # Verify week exists
        week = await session.get(WeeklyReleaseWeek, week_id)
        if week is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Weekly release week not found"
            )

        # Get all entries
        items_result = await session.exec(
            select(WeeklyReleaseItem).where(
                WeeklyReleaseItem.week_id == week_id, col(WeeklyReleaseItem.id).in_(entry_ids)
            )
        )
        items = list(items_result.all())

        if len(items) != len(entry_ids):
            logger.warning("Some entries not found", requested=len(entry_ids), found=len(items))

        import time

        updated_count = 0
        for item in items:
            item.status = status_value
            item.updated_at = int(time.time())
            updated_count += 1

        await session.commit()

        logger.info(
            "Bulk updated entry status", week_id=week_id, count=updated_count, status=status_value
        )

        return {
            "success": True,
            "message": f"Updated status to {status_value} for {updated_count} entry(ies)",
            "count": updated_count,
        }

    @router.get("/{week_id}", response_model=dict[str, Any])
    async def get_week(
        week_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Get a specific week and its entries."""
        logger.debug("Getting weekly release week", week_id=week_id)

        week = await session.get(WeeklyReleaseWeek, week_id)
        if week is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Weekly release week not found"
            )

        items_result = await session.exec(
            select(WeeklyReleaseItem)
            .where(WeeklyReleaseItem.week_id == week_id)
            .order_by(col(WeeklyReleaseItem.created_at))
        )
        items = items_result.all()

        entries = [await serialize_item(session, item) for item in items]

        return {
            "week": week.model_dump(),
            "entries": entries,
        }

    @router.put("/{week_id}/entries/{entry_id}", response_model=WeeklyReleaseItemResponse)
    async def update_entry(
        week_id: str,
        entry_id: str,
        request: UpdateEntryRequest,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Update a weekly release entry."""
        logger.debug("Updating entry", week_id=week_id, entry_id=entry_id)

        # Verify week exists
        week = await session.get(WeeklyReleaseWeek, week_id)
        if week is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Weekly release week not found"
            )

        entry = await session.get(WeeklyReleaseItem, entry_id)
        if entry is None or entry.week_id != week_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

        # Update fields
        if request.status is not None:
            entry.status = request.status
        if request.notes is not None:
            entry.notes = request.notes
        if hasattr(request, "comicvine_volume_id") and request.comicvine_volume_id is not None:
            entry.comicvine_volume_id = request.comicvine_volume_id  # type: ignore[assignment]
            # If status is not explicitly set and we're setting a ComicVine volume, set to manual_match
            if request.status is None and entry.status == "pending":
                entry.status = "manual_match"

        import time

        entry.updated_at = int(time.time())

        await session.commit()
        await session.refresh(entry)

        return await serialize_item(session, entry)

    @router.post("/{week_id}/entries/{entry_id}/reset-matches", response_model=dict[str, Any])
    async def reset_entry_matches(
        week_id: str,
        entry_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Reset ComicVine and library matches for an entry."""
        logger.info("Resetting matches for entry", week_id=week_id, entry_id=entry_id)

        # Verify week exists
        week = await session.get(WeeklyReleaseWeek, week_id)
        if week is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Weekly release week not found"
            )

        entry = await session.get(WeeklyReleaseItem, entry_id)
        if entry is None or entry.week_id != week_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

        # Reset all match fields
        entry.matched_volume_id = None
        entry.matched_issue_id = None
        entry.comicvine_volume_id = None
        entry.comicvine_issue_id = None
        entry.comicvine_volume_name = None
        entry.comicvine_issue_name = None
        entry.comicvine_issue_number = None
        entry.comicvine_site_url = None
        entry.comicvine_cover_date = None
        entry.comicvine_confidence = None
        entry.cv_search_query = None
        entry.cv_results_count = None
        entry.cv_results_sample = None

        import time

        entry.updated_at = int(time.time())

        await session.commit()
        await session.refresh(entry)

        logger.info("Reset matches for entry", week_id=week_id, entry_id=entry_id)

        return await serialize_item(session, entry)

    @router.post("/{week_id}/entries/{entry_id}/match-comicvine", response_model=dict[str, Any])
    async def match_entry_comicvine(
        week_id: str,
        entry_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Match a single entry to ComicVine."""
        from comicarr.core.weekly_releases.matching import match_weekly_release_to_comicvine

        logger.info("Matching entry to ComicVine", week_id=week_id, entry_id=entry_id)

        # Verify week exists
        week = await session.get(WeeklyReleaseWeek, week_id)
        if week is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Weekly release week not found"
            )

        entry = await session.get(WeeklyReleaseItem, entry_id)
        if entry is None or entry.week_id != week_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

        try:
            result = await match_weekly_release_to_comicvine(entry, session)
            await session.commit()
            await session.refresh(entry)

            return await serialize_item(session, entry)
        except Exception as exc:
            logger.exception(
                "Failed to match entry to ComicVine", entry_id=entry_id, error=str(exc)
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to match entry to ComicVine: {exc}",
            )

    @router.post("/{week_id}/entries/{entry_id}/match-library", response_model=dict[str, Any])
    async def match_entry_library(
        week_id: str,
        entry_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Match a single entry to library."""
        from comicarr.core.weekly_releases.matching import match_weekly_release_to_library

        logger.info("Matching entry to library", week_id=week_id, entry_id=entry_id)

        # Verify week exists
        week = await session.get(WeeklyReleaseWeek, week_id)
        if week is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Weekly release week not found"
            )

        entry = await session.get(WeeklyReleaseItem, entry_id)
        if entry is None or entry.week_id != week_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

        try:
            result = await match_weekly_release_to_library(entry, session)
            await session.commit()
            await session.refresh(entry)

            return await serialize_item(session, entry)
        except Exception as exc:
            logger.exception("Failed to match entry to library", entry_id=entry_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to match entry to library: {exc}",
            )

    @router.post("/{week_id}/process", response_model=dict[str, Any])
    async def process_week(
        week_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Start processing weekly release items - creates a background job.

        This endpoint creates a background job to process all items with status "import"
        for the given week. It creates or updates library volumes and issues based on ComicVine matches.

        Returns the job ID which can be used to poll for status.
        """
        logger.info("Starting weekly release processing job", week_id=week_id)

        # Verify week exists
        week = await session.get(WeeklyReleaseWeek, week_id)
        if week is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Weekly release week not found"
            )

        try:
            # Create and start job
            job = await start_weekly_release_job(session, week_id)

            # Start processing in background
            session_factory = get_global_session_factory()
            if session_factory:

                async def run_job():
                    async with session_factory() as bg_session:  # type: ignore[misc]
                        await process_weekly_release_job(bg_session, job.id)

                asyncio.create_task(run_job())

            logger.info("Processing job created", week_id=week_id, job_id=job.id)
            return {
                "success": True,
                "job_id": job.id,
                "status": job.status,
                "progress": {
                    "current": job.progress_current,
                    "total": job.progress_total,
                },
            }
        except Exception as exc:
            logger.exception("Failed to create processing job", week_id=week_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create processing job: {exc}",
            )

    @router.get("/{week_id}/process/status", response_model=dict[str, Any])
    async def get_process_status(
        week_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Get the status of the processing job for a week.

        Returns the current job status and progress.
        """
        try:
            # Find the most recent job for this week
            job_result = await session.exec(
                select(WeeklyReleaseProcessingJob)
                .where(WeeklyReleaseProcessingJob.week_id == week_id)
                .order_by(col(WeeklyReleaseProcessingJob.created_at).desc())
            )
            job = job_result.first()

            if not job:
                return {
                    "job_id": None,
                    "status": "none",
                    "progress": {"current": 0, "total": 0},
                }

            return {
                "job_id": job.id,
                "status": job.status,
                "progress": {
                    "current": job.progress_current,
                    "total": job.progress_total,
                },
                "error_count": job.error_count,
                "error": job.error,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
            }
        except Exception as exc:
            logger.exception("Failed to get job status", week_id=week_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get job status: {exc}",
            )

    @router.post("/{week_id}/process/pause", response_model=dict[str, Any])
    async def pause_processing(
        week_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Pause the processing job for a week."""
        try:
            # Find the most recent active job for this week
            job_result = await session.exec(
                select(WeeklyReleaseProcessingJob)
                .where(WeeklyReleaseProcessingJob.week_id == week_id)
                .where(col(WeeklyReleaseProcessingJob.status).in_(["queued", "processing"]))
                .order_by(col(WeeklyReleaseProcessingJob.created_at).desc())
            )
            job = job_result.first()

            if not job:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active processing job found for this week",
                )

            if job.status == "paused":
                return {"success": True, "message": "Job is already paused", "status": job.status}

            job.status = "paused"
            job.updated_at = int(time.time())
            await session.commit()

            logger.info("Processing job paused", week_id=week_id, job_id=job.id)
            return {"success": True, "message": "Job paused", "status": job.status}
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Failed to pause processing job", week_id=week_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to pause processing job: {exc}",
            )

    @router.post("/{week_id}/process/resume", response_model=dict[str, Any])
    async def resume_processing(
        week_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Resume a paused processing job for a week."""
        try:
            # Find the most recent paused job for this week
            job_result = await session.exec(
                select(WeeklyReleaseProcessingJob)
                .where(WeeklyReleaseProcessingJob.week_id == week_id)
                .where(WeeklyReleaseProcessingJob.status == "paused")
                .order_by(col(WeeklyReleaseProcessingJob.created_at).desc())
            )
            job = job_result.first()

            if not job:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No paused processing job found for this week",
                )

            job.status = "processing"
            job.updated_at = int(time.time())
            await session.commit()

            logger.info("Processing job resumed", week_id=week_id, job_id=job.id)

            # If job was not already running, start it
            session_factory = get_global_session_factory()
            if session_factory and job:
                job_id = job.id

                async def run_job():
                    async with session_factory() as bg_session:  # type: ignore[misc]
                        await process_weekly_release_job(bg_session, job_id)

                asyncio.create_task(run_job())

            return {"success": True, "message": "Job resumed", "status": job.status}
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Failed to resume processing job", week_id=week_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to resume processing job: {exc}",
            )

    @router.post("/{week_id}/match-bulk", response_model=dict[str, Any])
    async def start_bulk_matching(
        week_id: str,
        request: dict[str, Any] = Body(...),
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Start bulk matching job for selected entries.

        This endpoint creates a background job to match selected entries to ComicVine or library.

        Request body:
            - match_type: "comicvine" or "library"
            - entry_ids: List of entry IDs to match

        Returns the job ID which can be used to poll for status.
        """
        match_type = request.get("match_type")
        entry_ids = request.get("entry_ids", [])

        if match_type not in ("comicvine", "library"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="match_type must be 'comicvine' or 'library'",
            )

        if not entry_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="entry_ids is required and must not be empty",
            )

        logger.info(
            "Starting bulk matching job",
            week_id=week_id,
            match_type=match_type,
            count=len(entry_ids),
        )

        # Verify week exists
        week = await session.get(WeeklyReleaseWeek, week_id)
        if week is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Weekly release week not found"
            )

        try:
            # Create and start job
            job = await start_matching_job(session, week_id, match_type, entry_ids)

            # Start processing in background
            session_factory = get_global_session_factory()
            if session_factory:

                async def run_job():
                    async with session_factory() as bg_session:  # type: ignore[misc]
                        await process_matching_job(bg_session, job.id)

                asyncio.create_task(run_job())

            logger.info(
                "Matching job created", week_id=week_id, job_id=job.id, match_type=match_type
            )
            return {
                "success": True,
                "job_id": job.id,
                "status": job.status,
                "progress": {
                    "current": job.progress_current,
                    "total": job.progress_total,
                },
            }
        except Exception as exc:
            logger.exception("Failed to create matching job", week_id=week_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create matching job: {exc}",
            )

    @router.get("/{week_id}/match-bulk/status", response_model=dict[str, Any])
    async def get_bulk_matching_status(
        week_id: str,
        match_type: str = Query(..., description="Match type: 'comicvine' or 'library'"),
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Get the status of the bulk matching job for a week.

        Returns the current job status and progress.
        """
        if match_type not in ("comicvine", "library"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="match_type must be 'comicvine' or 'library'",
            )

        try:
            # Find the most recent job for this week and match type
            job_result = await session.exec(
                select(WeeklyReleaseMatchingJob)
                .where(WeeklyReleaseMatchingJob.week_id == week_id)
                .where(WeeklyReleaseMatchingJob.match_type == match_type)
                .order_by(col(WeeklyReleaseMatchingJob.created_at).desc())
            )
            job = job_result.first()

            if not job:
                return {
                    "job_id": None,
                    "status": "none",
                    "progress": {"current": 0, "total": 0},
                    "matched_count": 0,
                    "error_count": 0,
                }

            return {
                "job_id": job.id,
                "status": job.status,
                "progress": {
                    "current": job.progress_current,
                    "total": job.progress_total,
                },
                "matched_count": job.matched_count,
                "error_count": job.error_count,
                "error": job.error,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
            }
        except Exception as exc:
            logger.exception(
                "Failed to get matching job status",
                week_id=week_id,
                match_type=match_type,
                error=str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get matching job status: {exc}",
            )

    @router.post("/{week_id}/match-bulk/pause", response_model=dict[str, Any])
    async def pause_matching(
        week_id: str,
        match_type: str = Query(..., description="Match type: 'comicvine' or 'library'"),
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Pause the bulk matching job for a week."""
        if match_type not in ("comicvine", "library"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="match_type must be 'comicvine' or 'library'",
            )

        try:
            # Find the most recent active job for this week and match type
            job_result = await session.exec(
                select(WeeklyReleaseMatchingJob)
                .where(WeeklyReleaseMatchingJob.week_id == week_id)
                .where(WeeklyReleaseMatchingJob.match_type == match_type)
                .where(col(WeeklyReleaseMatchingJob.status).in_(["queued", "processing"]))
                .order_by(col(WeeklyReleaseMatchingJob.created_at).desc())
            )
            job = job_result.first()

            if not job:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active matching job found for this week and match type",
                )

            if job.status == "paused":
                return {"success": True, "message": "Job is already paused", "status": job.status}

            job.status = "paused"
            job.updated_at = int(time.time())
            await session.commit()

            logger.info(
                "Matching job paused", week_id=week_id, job_id=job.id, match_type=match_type
            )
            return {"success": True, "message": "Job paused", "status": job.status}
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "Failed to pause matching job",
                week_id=week_id,
                match_type=match_type,
                error=str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to pause matching job: {exc}",
            )

    @router.post("/{week_id}/match-bulk/resume", response_model=dict[str, Any])
    async def resume_matching(
        week_id: str,
        match_type: str = Query(..., description="Match type: 'comicvine' or 'library'"),
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Resume a paused bulk matching job for a week."""
        if match_type not in ("comicvine", "library"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="match_type must be 'comicvine' or 'library'",
            )

        try:
            # Find the most recent paused job for this week and match type
            job_result = await session.exec(
                select(WeeklyReleaseMatchingJob)
                .where(WeeklyReleaseMatchingJob.week_id == week_id)
                .where(WeeklyReleaseMatchingJob.match_type == match_type)
                .where(WeeklyReleaseMatchingJob.status == "paused")
                .order_by(col(WeeklyReleaseMatchingJob.created_at).desc())
            )
            job = job_result.first()

            if not job:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No paused matching job found for this week and match type",
                )

            job.status = "processing"
            job.updated_at = int(time.time())
            await session.commit()

            logger.info(
                "Matching job resumed", week_id=week_id, job_id=job.id, match_type=match_type
            )

            # If job was not already running, start it
            session_factory = get_global_session_factory()
            if session_factory and job:
                job_id = job.id

                async def run_job():
                    async with session_factory() as bg_session:  # type: ignore[misc]
                        await process_matching_job(bg_session, job_id)

                asyncio.create_task(run_job())

            return {"success": True, "message": "Job resumed", "status": job.status}
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "Failed to resume matching job",
                week_id=week_id,
                match_type=match_type,
                error=str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to resume matching job: {exc}",
            )

    @router.post("/{week_id}/process/restart", response_model=dict[str, Any])
    async def restart_processing(
        week_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Restart the processing job for a week (cancels existing and starts new)."""
        try:
            # Find any existing job for this week
            job_result = await session.exec(
                select(WeeklyReleaseProcessingJob)
                .where(WeeklyReleaseProcessingJob.week_id == week_id)
                .order_by(col(WeeklyReleaseProcessingJob.created_at).desc())
            )
            existing_job = job_result.first()

            # Cancel existing job if it's active
            if existing_job and existing_job.status in ("queued", "processing", "paused"):
                existing_job.status = "cancelled"
                existing_job.updated_at = int(time.time())
                await session.commit()

            # Start a new job
            job = await start_weekly_release_job(session, week_id)

            # Start processing in background
            session_factory = get_global_session_factory()
            if session_factory:

                async def run_job():
                    async with session_factory() as bg_session:  # type: ignore[misc]
                        await process_weekly_release_job(bg_session, job.id)

                asyncio.create_task(run_job())

            logger.info("Processing job restarted", week_id=week_id, job_id=job.id)
            return {
                "success": True,
                "message": "Job restarted",
                "job_id": job.id,
                "status": job.status,
                "progress": {
                    "current": job.progress_current,
                    "total": job.progress_total,
                },
            }
        except Exception as exc:
            logger.exception("Failed to restart processing job", week_id=week_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to restart processing job: {exc}",
            )

    @router.post("/{week_id}/match-bulk/restart", response_model=dict[str, Any])
    async def restart_matching(
        week_id: str,
        match_type: str = Query(..., description="Match type: 'comicvine' or 'library'"),
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Restart the bulk matching job for a week (cancels existing and starts new)."""
        if match_type not in ("comicvine", "library"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="match_type must be 'comicvine' or 'library'",
            )

        try:
            # Find any existing job for this week and type
            job_result = await session.exec(
                select(WeeklyReleaseMatchingJob)
                .where(WeeklyReleaseMatchingJob.week_id == week_id)
                .where(WeeklyReleaseMatchingJob.match_type == match_type)
                .order_by(col(WeeklyReleaseMatchingJob.created_at).desc())
            )
            existing_job = job_result.first()

            # Get entry IDs from existing job, or fetch all unmatched entries
            entry_ids = []
            if existing_job and existing_job.entry_ids:
                entry_ids = existing_job.entry_ids
            else:
                # Fetch entries that need matching
                entries_result = await session.exec(
                    select(WeeklyReleaseItem).where(WeeklyReleaseItem.week_id == week_id)
                )
                entries = entries_result.all()
                if match_type == "comicvine":
                    entry_ids = [e.id for e in entries if not e.comicvine_volume_id]
                else:
                    entry_ids = [e.id for e in entries if not e.matched_volume_id]

            # Cancel existing job if it's active
            if existing_job and existing_job.status in ("queued", "processing", "paused"):
                existing_job.status = "cancelled"
                existing_job.updated_at = int(time.time())
                await session.commit()

            # Start a new job
            job = await start_matching_job(session, week_id, match_type, entry_ids)

            # Start processing in background
            session_factory = get_global_session_factory()
            if session_factory:

                async def run_job():
                    async with session_factory() as bg_session:  # type: ignore[misc]
                        await process_matching_job(bg_session, job.id)

                asyncio.create_task(run_job())

            logger.info(
                "Matching job restarted", week_id=week_id, job_id=job.id, match_type=match_type
            )
            return {
                "success": True,
                "message": "Job restarted",
                "job_id": job.id,
                "status": job.status,
                "progress": {
                    "current": job.progress_current,
                    "total": job.progress_total,
                },
            }
        except Exception as exc:
            logger.exception(
                "Failed to restart matching job",
                week_id=week_id,
                match_type=match_type,
                error=str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to restart matching job: {exc}",
            )

    @router.post("/fetch", response_model=dict[str, Any])
    async def fetch_releases(
        fetch_request: FetchReleasesRequest = Body(...),
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Fetch releases from a source."""
        logger.info(
            "Fetching releases", source=fetch_request.source, week_start=fetch_request.week_start
        )

        # Parse week_start if provided
        week_start_date: datetime.date | None = None
        if fetch_request.week_start:
            try:
                week_start_date = datetime.date.fromisoformat(fetch_request.week_start)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid week_start format: {fetch_request.week_start}. Expected YYYY-MM-DD",
                )

        # Fetch releases based on source
        try:
            if fetch_request.source == "previewsworld":
                releases = await fetch_previewsworld_releases(week_start_date)
            elif fetch_request.source == "comicgeeks":
                releases = await fetch_comicgeeks_releases(week_start_date)
            elif fetch_request.source == "readcomicsonline":
                releases = await fetch_readcomicsonline_releases(week_start_date)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown source: {fetch_request.source}. Valid sources: previewsworld, comicgeeks, readcomicsonline",
                )
        except Exception as exc:
            logger.exception(
                "Failed to fetch releases", source=fetch_request.source, error=str(exc)
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch releases: {exc}",
            )

        if not releases:
            return {
                "success": True,
                "message": f"No releases found from {fetch_request.source}",
                "count": 0,
            }

        # Determine week_start from first release or use provided/default
        if week_start_date:
            week_start_iso = week_start_date.isoformat()
        elif releases and releases[0].get("release_date"):
            week_start_iso = releases[0]["release_date"]
        else:
            # Use current week (Wednesday)
            base = datetime.datetime.now(datetime.UTC)
            weekday = base.weekday()
            if weekday < 2:  # Monday or Tuesday
                days_to_subtract = weekday + 5
            else:  # Wednesday or later
                days_to_subtract = weekday - 2
            wednesday = base - datetime.timedelta(days=days_to_subtract)
            week_start_iso = wednesday.date().isoformat()

        # Get or create week
        week = await get_or_create_week(session, week_start_iso)

        # Store releases
        stored_count = await store_releases(
            session,
            week,
            week_start_iso,
            releases,
            fetch_request.source,
        )

        return {
            "success": True,
            "message": f"Fetched and stored {stored_count} releases from {fetch_request.source}",
            "count": stored_count,
            "week_id": week.id,
            "week_start": week_start_iso,
        }

    return router
