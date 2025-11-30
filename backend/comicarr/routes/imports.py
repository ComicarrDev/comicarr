"""Import routes for managing issue imports."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.database import get_global_session_factory
from comicarr.core.dependencies import require_auth
from comicarr.core.import_scanning_job_processor import process_import_scanning_job
from comicarr.core.utils import calculate_pending_file_counts
from comicarr.db.models import ImportJob, ImportPendingFile, ImportProcessingJob, ImportScanningJob

logger = structlog.get_logger("comicarr.routes.imports")


async def _update_job_counts(job_id: str, session: SQLModelAsyncSession) -> None:
    """Update job counts based on current pending file statuses."""
    from sqlmodel import select

    pending_files_result = await session.exec(
        select(ImportPendingFile).where(ImportPendingFile.import_job_id == job_id)
    )
    pending_files = pending_files_result.all()

    # Use shared function to calculate counts consistently
    counts = calculate_pending_file_counts(list(pending_files))

    job_result = await session.exec(select(ImportJob).where(ImportJob.id == job_id))
    job = job_result.one_or_none()
    if job:
        # Map new counts to legacy fields for backwards compatibility
        job.matched_count = counts["library_match"] + counts["comicvine_match"]
        job.unmatched_count = (
            counts["total"]
            - counts["library_match"]
            - counts["comicvine_match"]
            - counts["skipped"]
        )
        job.approved_count = counts["import"]  # "import" status replaces "approved"
        job.skipped_count = counts["skipped"]
        job.updated_at = int(time.time())
        session.add(job)
        await session.commit()


# Request/Response Models
class ImportJobResponse(BaseModel):
    """Import job response model."""

    id: str
    library_id: str
    scan_type: str
    folder_path: str | None
    link_files: bool
    status: str
    scanned_files: int
    total_files: int
    processed_files: int
    matched_count: int
    unmatched_count: int
    approved_count: int
    skipped_count: int
    error: str | None
    created_at: int
    updated_at: int
    completed_at: int | None


class ImportJobCreate(BaseModel):
    """Request model for creating an import job."""

    library_id: str = Field(..., description="Target library ID for import")
    scan_type: str = Field(..., description="Type of scan: 'root_folders' or 'external_folder'")
    folder_path: str | None = Field(
        default=None, description="Folder path for external_folder scans"
    )
    link_files: bool = Field(default=False, description="Link files instead of moving them")


class ImportJobListResponse(BaseModel):
    """Response model for listing import jobs."""

    jobs: list[ImportJobResponse]
    total: int


class ImportPendingFileResponse(BaseModel):
    """Import pending file response model."""

    id: str
    import_job_id: str
    file_path: str
    file_name: str
    file_size: int
    file_extension: str
    status: str
    matched_volume_id: str | None
    matched_issue_id: str | None
    matched_confidence: float | None
    comicvine_volume_id: int | None
    comicvine_issue_id: int | None
    comicvine_volume_name: str | None
    comicvine_issue_name: str | None
    comicvine_issue_number: str | None
    comicvine_issue_image: str | None
    comicvine_confidence: float | None
    cv_search_query: str | None
    cv_results_count: int | None
    cv_results_sample: str | None
    action: str | None
    target_volume_id: str | None
    target_issue_id: str | None
    preview_rename_to: str | None
    preview_convert_to: str | None
    preview_metatag: bool
    extracted_series: str | None
    extracted_issue_number: str | None
    extracted_year: int | None
    notes: str | None
    created_at: int
    updated_at: int


class ImportPendingFileListResponse(BaseModel):
    """Response model for listing import pending files."""

    pending_files: list[ImportPendingFileResponse]
    total: int
    library_match: int  # Files with library match (matched_volume_id or matched_issue_id)
    comicvine_match: int  # Files with ComicVine match (comicvine_volume_id or comicvine_issue_id)
    pending: int  # Status: pending
    import_count: int = Field(
        alias="import", serialization_alias="import"
    )  # Status: import (queued for import)
    skipped: int  # Status: skipped

    model_config = {"populate_by_name": True}  # Allow both field name and alias


class ImportPendingFileUpdate(BaseModel):
    """Request model for updating an import pending file."""

    status: str | None = Field(default=None, description="Pending file status")
    action: str | None = Field(
        default=None, description="Action to take: 'link', 'create_volume', 'skip', 'move'"
    )
    target_volume_id: str | None = Field(
        default=None, description="Target volume ID for manual match"
    )
    target_issue_id: str | None = Field(
        default=None, description="Target issue ID for manual match"
    )
    notes: str | None = Field(default=None, description="Notes about this pending file")


class ImportPendingFileMatch(BaseModel):
    """Request model for matching an import pending file to a ComicVine volume."""

    comicvine_volume_id: int = Field(..., description="ComicVine volume ID to match to")
    action: str = Field(
        default="create_volume", description="Action to take: 'link' or 'create_volume'"
    )


class ImportProcessPreviewResponse(BaseModel):
    """Response model for import processing preview."""

    total_files: int = Field(..., description="Total approved files to process")
    volumes_to_create: int = Field(..., description="Number of new volumes that will be created")
    files_to_move: int = Field(..., description="Number of files that will be moved")
    files_to_link: int = Field(..., description="Number of files that will be linked")
    existing_volumes: int = Field(..., description="Number of files going to existing volumes")


def create_imports_router(
    get_db_session: Callable[[], AsyncIterator[SQLModelAsyncSession]],
) -> APIRouter:
    """Create imports router with database dependency.

    Args:
        get_db_session: Dependency function for database sessions

    Returns:
        Configured APIRouter instance
    """
    router = APIRouter(prefix="/api/import", tags=["import"])

    @router.post("/jobs", response_model=ImportJobResponse, status_code=status.HTTP_201_CREATED)
    async def create_import_job(
        job_data: ImportJobCreate,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> ImportJobResponse:
        """Create a new import job."""
        if job_data.scan_type not in ("root_folders", "external_folder"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="scan_type must be 'root_folders' or 'external_folder'",
            )

        if job_data.scan_type == "external_folder" and not job_data.folder_path:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="folder_path is required for external_folder scans",
            )

        # Verify library exists
        from comicarr.db.models import Library

        library_result = await session.exec(
            select(Library).where(Library.id == job_data.library_id)
        )
        library = library_result.one_or_none()
        if not library:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library not found")

        # Create import job
        import_job = ImportJob(
            library_id=job_data.library_id,
            scan_type=job_data.scan_type,
            folder_path=job_data.folder_path,
            link_files=job_data.link_files,
            status="scanning",
        )

        session.add(import_job)
        await session.commit()
        await session.refresh(import_job)

        logger.info("Created import job", job_id=import_job.id, scan_type=job_data.scan_type)

        # Create ImportScanningJob
        from comicarr.db.models import ImportScanningJob

        scanning_job = ImportScanningJob(
            import_job_id=import_job.id,
            status="queued",
        )
        session.add(scanning_job)
        await session.commit()
        await session.refresh(scanning_job)

        # Start background scanning task
        session_factory = get_global_session_factory()
        if session_factory:

            async def run_scanning_job(job_id: str):
                async with session_factory() as bg_session:  # type: ignore[misc]
                    await process_import_scanning_job(bg_session, job_id)

            asyncio.create_task(run_scanning_job(scanning_job.id))
        else:
            logger.error(
                "Session factory not available, cannot start background scan", job_id=import_job.id
            )

        return ImportJobResponse.model_validate(import_job, from_attributes=True)

    @router.get("/jobs", response_model=ImportJobListResponse)
    async def list_import_jobs(
        status_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> ImportJobListResponse:
        """List import jobs."""
        query = select(ImportJob)

        if status_filter:
            query = query.where(ImportJob.status == status_filter)

        query = query.order_by(col(ImportJob.created_at).desc()).limit(limit).offset(offset)

        result = await session.exec(query)
        jobs = result.all()

        # Get total count
        from sqlmodel import func

        count_query = select(func.count())
        if status_filter:
            count_query = count_query.where(ImportJob.status == status_filter)
        total_result = await session.exec(count_query)
        total = total_result.one()

        return ImportJobListResponse(
            jobs=[ImportJobResponse.model_validate(job, from_attributes=True) for job in jobs],
            total=total,
        )

    @router.get("/jobs/{job_id}", response_model=ImportJobResponse)
    async def get_import_job(
        job_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> ImportJobResponse:
        """Get import job details."""
        result = await session.exec(select(ImportJob).where(ImportJob.id == job_id))
        job = result.one_or_none()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found"
            )

        return ImportJobResponse.model_validate(job, from_attributes=True)

    @router.get("/jobs/{job_id}/pending-files", response_model=ImportPendingFileListResponse)
    async def list_import_pending_files(
        job_id: str,
        status_filter: str | None = None,
        limit: int = 100,
        offset: int = 0,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> ImportPendingFileListResponse:
        """List pending files for an import job."""
        # Verify job exists
        job_result = await session.exec(select(ImportJob).where(ImportJob.id == job_id))
        job = job_result.one_or_none()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found"
            )

        query = select(ImportPendingFile).where(ImportPendingFile.import_job_id == job_id)

        if status_filter:
            query = query.where(ImportPendingFile.status == status_filter)

        query = query.order_by(col(ImportPendingFile.created_at).desc()).limit(limit).offset(offset)

        result = await session.exec(query)
        pending_files = result.all()

        # Refresh file sizes from disk for all pending files
        from pathlib import Path

        updated_count = 0
        for pf in pending_files:
            try:
                file_path = Path(pf.file_path)
                # Try to resolve the path in case it's relative or has symlinks
                if not file_path.is_absolute():
                    # If relative, we can't resolve it - skip
                    logger.debug(
                        "Skipping file size refresh for relative path",
                        pending_file_id=pf.id,
                        file_path=pf.file_path,
                    )
                    continue

                resolved_path = file_path.resolve()
                if resolved_path.exists():
                    new_size = resolved_path.stat().st_size
                    if new_size != pf.file_size:
                        logger.debug(
                            "Updating file size from disk",
                            pending_file_id=pf.id,
                            old_size=pf.file_size,
                            new_size=new_size,
                            file_path=str(resolved_path),
                        )
                        pf.file_size = new_size
                        session.add(pf)
                        updated_count += 1
                else:
                    logger.warning(
                        "File not found for size refresh",
                        pending_file_id=pf.id,
                        file_path=str(resolved_path),
                    )
            except Exception as exc:
                logger.warning(
                    "Failed to refresh file size",
                    pending_file_id=pf.id,
                    file_path=pf.file_path,
                    error=str(exc),
                )

        if updated_count > 0:
            await session.commit()
            logger.debug(
                "Refreshed file sizes", updated_count=updated_count, total_files=len(pending_files)
            )
            # Re-fetch to get updated sizes
            result = await session.exec(query)
            pending_files = result.all()

        # Get counts
        all_pending_files_result = await session.exec(
            select(ImportPendingFile).where(ImportPendingFile.import_job_id == job_id)
        )
        all_pending_files = all_pending_files_result.all()

        # Use shared function to calculate counts consistently
        counts = calculate_pending_file_counts(list(all_pending_files))

        return ImportPendingFileListResponse(
            pending_files=[
                ImportPendingFileResponse.model_validate(c, from_attributes=True)
                for c in pending_files
            ],
            total=counts["total"],
            library_match=counts["library_match"],
            comicvine_match=counts["comicvine_match"],
            pending=counts["pending"],
            import_count=counts["import"],  # type: ignore[arg-type]  # alias="import" works with populate_by_name=True
            skipped=counts["skipped"],
        )

    @router.put(
        "/jobs/{job_id}/pending-files/{pending_file_id}", response_model=ImportPendingFileResponse
    )
    async def update_import_pending_file(
        job_id: str,
        pending_file_id: str,
        update_data: ImportPendingFileUpdate,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> ImportPendingFileResponse:
        """Update an import pending file."""
        # Verify job exists
        job_result = await session.exec(select(ImportJob).where(ImportJob.id == job_id))
        job = job_result.one_or_none()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found"
            )

        # Get pending file
        pending_file_result = await session.exec(
            select(ImportPendingFile).where(
                ImportPendingFile.id == pending_file_id,
                ImportPendingFile.import_job_id == job_id,
            )
        )
        pending_file = pending_file_result.one_or_none()

        if not pending_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Import pending file not found (id: {pending_file_id}, job_id: {job_id})",
            )

        # Update pending file
        if update_data.status is not None:
            pending_file.status = update_data.status

        # Handle action update - check if action field was provided in the request
        # We need to distinguish between "not provided" (don't update) and "explicitly None" (clear action)
        # Use model_dump(exclude_unset=True) to check if the field was explicitly set
        update_dict = update_data.model_dump(exclude_unset=True)
        if "action" in update_dict:
            pending_file.action = update_data.action
            # Ensure status is set correctly when action is "skip"
            if update_data.action == "skip" and (
                update_data.status is None or update_data.status != "skipped"
            ):
                pending_file.status = "skipped"
            # Ensure status is set correctly when action is "link" and status is "approved"
            elif update_data.action == "link" and update_data.status == "import":
                pending_file.status = "import"
        if update_data.target_volume_id is not None:
            pending_file.target_volume_id = update_data.target_volume_id
        if update_data.target_issue_id is not None:
            pending_file.target_issue_id = update_data.target_issue_id
        if update_data.notes is not None:
            pending_file.notes = update_data.notes

        pending_file.updated_at = int(time.time())

        # Refresh file size from disk in case file was updated
        try:
            from pathlib import Path

            file_path = Path(pending_file.file_path)
            if not file_path.is_absolute():
                logger.debug(
                    "Skipping file size refresh for relative path",
                    pending_file_id=pending_file_id,
                    file_path=pending_file.file_path,
                )
            else:
                resolved_path = file_path.resolve()
                if resolved_path.exists():
                    new_size = resolved_path.stat().st_size
                    if new_size != pending_file.file_size:
                        logger.info(
                            "File size changed, updating",
                            pending_file_id=pending_file_id,
                            old_size=pending_file.file_size,
                            new_size=new_size,
                            file_path=str(resolved_path),
                        )
                        pending_file.file_size = new_size
                else:
                    logger.warning(
                        "File not found for size refresh",
                        pending_file_id=pending_file_id,
                        file_path=str(resolved_path),
                    )
        except Exception as size_exc:
            logger.warning(
                "Failed to refresh file size",
                pending_file_id=pending_file_id,
                file_path=pending_file.file_path,
                error=str(size_exc),
                exc_info=True,
            )

        # session.add() is synchronous, not async
        session.add(pending_file)
        await session.commit()
        await session.refresh(pending_file)

        # Update job counts to reflect the change
        await _update_job_counts(job_id, session)

        logger.info("Updated import pending file", job_id=job_id, pending_file_id=pending_file_id)

        return ImportPendingFileResponse.model_validate(pending_file, from_attributes=True)

    @router.get("/jobs/{job_id}/preview", response_model=ImportProcessPreviewResponse)
    async def preview_import_job(
        job_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> ImportProcessPreviewResponse:
        """Preview what will happen when processing an import job."""
        from comicarr.db.models import LibraryVolume

        # Verify job exists
        job_result = await session.exec(select(ImportJob).where(ImportJob.id == job_id))
        job = job_result.one_or_none()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found"
            )

        # Get approved pending files
        approved_files_result = await session.exec(
            select(ImportPendingFile).where(
                ImportPendingFile.import_job_id == job_id, ImportPendingFile.status == "import"
            )
        )
        approved_files = approved_files_result.all()

        if not approved_files:
            return ImportProcessPreviewResponse(
                total_files=0,
                volumes_to_create=0,
                files_to_move=0,
                files_to_link=0,
                existing_volumes=0,
            )

        # Count volumes to create (files with ComicVine volume ID but no matched volume)
        volumes_to_create = set()
        existing_volumes = set()
        files_to_move = 0
        files_to_link = 0

        for pending_file in approved_files:
            # Determine if volume needs to be created
            target_volume_id = pending_file.target_volume_id or pending_file.matched_volume_id

            if pending_file.comicvine_volume_id and not target_volume_id:
                volumes_to_create.add(pending_file.comicvine_volume_id)
            elif target_volume_id:
                # Check if volume exists
                volume = await session.get(LibraryVolume, target_volume_id)
                if volume:
                    existing_volumes.add(target_volume_id)

            # Determine if file will be moved or linked
            # Priority: 1) pending_file.action override, 2) job.link_files setting
            should_link = False
            if pending_file.action == "link":
                should_link = True
            elif pending_file.action == "move":
                should_link = False
            else:
                # Respect job.link_files setting
                should_link = job.link_files

            # Count files to move vs link
            # For root_folders scans: files are already in library root, so we always "link"
            # (update file_path in database) regardless of link_files setting, since moving doesn't make sense.
            # For external_folder scans: respect link_files setting - True = create symlink, False = move.
            if job.scan_type == "root_folders":
                # Root folders: always register in database (files are already in place)
                files_to_link += 1
            elif should_link:
                # External folder with linking enabled - will create symbolic links
                files_to_link += 1
            else:
                # External folder with linking disabled - will move files
                files_to_move += 1

        return ImportProcessPreviewResponse(
            total_files=len(approved_files),
            volumes_to_create=len(volumes_to_create),
            files_to_move=files_to_move,
            files_to_link=files_to_link,
            existing_volumes=len(existing_volumes),
        )

    @router.post("/jobs/{job_id}/process", response_model=ImportJobResponse)
    async def process_import_job(
        job_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> ImportJobResponse:
        """Process approved pending_files in an import job."""
        # Verify job exists
        job_result = await session.exec(select(ImportJob).where(ImportJob.id == job_id))
        job = job_result.one_or_none()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found"
            )

        if job.status not in ("pending_review", "scanning"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot process job with status: {job.status}",
            )

        # Get approved pending files
        approved_files_result = await session.exec(
            select(ImportPendingFile).where(
                ImportPendingFile.import_job_id == job_id, ImportPendingFile.status == "import"
            )
        )
        approved_files = approved_files_result.all()

        if not approved_files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No approved files to process. Please approve some files first.",
            )

        # Start background processing task
        job.status = "processing"
        job.updated_at = int(time.time())
        session.add(job)
        await session.commit()
        await session.refresh(job)

        # Create ImportProcessingJob
        try:
            from comicarr.db.models import ImportProcessingJob

            logger.info("Creating ImportProcessingJob", job_id=job_id)
            processing_job = ImportProcessingJob(
                import_job_id=job.id,
                status="queued",
            )
            session.add(processing_job)
            await session.commit()
            await session.refresh(processing_job)
            logger.info(
                "Created ImportProcessingJob",
                job_id=job_id,
                processing_job_id=processing_job.id,
                status=processing_job.status,
            )
        except Exception as exc:
            logger.exception(
                "Failed to create ImportProcessingJob", job_id=job_id, error=str(exc), exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create processing job: {exc}",
            )

        # Start background task to process files
        try:
            from comicarr.core.database import get_global_session_factory
            from comicarr.core.import_processing_job_processor import process_import_processing_job

            session_factory = get_global_session_factory()
            if session_factory:
                # Use asyncio.create_task to run in background
                import asyncio

                async def run_processing_job(job_id: str):
                    try:
                        logger.info("Background processing task started", processing_job_id=job_id)
                        async with session_factory() as bg_session:  # type: ignore[misc]
                            await process_import_processing_job(bg_session, job_id)
                        logger.info(
                            "Background processing task completed", processing_job_id=job_id
                        )
                    except Exception as exc:
                        logger.exception(
                            "Error in background processing job",
                            processing_job_id=job_id,
                            error=str(exc),
                            exc_info=True,
                        )

                task = asyncio.create_task(run_processing_job(processing_job.id))
                logger.info(
                    "Started background processing task",
                    job_id=job_id,
                    processing_job_id=processing_job.id,
                    approved_files_count=len(approved_files),
                    task_done=task.done(),
                )
            else:
                logger.error("Global session factory not set, cannot start background processing")
                job.status = "pending_review"
                job.error = "Failed to start processing: database session unavailable"
                session.add(job)
                await session.commit()
                await session.refresh(job)
        except Exception as exc:
            logger.exception(
                "Failed to start background processing task", job_id=job_id, error=str(exc)
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to start processing: {exc}",
            )

        return ImportJobResponse.model_validate(job, from_attributes=True)

    @router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_import_job(
        job_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> None:
        """Cancel/delete an import job."""
        job_result = await session.exec(select(ImportJob).where(ImportJob.id == job_id))
        job = job_result.one_or_none()

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found"
            )

        # Cancel job if it's still running
        if job.status in ("scanning", "pending_review", "processing"):
            job.status = "cancelled"
            job.updated_at = int(time.time())
            session.add(job)
            await session.commit()
            await session.refresh(job)

        # Delete pending_files - use exec() to select, then delete individually
        pending_files_result = await session.exec(
            select(ImportPendingFile).where(ImportPendingFile.import_job_id == job_id)
        )
        pending_files = pending_files_result.all()
        for pending_file in pending_files:
            await session.delete(pending_file)

        # Delete job
        job_to_delete = await session.get(ImportJob, job_id)
        if job_to_delete:
            await session.delete(job_to_delete)

        await session.commit()

        logger.info("Deleted import job", job_id=job_id)

    @router.post("/pending-files/{pending_file_id}/match", response_model=ImportPendingFileResponse)
    async def match_import_pending_file(
        pending_file_id: str,
        match_data: ImportPendingFileMatch,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> ImportPendingFileResponse:
        """Match an import pending file to a ComicVine volume."""
        from comicarr.routes.comicvine import fetch_comicvine, normalize_comicvine_payload
        from comicarr.routes.settings import _get_external_apis

        # Get pending file
        pending_file_result = await session.exec(
            select(ImportPendingFile).where(ImportPendingFile.id == pending_file_id)
        )
        pending_file = pending_file_result.one_or_none()

        if not pending_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Import pending file not found"
            )

        # Update pending file with ComicVine volume
        pending_file.comicvine_volume_id = match_data.comicvine_volume_id
        pending_file.action = match_data.action
        pending_file.comicvine_match_type = "manual"  # Manual selection
        pending_file.status = "import"  # Queued for import

        # Fetch volume details from ComicVine to populate name
        external_apis = _get_external_apis()
        normalized = normalize_comicvine_payload(external_apis["comicvine"])

        if normalized.get("enabled") and normalized.get("api_key"):
            try:
                # Extract resource prefix and ID
                volume_id_str = f"4050-{match_data.comicvine_volume_id}"
                volume_payload = await fetch_comicvine(
                    normalized,
                    f"volume/{volume_id_str}",
                    {"field_list": "id,name,start_year,publisher,site_detail_url,image"},
                )

                volume_data = volume_payload.get("results")
                if volume_data:
                    pending_file.comicvine_volume_name = volume_data.get("name")
            except Exception as exc:
                logger.warning(
                    "Failed to fetch ComicVine volume details",
                    volume_id=match_data.comicvine_volume_id,
                    error=str(exc),
                )

        pending_file.updated_at = int(time.time())

        session.add(pending_file)
        await session.commit()
        await session.refresh(pending_file)

        logger.info(
            "Matched import pending file to ComicVine volume",
            pending_file_id=pending_file_id,
            comicvine_volume_id=match_data.comicvine_volume_id,
        )

        return ImportPendingFileResponse.model_validate(pending_file, from_attributes=True)

    @router.get("/pending-files/{pending_file_id}/cover-image")
    async def get_import_candidate_cover_image(
        pending_file_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ):
        """Serve cover image extracted from the comic file."""
        import io
        import zipfile
        from pathlib import Path

        from fastapi.responses import StreamingResponse

        from comicarr.core.utils import MIN_COMIC_FILE_SIZE

        logger.info(
            "Cover image request received",
            pending_file_id=pending_file_id,
        )

        candidate_result = await session.exec(
            select(ImportPendingFile).where(ImportPendingFile.id == pending_file_id)
        )
        candidate = candidate_result.one_or_none()

        if not candidate:
            logger.warning(
                "Import candidate not found for cover image",
                pending_file_id=pending_file_id,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Import candidate not found"
            )

        # Skip cover extraction for suspiciously small files (likely corrupted)
        if candidate.file_size < MIN_COMIC_FILE_SIZE:
            logger.debug(
                "Skipping cover extraction for suspiciously small file",
                pending_file_id=pending_file_id,
                file_size=candidate.file_size,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cover image not available (file may be corrupted)",
            )

        file_path = Path(candidate.file_path)

        # Resolve path - handle both absolute and relative paths
        if file_path.is_absolute():
            resolved_path = file_path.resolve()
        else:
            # For relative paths, resolve from current working directory
            resolved_path = file_path.resolve()

        logger.debug(
            "Extracting cover image",
            pending_file_id=pending_file_id,
            file_path=candidate.file_path,
            resolved_path=str(resolved_path),
            exists=resolved_path.exists(),
        )

        if not resolved_path.exists():
            logger.warning(
                "Cover image file not found",
                pending_file_id=pending_file_id,
                file_path=candidate.file_path,
                resolved_path=str(resolved_path),
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found: {candidate.file_path}",
            )

        ext = resolved_path.suffix.lower()

        # Extract first image from archive using the same utilities as reading.py
        try:
            from comicarr.routes.reading import _get_pages_from_archive

            # Get sorted list of image files from archive
            image_files = _get_pages_from_archive(resolved_path)

            if not image_files:
                logger.warning(
                    "No image found in archive",
                    pending_file_id=pending_file_id,
                    file_path=str(resolved_path),
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="No image found in archive"
                )

            # Get the first image (cover)
            cover_image = image_files[0]

            logger.debug(
                "Selected cover image",
                pending_file_id=pending_file_id,
                cover_image=cover_image,
                total_images=len(image_files),
            )

            # Extract the image data
            if ext in {".zip", ".cbz"}:
                with zipfile.ZipFile(resolved_path, "r") as zf:
                    image_data = zf.read(cover_image)
            elif ext in {".rar", ".cbr"}:
                import rarfile

                with rarfile.RarFile(str(resolved_path), "r") as rf:
                    image_data = rf.read(cover_image)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported file format: {ext}",
                )

            # Determine content type from extension
            from pathlib import Path

            image_ext = Path(cover_image).suffix.lower()
            content_type = "image/jpeg"  # default
            if image_ext == ".png":
                content_type = "image/png"
            elif image_ext == ".gif":
                content_type = "image/gif"
            elif image_ext == ".webp":
                content_type = "image/webp"
            elif image_ext == ".bmp":
                content_type = "image/bmp"

            return StreamingResponse(
                io.BytesIO(image_data),
                media_type=content_type,
                headers={"Cache-Control": "public, max-age=3600"},
            )
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error(
                "Error extracting cover image",
                error=str(e),
                pending_file_id=pending_file_id,
                file_path=str(resolved_path),
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error extracting cover: {str(e)}",
            )

    @router.get("/pending-files/{pending_file_id}/cover")
    async def get_import_candidate_cover(
        pending_file_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Get cover image URL for an import candidate (from ComicVine or file)."""
        from pathlib import Path

        from comicarr.core.utils import MIN_COMIC_FILE_SIZE

        candidate_result = await session.exec(
            select(ImportPendingFile).where(ImportPendingFile.id == pending_file_id)
        )
        candidate = candidate_result.one_or_none()

        if not candidate:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Import candidate not found"
            )

        # Return ComicVine issue image if available
        if candidate.comicvine_issue_image:
            return {"image_url": candidate.comicvine_issue_image}

        # Skip cover extraction for suspiciously small files (likely corrupted)
        if candidate.file_size < MIN_COMIC_FILE_SIZE:
            logger.debug(
                "Skipping cover extraction for suspiciously small file",
                pending_file_id=pending_file_id,
                file_size=candidate.file_size,
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cover image not available (file may be corrupted)",
            )

        # Check if file exists
        file_path = Path(candidate.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

        # Return URL to cover image endpoint
        # The frontend will construct the full URL using buildApiUrl
        cover_url = f"/api/import/pending-files/{pending_file_id}/cover-image"
        return {"image_url": cover_url}

    @router.get("/pending-files/{pending_file_id}/issue-cover")
    async def get_issue_cover_for_volume(
        pending_file_id: str,
        volume_id: int = Query(..., description="ComicVine volume ID"),
        issue_number: str = Query(..., description="Issue number"),
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Get ComicVine issue cover image for a specific volume and issue number."""
        from comicarr.core.utils import normalize_issue_number
        from comicarr.routes.comicvine import fetch_comicvine, normalize_comicvine_payload
        from comicarr.routes.settings import _get_external_apis

        candidate_result = await session.exec(
            select(ImportPendingFile).where(ImportPendingFile.id == pending_file_id)
        )
        candidate = candidate_result.one_or_none()

        if not candidate:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Import candidate not found"
            )

        external_apis = _get_external_apis()
        normalized = normalize_comicvine_payload(external_apis["comicvine"])

        if not normalized.get("enabled") or not normalized.get("api_key"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ComicVine integration disabled",
            )

        try:
            # Fetch issues for the volume
            issue_payload = await fetch_comicvine(
                normalized,
                "issues",
                {
                    "filter": f"volume:{volume_id}",
                    "limit": 100,
                    "field_list": "id,name,issue_number,image",
                },
            )

            issue_results = issue_payload.get("results", [])
            normalized_issue_num = normalize_issue_number(issue_number)

            for issue in issue_results:
                issue_num_raw = issue.get("issue_number")
                issue_num = normalize_issue_number(str(issue_num_raw) if issue_num_raw else None)

                if issue_num is not None and normalized_issue_num is not None:
                    if abs(issue_num - normalized_issue_num) < 0.01:
                        # Extract issue image
                        image_data = issue.get("image")
                        if isinstance(image_data, dict):
                            issue_image_url = (
                                image_data.get("super_url")
                                or image_data.get("medium_url")
                                or image_data.get("small_url")
                                or image_data.get("thumb_url")
                            )
                            if issue_image_url:
                                return {"issue_image_url": issue_image_url}

            return {"issue_image_url": None}
        except Exception as exc:
            logger.warning(
                "Failed to fetch issue cover",
                volume_id=volume_id,
                issue_number=issue_number,
                error=str(exc),
            )
            return {"issue_image_url": None}

    @router.post("/pending-files/{pending_file_id}/identify", response_model=dict[str, Any])
    async def identify_pending_file(
        pending_file_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Re-run identification/scraping for a pending file and return diagnostic information.

        Returns detailed information about what was tried and what failed.
        """
        from pathlib import Path

        from comicarr.core.import_scan import (
            _extract_series_from_filename,
            _match_file_to_library,
            _search_comicvine_for_file,
        )

        # Get pending file
        pending_file_result = await session.exec(
            select(ImportPendingFile).where(ImportPendingFile.id == pending_file_id)
        )
        pending_file = pending_file_result.one_or_none()

        if not pending_file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Pending file not found"
            )

        file_path = Path(pending_file.file_path)
        diagnostic_info: dict[str, Any] = {
            "file_name": pending_file.file_name,
            "file_path": pending_file.file_path,
            "steps": [],
            "errors": [],
            "warnings": [],
        }

        try:
            # Step 1: Extract metadata from filename
            step1: dict[str, Any] = {
                "step": "extract_metadata",
                "description": "Extract series name, issue number, year, and month from filename",
            }
            series_name: str | None = None
            issue_number: str | None = None
            year: int | None = None
            month: int | None = None
            volume: str | None = None
            try:
                series_name, issue_number, year_str, month_str, volume = (
                    _extract_series_from_filename(pending_file.file_name)
                )
                # Convert year to int if it's a string
                if year_str is not None:
                    if isinstance(year_str, int):
                        year = year_str
                    elif isinstance(year_str, str) and year_str.isdigit():
                        year = int(year_str)
                # Convert month to int if it's a string
                if month_str is not None:
                    if isinstance(month_str, int):
                        month = month_str
                    elif isinstance(month_str, str) and month_str.isdigit():
                        month = int(month_str)
            except Exception:
                year = None
                month = None
                step1["result"] = {
                    "series_name": series_name,
                    "issue_number": issue_number,
                    "year": year,
                    "month": month,
                    "volume": volume,
                }
                step1["success"] = True
            except Exception as exc:
                step1["success"] = False
                step1["error"] = str(exc)
                diagnostic_info["errors"].append(f"Failed to extract metadata: {exc}")
            diagnostic_info["steps"].append(step1)

            # Step 2: Try to match to library
            step2: dict[str, Any] = {
                "step": "match_to_library",
                "description": "Attempt to match file to existing library volumes/issues",
            }
            if step1.get("success") and series_name and issue_number:
                try:
                    matched_volume_id, matched_issue_id, confidence = await _match_file_to_library(
                        file_path,
                        Path(pending_file.file_name).stem,
                        series_name,
                        issue_number,
                        session,
                    )
                    step2["result"] = {
                        "matched_volume_id": matched_volume_id,
                        "matched_issue_id": matched_issue_id,
                        "confidence": confidence,
                    }
                    step2["success"] = matched_volume_id is not None
                    if not matched_volume_id:
                        step2["reason"] = (
                            "No matching volume/issue found in library - will create new volume on import"
                        )
                        diagnostic_info["warnings"].append(
                            "No existing library volume match - will create new volume on import"
                        )
                except Exception as exc:
                    step2["success"] = False
                    step2["error"] = str(exc)
                    diagnostic_info["errors"].append(f"Library matching failed: {exc}")
            else:
                step2["success"] = False
                step2["reason"] = "Cannot match to library: missing series name or issue number"
                diagnostic_info["warnings"].append(
                    "Skipped library matching: insufficient metadata"
                )
            diagnostic_info["steps"].append(step2)

            # Step 3: Search ComicVine if no library match
            step3: dict[str, Any] = {
                "step": "search_comicvine",
                "description": "Search ComicVine for volume/issue match",
            }
            if (
                step1.get("success")
                and series_name
                and not step2.get("result", {}).get("matched_volume_id")
            ):
                try:
                    comicvine_data = await _search_comicvine_for_file(
                        series_name, issue_number, year, session
                    )
                    if comicvine_data:
                        # Parse results_sample if it's a JSON string, otherwise use as-is
                        results_sample = comicvine_data.get("results_sample")
                        if isinstance(results_sample, str):
                            try:
                                import json as json_module

                                results_sample = json_module.loads(results_sample)
                            except (json_module.JSONDecodeError, TypeError):  # type: ignore[misc]
                                results_sample = None

                        step3["result"] = {
                            "volume_id": comicvine_data.get("volume_id"),
                            "volume_name": comicvine_data.get("volume_name"),
                            "issue_id": comicvine_data.get("issue_id"),
                            "confidence": comicvine_data.get("confidence"),
                            "search_query": comicvine_data.get(
                                "search_query"
                            ),  # Human-readable query
                            "api_query": comicvine_data.get(
                                "api_query"
                            ),  # Exact query sent to ComicVine API
                            "results_count": comicvine_data.get("results_count"),
                            "has_results_sample": bool(results_sample),
                            "results_sample": results_sample,  # Include full results for debugging/volume picker
                        }
                        step3["success"] = comicvine_data.get("volume_id") is not None
                        if not step3["success"]:
                            step3["reason"] = (
                                "ComicVine search returned results but no good match found"
                            )
                            diagnostic_info["warnings"].append(
                                "ComicVine search found results but no match"
                            )
                    else:
                        step3["success"] = False
                        step3["reason"] = "ComicVine search returned no results"
                        diagnostic_info["warnings"].append("No ComicVine results found")
                except Exception as exc:
                    step3["success"] = False
                    step3["error"] = str(exc)
                    diagnostic_info["errors"].append(f"ComicVine search failed: {exc}")
            else:
                step3["success"] = False
                if step2.get("result", {}).get("matched_volume_id"):
                    step3["reason"] = "Skipped ComicVine search: file already matched to library"
                else:
                    step3["reason"] = "Cannot search ComicVine: missing series name"
            diagnostic_info["steps"].append(step3)

            # Summary
            diagnostic_info["summary"] = {
                "metadata_extracted": step1.get("success", False),
                "library_match_found": step2.get("result", {}).get("matched_volume_id") is not None,
                "comicvine_match_found": step3.get("result", {}).get("volume_id") is not None,
                "has_errors": len(diagnostic_info["errors"]) > 0,
                "has_warnings": len(diagnostic_info["warnings"]) > 0,
            }

        except Exception as exc:
            diagnostic_info["errors"].append(f"Unexpected error during identification: {exc}")
            logger.error(
                "Failed to identify pending file",
                pending_file_id=pending_file_id,
                error=str(exc),
                exc_info=True,
            )

        return diagnostic_info

    @router.get("/jobs/{job_id}/scanning/status")
    async def get_scanning_job_status(
        job_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Get the status of the scanning job for an import job.

        Returns the current job status and progress.
        """
        try:
            # Find the most recent scanning job for this import job
            job_result = await session.exec(
                select(ImportScanningJob)
                .where(ImportScanningJob.import_job_id == job_id)
                .order_by(col(ImportScanningJob.created_at).desc())
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
            logger.exception("Failed to get scanning job status", job_id=job_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get scanning job status: {exc}",
            )

    @router.get("/jobs/{job_id}/processing/status")
    async def get_processing_job_status(
        job_id: str,
        session: SQLModelAsyncSession = Depends(get_db_session),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """Get the status of the processing job for an import job.

        Returns the current job status and progress.
        """
        try:
            # Find the most recent processing job for this import job
            job_result = await session.exec(
                select(ImportProcessingJob)
                .where(ImportProcessingJob.import_job_id == job_id)
                .order_by(col(ImportProcessingJob.created_at).desc())
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
            logger.exception("Failed to get processing job status", job_id=job_id, error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get processing job status: {exc}",
            )

    return router
