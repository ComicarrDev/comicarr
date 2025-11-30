"""Background job processor for import processing."""

from __future__ import annotations

import asyncio
import time

import structlog
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.database import get_global_session_factory, retry_db_operation
from comicarr.core.import_process import _process_pending_file
from comicarr.db.models import ImportJob, ImportPendingFile, ImportProcessingJob, Library

logger = structlog.get_logger("comicarr.import.processing_job_processor")


async def process_import_processing_job(
    session: SQLModelAsyncSession,
    job_id: str,
) -> None:
    """Process an import processing job.

    This function runs the actual processing work and updates job status/progress.

    Args:
        session: Database session
        job_id: Processing job ID to process
    """
    logger.info("process_import_processing_job called", job_id=job_id)
    try:
        # Load job
        job_result = await session.exec(
            select(ImportProcessingJob).where(ImportProcessingJob.id == job_id)
        )
        job = job_result.one_or_none()
        if not job:
            logger.error("Processing job not found", job_id=job_id)
            return

        logger.info(
            "Processing job loaded",
            job_id=job_id,
            status=job.status,
            import_job_id=job.import_job_id,
        )

        # Check if already completed, cancelled, or paused
        if job.status in ("completed", "failed", "cancelled"):
            logger.warning("Processing job already finished", job_id=job_id, status=job.status)
            return

        # If paused, wait until resumed
        if job.status == "paused":
            logger.info("Processing job is paused, waiting for resume", job_id=job_id)
            max_wait_time = 3600  # Wait up to 1 hour
            wait_start = time.time()
            while job.status == "paused" and (time.time() - wait_start) < max_wait_time:
                await asyncio.sleep(1)
                await session.refresh(job)

            if job.status != "paused":
                logger.info("Processing job resumed", job_id=job_id, new_status=job.status)
            else:
                logger.warning("Processing job still paused after max wait time", job_id=job_id)
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
        library_result = await session.exec(
            select(Library).where(Library.id == import_job.library_id)
        )
        library = library_result.one_or_none()
        if not library:
            job.status = "failed"
            job.error = "Library not found"
            job.completed_at = int(time.time())
            await session.commit()
            logger.error("Library not found", job_id=job_id, library_id=import_job.library_id)
            return

        # Get approved files (status == "import")
        approved_files_result = await session.exec(
            select(ImportPendingFile).where(
                ImportPendingFile.import_job_id == import_job.id,
                ImportPendingFile.status == "import",
            )
        )
        approved_files = approved_files_result.all()

        if not approved_files:
            job.status = "completed"
            job.progress_current = 0
            job.progress_total = 0
            job.completed_at = int(time.time())
            await session.commit()
            logger.info("No approved files to process", job_id=job_id)
            return

        # Update job status and progress
        job.status = "processing"
        job.progress_total = len(approved_files)
        job.progress_current = 0
        job.error_count = 0
        job.started_at = int(time.time())
        await session.commit()

        logger.info("Starting processing job", job_id=job_id, total=job.progress_total)

        # Process files
        session_factory = get_global_session_factory()
        processed_count = 0
        errors = 0
        error_messages: list[str] = []

        try:
            for pending_file in approved_files:
                # Check if job was paused or cancelled
                await session.refresh(job)
                if job.status in ("paused", "cancelled"):
                    logger.info("Processing job paused/cancelled", job_id=job_id, status=job.status)
                    break

                try:
                    if session_factory:
                        async with session_factory() as file_session:
                            # Reload pending_file in the new session to avoid attachment errors
                            pending_file_id = pending_file.id
                            file_session_pending_file_result = await file_session.exec(
                                select(ImportPendingFile).where(
                                    ImportPendingFile.id == pending_file_id
                                )
                            )
                            file_session_pending_file = (
                                file_session_pending_file_result.one_or_none()
                            )

                            if not file_session_pending_file:
                                errors += 1
                                error_msg = f"Pending file {pending_file_id} not found in database"
                                error_messages.append(
                                    f"Failed to process {pending_file.file_name}: {error_msg}"
                                )
                                logger.error(
                                    "Pending file not found", job_id=job_id, file_id=pending_file_id
                                )
                                continue

                            success, error_msg = await _process_pending_file(
                                file_session_pending_file,
                                import_job,
                                library,
                                file_session,
                            )

                            if success:
                                processed_count += 1
                            else:
                                errors += 1
                                if error_msg:
                                    error_messages.append(
                                        f"Failed to process {pending_file.file_name}: {error_msg}"
                                    )

                            # Update progress
                            await session.refresh(job)
                            job.progress_current = processed_count + errors
                            job.error_count = errors
                            job.updated_at = int(time.time())
                            await retry_db_operation(
                                lambda: session.commit(),
                                session=session,
                                operation_type="update_processing_progress",
                            )
                    else:
                        logger.warning("No session factory available for processing", job_id=job_id)
                        break

                except Exception as exc:
                    errors += 1
                    error_msg = f"Error processing {pending_file.file_name}: {str(exc)}"
                    error_messages.append(error_msg)
                    logger.error(
                        "Error processing file",
                        job_id=job_id,
                        file_id=pending_file.id,
                        error=str(exc),
                        exc_info=True,
                    )

                    # Update progress
                    await session.refresh(job)
                    job.progress_current = processed_count + errors
                    job.error_count = errors
                    job.updated_at = int(time.time())
                    await retry_db_operation(
                        lambda: session.commit(),
                        session=session,
                        operation_type="update_processing_progress",
                    )

            # Mark job as completed
            job.status = "completed"
            job.completed_at = int(time.time())
            job.progress_current = processed_count + errors
            job.error_count = errors
            if error_messages:
                job.error = "; ".join(error_messages[:5])  # Limit error message length
            job.updated_at = int(time.time())

            # Update import job status
            await session.refresh(import_job)
            import_job.status = "completed"
            import_job.updated_at = int(time.time())
            import_job.completed_at = int(time.time())

            await retry_db_operation(
                lambda: session.commit(),
                session=session,
                operation_type="complete_processing_job",
            )

            logger.info(
                "Processing job completed",
                job_id=job_id,
                processed=processed_count,
                errors=errors,
                total=job.progress_total,
            )

        except Exception as exc:
            logger.error("Processing job failed", job_id=job_id, error=str(exc), exc_info=True)
            try:
                await session.refresh(job)
                job.status = "failed"
                job.error = str(exc)
                job.error_count = errors if "errors" in locals() else 0
                job.completed_at = int(time.time())
                await retry_db_operation(
                    lambda: session.commit(),
                    session=session,
                    operation_type="fail_processing_job",
                )
            except Exception as commit_exc:
                logger.error(
                    "Failed to update job status on error", job_id=job_id, error=str(commit_exc)
                )

    except Exception as exc:
        logger.error(
            "Unexpected error in process_import_processing_job",
            job_id=job_id,
            error=str(exc),
            exc_info=True,
        )

    except Exception as exc:
        logger.error(
            "Unexpected error in process_import_processing_job",
            job_id=job_id,
            error=str(exc),
            exc_info=True,
        )
