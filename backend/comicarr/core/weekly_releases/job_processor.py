"""Background job processor for weekly release processing."""

from __future__ import annotations

import asyncio
import time

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.database import get_global_session_factory, retry_db_operation
from comicarr.core.weekly_releases.processing import _create_volume_from_comicvine
from comicarr.db.models import (
    LibraryIssue,
    LibraryVolume,
    WeeklyReleaseItem,
    WeeklyReleaseProcessingJob,
    WeeklyReleaseWeek,
)

logger = structlog.get_logger("comicarr.weekly_releases.job_processor")


async def process_weekly_release_job(
    session: SQLModelAsyncSession,
    job_id: str,
) -> None:
    """Process a weekly release processing job.

    This function runs the actual processing work and updates job status/progress.

    Args:
        session: Database session
        job_id: Job ID to process
    """
    # Load job
    job_result = await session.exec(  # type: ignore[attr-defined]
        select(WeeklyReleaseProcessingJob).where(WeeklyReleaseProcessingJob.id == job_id)
    )
    job = job_result.one_or_none()
    if not job:
        logger.error("Job not found", job_id=job_id)
        return

    # Check if already completed, cancelled, or paused
    if job.status in ("completed", "failed", "cancelled"):
        logger.warning("Job already finished", job_id=job_id, status=job.status)
        return

    # If paused, wait until resumed
    if job.status == "paused":
        logger.info("Job is paused, waiting for resume", job_id=job_id)
        # Wait in a loop checking for status change
        max_wait_time = 3600  # Wait up to 1 hour
        wait_start = time.time()
        while job.status == "paused" and (time.time() - wait_start) < max_wait_time:
            await asyncio.sleep(1)  # Check every second
            await session.refresh(job)

        if job.status != "paused":
            logger.info("Job resumed", job_id=job_id, new_status=job.status)
        else:
            logger.warning("Job still paused after max wait time", job_id=job_id)
            return

    # Load week
    week_result = await session.exec(  # type: ignore[attr-defined]
        select(WeeklyReleaseWeek).where(WeeklyReleaseWeek.id == job.week_id)
    )
    week = week_result.one_or_none()
    if not week:
        job.status = "failed"
        job.error = f"Week {job.week_id} not found"
        job.completed_at = int(time.time())
        await session.commit()
        logger.error("Week not found", job_id=job_id, week_id=job.week_id)
        return

    # Load entries with status "import"
    entries_result = await session.exec(  # type: ignore[attr-defined]
        select(WeeklyReleaseItem)
        .where(WeeklyReleaseItem.week_id == job.week_id)
        .where(WeeklyReleaseItem.status == "import")
    )
    entries = entries_result.all()

    if not entries:
        job.status = "completed"
        job.progress_current = 0
        job.progress_total = 0
        job.completed_at = int(time.time())
        await session.commit()
        logger.info("No entries to process", job_id=job_id)
        return

    # Update job status and progress
    job.status = "processing"
    job.progress_total = len(entries)
    job.progress_current = 0
    job.started_at = int(time.time())
    await session.commit()

    logger.info("Starting job processing", job_id=job_id, total=job.progress_total)

    # Initialize error tracking variables early
    processed = 0
    errors = 0
    error_messages: list[str] = []

    try:
        # Get ComicVine settings
        from comicarr.routes.comicvine import fetch_comicvine, normalize_comicvine_payload
        from comicarr.routes.settings import _get_external_apis

        external_apis = _get_external_apis()
        comicvine_settings = external_apis.get("comicvine", {})
        normalized_comicvine = None
        if comicvine_settings.get("api_key"):
            normalized_comicvine = normalize_comicvine_payload(comicvine_settings)

        # Get default library
        from comicarr.db.models import Library

        libraries_result = await session.exec(  # type: ignore[attr-defined]
            select(Library)
            .where(Library.enabled == True)
            .order_by(col(Library.default).desc(), Library.name)
        )
        libraries = libraries_result.all()
        if not libraries:
            raise ValueError("No enabled libraries found. Cannot process weekly releases.")
        default_library = libraries[0]

        # Get session factory for concurrent processing
        session_factory = get_global_session_factory()

        # Limit concurrency to prevent overwhelming the database and ComicVine API
        # Processing involves DB operations and potentially ComicVine API calls
        # Reduced to 3 to minimize SQLite write lock contention
        max_concurrent = 3
        semaphore = asyncio.Semaphore(max_concurrent)

        # Lock for progress updates (only one coroutine updates progress at a time)
        progress_lock = asyncio.Lock()

        async def process_entry(entry: WeeklyReleaseItem) -> tuple[bool, bool, str | None]:
            """Process a single entry and return (success, error_occurred, error_message).

            Creates its own session to allow concurrent processing.
            """
            async with semaphore:  # Limit concurrent operations
                try:
                    if session_factory:
                        async with session_factory() as task_session:
                            # Load the entry in the task session
                            task_entry = await task_session.get(WeeklyReleaseItem, entry.id)
                            if not task_entry:
                                logger.error("Entry not found in task session", item_id=entry.id)
                                return (False, True, f"Entry not found: {entry.id}")

                            volume = None

                            # Try to get volume from library match first
                            if task_entry.matched_volume_id:
                                volume = await task_session.get(
                                    LibraryVolume, task_entry.matched_volume_id
                                )

                            # If no library match, try to find or create from ComicVine ID
                            if not volume and task_entry.comicvine_volume_id:
                                existing_volume_result = await task_session.exec(
                                    select(LibraryVolume).where(
                                        LibraryVolume.comicvine_id
                                        == task_entry.comicvine_volume_id,
                                        LibraryVolume.library_id == default_library.id,
                                    )
                                )
                                volume = existing_volume_result.one_or_none()

                                if not volume:
                                    volume = await _create_volume_from_comicvine(
                                        session=task_session,
                                        comicvine_id=task_entry.comicvine_volume_id,
                                        library_id=default_library.id,
                                        normalized_comicvine=normalized_comicvine,
                                    )

                            if not volume:
                                error_msg = (
                                    f"No volume match and no ComicVine ID for: {task_entry.title}"
                                )
                                logger.warning(error_msg, item_id=task_entry.id)
                                # Mark as processed (failed) but don't update status to processed
                                return (False, False, error_msg)

                            # Update item with matched volume ID if not set
                            if not task_entry.matched_volume_id:
                                task_entry.matched_volume_id = volume.id

                            # Check if issue already exists
                            if task_entry.matched_issue_id:
                                # Issue exists - update it
                                issue = await task_session.get(
                                    LibraryIssue, task_entry.matched_issue_id
                                )
                                if issue:
                                    # Update ComicVine data if available
                                    if task_entry.comicvine_issue_id and not issue.comicvine_id:
                                        issue.comicvine_id = task_entry.comicvine_issue_id

                                    # Update other fields if missing
                                    if task_entry.comicvine_issue_name and not issue.title:
                                        issue.title = task_entry.comicvine_issue_name
                                    if task_entry.release_date and not issue.release_date:
                                        issue.release_date = task_entry.release_date

                                    # Ensure it's marked as wanted and monitored
                                    if issue.status == "missing":
                                        issue.status = "wanted"
                                    issue.monitored = True
                                    issue.updated_at = int(time.time())
                            else:
                                # Issue doesn't exist - create it
                                import json
                                import uuid

                                metadata = {}
                                try:
                                    metadata = json.loads(task_entry.metadata_json or "{}")
                                except (json.JSONDecodeError, TypeError):
                                    pass

                                issue_number = (
                                    metadata.get("issue_number")
                                    or task_entry.comicvine_issue_number
                                    or "?"
                                )

                                # Try to fetch issue details from ComicVine if we have an issue ID
                                issue_title = task_entry.comicvine_issue_name or task_entry.title
                                issue_release_date = (
                                    task_entry.release_date or task_entry.comicvine_cover_date
                                )
                                issue_image = None

                                if task_entry.comicvine_issue_id and normalized_comicvine:
                                    try:
                                        issue_payload = await fetch_comicvine(
                                            normalized_comicvine,
                                            f"issue/4000-{task_entry.comicvine_issue_id}",
                                            {
                                                "field_list": "id,issue_number,name,description,site_detail_url,image,cover_date",
                                            },
                                        )
                                        issue_data = issue_payload.get("results", {})
                                        if issue_data:
                                            issue_title = issue_data.get("name") or issue_title
                                            issue_release_date = (
                                                issue_data.get("cover_date") or issue_release_date
                                            )

                                            # Extract image URL
                                            image_data = issue_data.get("image")
                                            if isinstance(image_data, dict):
                                                issue_image = (
                                                    image_data.get("super_url")
                                                    or image_data.get("medium_url")
                                                    or image_data.get("original_url")
                                                    or image_data.get("icon_url")
                                                )
                                            elif isinstance(image_data, str):
                                                issue_image = issue_data
                                    except Exception as exc:
                                        logger.debug(
                                            "Failed to fetch issue details from ComicVine",
                                            error=str(exc),
                                            issue_id=task_entry.comicvine_issue_id,
                                        )

                                # Create the issue
                                new_issue = LibraryIssue(
                                    id=uuid.uuid4().hex,
                                    volume_id=volume.id,
                                    comicvine_id=task_entry.comicvine_issue_id,
                                    number=str(issue_number),
                                    title=issue_title,
                                    release_date=issue_release_date,
                                    image=issue_image,
                                    monitored=True,
                                    status="wanted",
                                    created_at=int(time.time()),
                                    updated_at=int(time.time()),
                                )
                                task_session.add(new_issue)
                                # Use retry logic for flush to handle lock errors
                                await retry_db_operation(
                                    lambda: task_session.flush(),
                                    session=task_session,
                                    operation_type="flush_issue",
                                )
                                await task_session.refresh(new_issue)

                                # Update the item with the new issue ID
                                task_entry.matched_issue_id = new_issue.id

                            # Mark entry as processed after successful processing
                            # Use retry logic to handle lock errors
                            from sqlalchemy import update

                            await retry_db_operation(
                                lambda: task_session.execute(
                                    update(WeeklyReleaseItem)
                                    .where(WeeklyReleaseItem.id == task_entry.id)  # type: ignore[arg-type]
                                    .values(status="processed", updated_at=int(time.time()))
                                ),
                                session=task_session,
                                operation_type="update_weekly_release_item",
                            )

                            # Commit this task's changes independently with retry
                            await retry_db_operation(
                                lambda: task_session.commit(),
                                session=task_session,
                                operation_type="commit_processing",
                            )

                            logger.debug("Processed entry", job_id=job_id, entry_id=task_entry.id)
                            return (True, False, None)
                    else:
                        # Fallback: if no session factory, can't do concurrent processing
                        logger.warning(
                            "No session factory available for concurrent processing", job_id=job_id
                        )
                        return (False, False, None)
                except Exception as e:
                    error_msg = f"Failed to process {entry.title}: {str(e)}"
                    logger.error(
                        "Error processing entry",
                        job_id=job_id,
                        entry_id=entry.id,
                        error=str(e),
                        exc_info=True,
                    )
                    return (False, True, error_msg)

        # Create tasks for all entries - process concurrently with limited concurrency
        tasks = [process_entry(entry) for entry in entries]

        # Process tasks as they complete, updating progress incrementally
        for coro in asyncio.as_completed(tasks):
            entry_success, entry_error, error_msg = await coro

            # Update progress after each entry completes (with lock to prevent race conditions)
            async with progress_lock:
                # Check for pause/cancel status before updating progress
                await session.refresh(job)
                if job.status == "paused":
                    logger.info("Processing job paused, waiting for resume", job_id=job_id)
                    # Wait for resume
                    while job.status == "paused":
                        await asyncio.sleep(1)
                        await session.refresh(job)
                    logger.info("Processing job resumed", job_id=job_id)

                # Check if job was cancelled/failed/completed while paused
                if job.status in ("cancelled", "failed", "completed"):
                    logger.info("Processing job status changed", job_id=job_id, status=job.status)
                    return

                processed += 1
                if entry_error:
                    errors += 1
                    if error_msg:
                        error_messages.append(error_msg)
                job.progress_current = processed
                job.error_count = errors
                job.updated_at = int(time.time())
                await session.commit()
        # Mark job as completed
        job.status = "completed"
        job.completed_at = int(time.time())
        job.updated_at = int(time.time())
        # Store error summary if there were errors
        if errors > 0:
            error_summary = f"{errors} error(s) occurred. " + "; ".join(error_messages[:5])
            if len(error_messages) > 5:
                error_summary += f" (and {len(error_messages) - 5} more)"
            job.error = error_summary
        await session.commit()

        logger.info(
            "Job completed",
            job_id=job_id,
            processed=processed,
            total=job.progress_total,
            errors=errors,
        )

    except Exception as e:
        # Mark job as failed
        job.status = "failed"
        job.error = str(e)
        job.completed_at = int(time.time())
        job.updated_at = int(time.time())
        await session.commit()

        logger.error("Job failed", job_id=job_id, error=str(e), exc_info=True)


