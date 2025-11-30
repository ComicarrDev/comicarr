"""Background job processor for bulk matching weekly releases."""

from __future__ import annotations

import asyncio
import json
import time

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.database import get_global_session_factory
from comicarr.core.weekly_releases.matching import (
    match_weekly_release_to_comicvine,
    match_weekly_release_to_library,
)
from comicarr.db.models import WeeklyReleaseItem, WeeklyReleaseMatchingJob, WeeklyReleaseWeek

logger = structlog.get_logger("comicarr.weekly_releases.matching_job_processor")


async def process_matching_job(
    session: SQLModelAsyncSession,
    job_id: str,
) -> None:
    """Process a bulk matching job.

    This function runs the actual matching work and updates job status/progress.

    Args:
        session: Database session
        job_id: Job ID to process
    """
    # Load job
    job_result = await session.exec(
        select(WeeklyReleaseMatchingJob).where(WeeklyReleaseMatchingJob.id == job_id)
    )
    job = job_result.one_or_none()
    if not job:
        logger.error("Matching job not found", job_id=job_id)
        return

    # Check if already completed, cancelled, or paused
    if job.status in ("completed", "failed", "cancelled"):
        logger.warning("Matching job already finished", job_id=job_id, status=job.status)
        return

    # If paused, wait until resumed
    if job.status == "paused":
        logger.info("Matching job is paused, waiting for resume", job_id=job_id)
        # Wait in a loop checking for status change
        max_wait_time = 3600  # Wait up to 1 hour
        wait_start = time.time()
        while job.status == "paused" and (time.time() - wait_start) < max_wait_time:
            await asyncio.sleep(1)  # Check every second
            await session.refresh(job)

        if job.status != "paused":
            logger.info("Matching job resumed", job_id=job_id, new_status=job.status)
        else:
            logger.warning("Matching job still paused after max wait time", job_id=job_id)
            return

    # Load week
    week_result = await session.exec(
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

    # Load entries to match
    if not job.entry_ids:
        job.status = "completed"
        job.progress_current = 0
        job.progress_total = 0
        job.completed_at = int(time.time())
        await session.commit()
        logger.info("No entries to match", job_id=job_id)
        return

    entries_result = await session.exec(
        select(WeeklyReleaseItem).where(col(WeeklyReleaseItem.id).in_(job.entry_ids))
    )
    entries = entries_result.all()

    if not entries:
        job.status = "completed"
        job.progress_current = 0
        job.progress_total = 0
        job.completed_at = int(time.time())
        await session.commit()
        logger.info("No matching entries found", job_id=job_id)
        return

    # Update job status and progress
    job.status = "processing"
    job.progress_total = len(entries)
    job.progress_current = 0
    job.matched_count = 0
    job.error_count = 0
    job.started_at = int(time.time())
    await session.commit()

    logger.info(
        "Starting matching job",
        job_id=job_id,
        type=job.match_type if job else None,
        total=job.progress_total if job else 0,
    )

    try:
        matched = 0
        errors = 0
        progress_lock = asyncio.Lock()

        # Get session factory for creating per-task sessions (for library matching)
        session_factory = get_global_session_factory()

        # Limit concurrency to prevent overwhelming the database
        # Library matching does more DB work, so use lower concurrency
        # ComicVine matching is mostly API calls, so can handle more
        max_concurrent = 5 if job and job.match_type == "library" else 20
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_entry(entry: WeeklyReleaseItem) -> tuple[bool, bool]:
            """Process a single entry and return (matched, error_occurred).

            For library matching, creates its own session to allow concurrent processing.
            For ComicVine matching, uses the main session (mostly API calls, minimal DB usage).
            """
            async with semaphore:  # Limit concurrent operations
                try:
                    if job and job.match_type == "library":
                        # Library matching: create a new session for this task to allow concurrency
                        # Each task gets its own session, so they can run in parallel without conflicts
                        if session_factory:
                            async with session_factory() as task_session:
                                # Load the entry in the task session so changes can be persisted
                                task_entry = await task_session.get(WeeklyReleaseItem, entry.id)
                                if not task_entry:
                                    logger.error(
                                        "Entry not found in task session", item_id=entry.id
                                    )
                                    return (False, True)

                                result = await match_weekly_release_to_library(
                                    task_entry, task_session
                                )
                                # Commit this task's changes independently
                                # The changes are now persisted in the database
                                await task_session.commit()

                                if result and result.get("matched") and result.get("volume_id"):
                                    return (True, False)
                                else:
                                    # Log why matching failed for debugging
                                    reason = (
                                        result.get("reason", "unknown") if result else "no_result"
                                    )
                                    metadata = json.loads(entry.metadata_json or "{}")
                                    series = metadata.get("series") or entry.title
                                    issue_number = metadata.get("issue_number")
                                    logger.debug(
                                        "Library matching failed",
                                        item_id=entry.id,
                                        title=entry.title,
                                        series=series,
                                        issue_number=issue_number,
                                        comicvine_issue_id=entry.comicvine_issue_id,
                                        reason=reason,
                                    )
                                    return (False, False)
                        else:
                            # Fallback: if no session factory, can't do concurrent processing
                            logger.warning(
                                "No session factory available for concurrent library matching",
                                job_id=job_id,
                            )
                            return (False, False)
                    elif job and job.match_type == "comicvine":
                        # ComicVine matching: uses main session (mostly API calls, minimal DB usage)
                        result = await match_weekly_release_to_comicvine(entry, session)
                        if result and result.get("comicvine_volume_id"):
                            return (True, False)
                        else:
                            return (False, False)
                    else:
                        match_type = job.match_type if job else None
                        logger.error("Unknown match type", job_id=job_id, match_type=match_type)
                        return (False, False)
                except Exception as e:
                    logger.error(
                        "Error matching entry",
                        job_id=job_id,
                        entry_id=entry.id,
                        error=str(e),
                        exc_info=True,
                    )
                    return (False, True)

        # Create tasks for all entries - both library and ComicVine can now run concurrently
        # But with limited concurrency to prevent overwhelming the database
        tasks = [process_entry(entry) for entry in entries]

        # Process tasks as they complete, updating progress incrementally
        # This allows cached items (which complete quickly) to proceed immediately
        # while non-cached items wait for rate limits
        for coro in asyncio.as_completed(tasks):
            entry_matched, entry_error = await coro

            # Update progress after each entry completes (with lock to prevent race conditions)
            # Progress updates use the main session, which is safe because only one
            # coroutine updates progress at a time (protected by progress_lock)
            async with progress_lock:
                # Check for pause/cancel status before updating progress
                await session.refresh(job)
                if job.status == "paused":
                    logger.info("Matching job paused, waiting for resume", job_id=job_id)
                    # Wait for resume
                    while job.status == "paused":
                        await asyncio.sleep(1)
                        await session.refresh(job)
                    logger.info("Matching job resumed", job_id=job_id)

                # Check if job was cancelled/failed/completed while paused
                if job.status in ("cancelled", "failed", "completed"):
                    logger.info("Matching job status changed", job_id=job_id, status=job.status)
                    return

                job.progress_current += 1
                if entry_matched:
                    matched += 1
                    job.matched_count = matched
                if entry_error:
                    errors += 1
                    job.error_count = errors
                job.updated_at = int(time.time())
                await session.commit()

        # Mark job as completed
        job.status = "completed"
        job.completed_at = int(time.time())
        job.updated_at = int(time.time())
        await session.commit()

        logger.info(
            "Matching job completed",
            job_id=job_id,
            matched=matched,
            errors=errors,
            total=job.progress_total,
        )

    except Exception as e:
        # Mark job as failed
        job.status = "failed"
        job.error = str(e)
        job.completed_at = int(time.time())
        job.updated_at = int(time.time())
        await session.commit()

        logger.error("Matching job failed", job_id=job_id, error=str(e), exc_info=True)


async def start_matching_job(
    session: SQLModelAsyncSession,
    week_id: str,
    match_type: str,
    entry_ids: list[str],
) -> WeeklyReleaseMatchingJob:
    """Create and start a background job for bulk matching.

    Args:
        session: Database session
        week_id: Week ID
        match_type: "comicvine" or "library"
        entry_ids: List of entry IDs to match

    Returns:
        Created job
    """
    # Check if there's already a queued or processing job for this week and type
    existing_result = await session.exec(
        select(WeeklyReleaseMatchingJob)
        .where(WeeklyReleaseMatchingJob.week_id == week_id)
        .where(WeeklyReleaseMatchingJob.match_type == match_type)
        .where(col(WeeklyReleaseMatchingJob.status).in_(["queued", "processing"]))
    )
    existing = existing_result.one_or_none()
    if existing:
        logger.warning(
            "Matching job already exists",
            week_id=week_id,
            match_type=match_type,
            job_id=existing.id,
        )
        return existing

    # Create job
    job = WeeklyReleaseMatchingJob(
        week_id=week_id,
        match_type=match_type,
        entry_ids=entry_ids,
        status="queued",
        progress_total=len(entry_ids),
        progress_current=0,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    logger.info(
        "Created matching job",
        job_id=job.id,
        week_id=week_id,
        match_type=match_type,
        total=len(entry_ids),
    )

    return job
