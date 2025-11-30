"""Background job processor for import scanning."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.database import get_global_session_factory, retry_db_operation
from comicarr.core.import_scan import (
    _collect_comic_files,
    _extract_series_from_filename,
    _match_file_to_library,
    scan_folder_for_import,
)
from comicarr.db.models import (
    ImportJob,
    ImportScanningJob,
    IncludePath,
    Library,
    LibraryIssue,
    LibraryVolume,
)

logger = structlog.get_logger("comicarr.import.scanning_job_processor")


async def _count_files_that_will_create_entries(
    folders: list[Path],
    library_id: str,
    session: SQLModelAsyncSession,
) -> int:
    """Count files that will create ImportPendingFile entries (excluding files already in library).

    This does a quick pre-check without ComicVine search to estimate progress_total.
    We only count files that:
    - Can be parsed (have series/issue)
    - Don't match to library issues that already have files

    Args:
        folders: List of folder paths to scan
        library_id: Library ID to check against
        session: Database session

    Returns:
        Estimated count of files that will create ImportPendingFile entries
    """
    count = 0

    # Get all library issues for quick lookup
    issues_result = await session.exec(
        select(LibraryIssue).where(
            col(LibraryIssue.volume_id).in_(
                select(LibraryVolume.id).where(LibraryVolume.library_id == library_id)
            )
        )
    )
    library_issues = {issue.id: issue for issue in issues_result.all()}

    for folder in folders:
        files = await asyncio.to_thread(_collect_comic_files, folder)

        for file_path in files:
            try:
                file_name = file_path.name
                # Quick extract (no ComicVine search)
                series_name, issue_number, year, month, volume = _extract_series_from_filename(
                    file_name
                )

                # If we can't extract metadata, we'll still create an entry (for user review)
                if not series_name or not issue_number:
                    count += 1
                    continue

                # Quick library match check
                stem = file_path.stem
                matched_volume_id, matched_issue_id, confidence = await _match_file_to_library(
                    file_path, stem, series_name, issue_number, session
                )

                # If matched to library and issue has file, skip (won't create entry)
                if matched_volume_id and matched_issue_id:
                    if matched_issue_id in library_issues:
                        issue = library_issues[matched_issue_id]
                        if issue.file_path and issue.file_path.strip():
                            # Issue already has file, will be skipped
                            continue

                # This file will create an ImportPendingFile entry
                count += 1
            except Exception as e:
                # If we can't process the file, we'll still try to create an entry
                logger.debug(
                    "Error during pre-check, will still create entry",
                    file_path=str(file_path),
                    error=str(e),
                )
                count += 1

    return count


async def process_import_scanning_job(
    session: SQLModelAsyncSession,
    job_id: str,
) -> None:
    """Process an import scanning job.

    This function runs the actual scanning work and updates job status/progress.
    Only counts files that will create ImportPendingFile entries (excludes files already in library).

    Args:
        session: Database session
        job_id: Scanning job ID to process
    """
    # Load job
    job_result = await session.exec(select(ImportScanningJob).where(ImportScanningJob.id == job_id))
    job = job_result.one_or_none()
    if not job:
        logger.error("Scanning job not found", job_id=job_id)
        return

    # Check if already completed, cancelled, or paused
    if job.status in ("completed", "failed", "cancelled"):
        logger.warning("Job already finished", job_id=job_id, status=job.status)
        return

    # If paused, wait until resumed
    if job.status == "paused":
        logger.info("Job is paused, waiting for resume", job_id=job_id)
        max_wait_time = 3600  # Wait up to 1 hour
        wait_start = time.time()
        while job.status == "paused" and (time.time() - wait_start) < max_wait_time:
            await asyncio.sleep(1)
            await session.refresh(job)

        if job.status != "paused":
            logger.info("Job resumed", job_id=job_id, new_status=job.status)
        else:
            logger.warning("Job still paused after max wait time", job_id=job_id)
            return

    # Load import job
    import_job_result = await session.exec(
        select(ImportJob).where(ImportJob.id == job.import_job_id)
    )
    import_job = import_job_result.one_or_none()
    if not import_job:
        job.status = "failed"
        job.error = f"Import job {job.import_job_id} not found"
        job.completed_at = int(time.time())
        await session.commit()
        logger.error("Import job not found", job_id=job_id, import_job_id=job.import_job_id)
        return

    # Get library
    library_result = await session.exec(select(Library).where(Library.id == import_job.library_id))
    library = library_result.one_or_none()
    if not library:
        job.status = "failed"
        job.error = "Library not found"
        job.completed_at = int(time.time())
        await session.commit()
        logger.error("Library not found", job_id=job_id, library_id=import_job.library_id)
        return

    library_root = Path(library.library_root)
    if not library_root.exists():
        job.status = "failed"
        job.error = f"Library root does not exist: {library_root}"
        job.completed_at = int(time.time())
        await session.commit()
        return

    # Determine folders to scan
    folders_to_scan: list[Path] = []

    if import_job.scan_type == "root_folders":
        include_paths_result = await session.exec(
            select(IncludePath).where(
                IncludePath.library_id == import_job.library_id,
                IncludePath.enabled == True,
            )
        )
        include_paths = include_paths_result.all()

        if include_paths:
            for include_path in include_paths:
                include_path_obj = Path(include_path.path)
                if include_path_obj.exists() and include_path_obj.is_dir():
                    try:
                        include_path_obj.resolve().relative_to(library_root.resolve())
                        folders_to_scan.append(include_path_obj)
                    except ValueError:
                        logger.warning(
                            "Include path outside library root",
                            include_path=str(include_path_obj),
                            library_root=str(library_root),
                        )
        else:
            folders_to_scan.append(library_root)

    elif import_job.scan_type == "external_folder":
        if import_job.folder_path:
            folder_path = Path(import_job.folder_path)
            if folder_path.exists() and folder_path.is_dir():
                folders_to_scan.append(folder_path)
            else:
                job.status = "failed"
                job.error = f"External folder does not exist: {import_job.folder_path}"
                job.completed_at = int(time.time())
                await session.commit()
                return
        else:
            job.status = "failed"
            job.error = "folder_path is required for external_folder scans"
            job.completed_at = int(time.time())
            await session.commit()
            return

    if not folders_to_scan:
        job.status = "completed"
        job.progress_current = 0
        job.progress_total = 0
        job.completed_at = int(time.time())
        await session.commit()
        logger.info("No folders to scan", job_id=job_id)
        return

    # Count files that will create ImportPendingFile entries (excluding files already in library)
    logger.info(
        "Counting files that will create entries", job_id=job_id, folders_count=len(folders_to_scan)
    )
    estimated_total = await _count_files_that_will_create_entries(
        folders_to_scan,
        import_job.library_id,
        session,
    )

    # Update job status and progress
    job.status = "processing"
    job.progress_total = estimated_total
    job.progress_current = 0
    job.started_at = int(time.time())
    await session.commit()

    logger.info("Starting scanning job", job_id=job_id, estimated_total=estimated_total)

    # Scan each folder
    session_factory = get_global_session_factory()
    total_created = 0
    errors = 0
    error_messages: list[str] = []

    try:
        for folder in folders_to_scan:
            logger.info("Scanning folder", folder=str(folder), job_id=job_id)

            if session_factory:
                async with session_factory() as folder_session:
                    files_created = await scan_folder_for_import(
                        folder,
                        import_job.id,
                        folder_session,
                        scanning_job_id=job.id,
                        update_progress=True,  # Update progress via scanning job
                    )
                    total_created += files_created

                    # Refresh and update progress in the scanning job
                    await session.refresh(job)
                    job.progress_current = total_created
                    job.updated_at = int(time.time())
                    await retry_db_operation(
                        lambda: session.commit(),
                        session=session,
                        operation_type="update_scanning_progress",
                    )
            else:
                logger.warning("No session factory available for scanning", job_id=job_id)

        # Mark job as completed
        job.status = "completed"
        job.completed_at = int(time.time())
        job.progress_current = total_created
        job.updated_at = int(time.time())

        # Update import job status
        await session.refresh(import_job)
        import_job.status = "pending_review"
        import_job.updated_at = int(time.time())

        await retry_db_operation(
            lambda: session.commit(),
            session=session,
            operation_type="complete_scanning_job",
        )

        logger.info(
            "Scanning job completed",
            job_id=job_id,
            created=total_created,
            total=job.progress_total,
            errors=errors,
        )

    except Exception as exc:
        logger.error("Scanning job failed", job_id=job_id, error=str(exc), exc_info=True)
        job.status = "failed"
        job.error = str(exc)
        job.error_count = errors
        job.completed_at = int(time.time())
        await retry_db_operation(
            lambda: session.commit(),
            session=session,
            operation_type="fail_scanning_job",
        )