async def start_weekly_release_job(
    session: SQLModelAsyncSession,
    week_id: str,
) -> WeeklyReleaseProcessingJob:
    """Create and start a background job for processing weekly releases.

    Args:
        session: Database session
        week_id: Week ID to process

    Returns:
        Created job
    """
    # Check if there's already a queued or processing job for this week
    existing_result = await session.exec(  # type: ignore[attr-defined]
        select(WeeklyReleaseProcessingJob)
        .where(WeeklyReleaseProcessingJob.week_id == week_id)
        .where(col(WeeklyReleaseProcessingJob.status).in_(["queued", "processing"]))
    )
    existing = existing_result.one_or_none()
    if existing:
        logger.warning("Job already exists for week", week_id=week_id, job_id=existing.id)
        return existing

    # Count entries to process
    entries_result = await session.exec(
        select(WeeklyReleaseItem)
        .where(WeeklyReleaseItem.week_id == week_id)
        .where(WeeklyReleaseItem.status == "import")
    )
    entries = entries_result.all()

    # Create job
    job = WeeklyReleaseProcessingJob(
        week_id=week_id,
        status="queued",
        progress_total=len(entries),
        progress_current=0,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    logger.info("Created processing job", job_id=job.id, week_id=week_id, total=len(entries))

    # Start processing in background (fire and forget)
    # Note: We need to get the session factory from the app state
    # For now, we'll pass the session factory as a parameter
    # This will be called from the route handler which has access to the session factory

    return job
