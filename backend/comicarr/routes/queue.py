"""Queue and activity routes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path

# Stub types for job types that don't exist yet (planned features)
# These are used in the queue routes but the models haven't been implemented
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.db import LibraryIssue, LibraryVolume

# Type stubs for unimplemented job types
DownloadJob: type[Any] = Any  # type: ignore[assignment, misc]
MetatagJob: type[Any] = Any  # type: ignore[assignment, misc]
BulkOperationJob: type[Any] = Any  # type: ignore[assignment, misc]

logger = structlog.get_logger("comicarr.queue")


def create_queue_router(
    require_authenticated: Callable,
    get_db_session: Callable[[], AsyncIterator[SQLModelAsyncSession]],
    metatag_queue: asyncio.Queue[str],
    bulk_operation_queue: asyncio.Queue[str],
) -> APIRouter:
    """Create queue and activity router.

    Args:
        require_authenticated: Dependency function for authentication
        get_db_session: Dependency function for database sessions
        metatag_queue: Asyncio queue for metatag jobs
        bulk_operation_queue: Asyncio queue for bulk operation jobs

    Returns:
        Configured APIRouter instance
    """
    router = APIRouter()

    @router.delete("/api/queue/jobs/{job_id}", tags=["queue"])
    async def delete_job(
        job_id: str,
        job_type: str = Query(
            ...,
            description="Job type: metatag_issue, metatag_volume, bulk_operation",
        ),
        _: None = Depends(require_authenticated),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> dict[str, Any]:
        """Delete a job by ID.

        Args:
            job_id: Job ID
            job_type: Type of job to delete

        Returns:
            Dictionary with deletion status
        """
        # Get the appropriate job model based on type
        if job_type in ("metatag_issue", "metatag_volume"):
            job = await session.get(MetatagJob, job_id)  # type: ignore[name-defined]
            model_class = MetatagJob  # type: ignore[name-defined]
        elif job_type == "bulk_operation":
            try:
                job = await session.get(BulkOperationJob, job_id)  # type: ignore[name-defined]
                model_class = BulkOperationJob  # type: ignore[name-defined]
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Bulk operation jobs table not available",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid job type: {job_type}"
            )

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"{job_type} job not found"
            )

        await session.delete(job)
        await session.commit()

        logger.info("Deleted job", job_id=job_id, job_type=job_type)

        return {
            "job_id": job_id,
            "job_type": job_type,
            "status": "deleted",
            "message": f"{job_type} job deleted successfully",
        }

    @router.post("/api/queue/jobs/{job_id}/retry", tags=["queue"])
    async def retry_job(
        job_id: str,
        job_type: str = Query(
            ...,
            description="Job type: metatag_issue, metatag_volume, bulk_operation",
        ),
        _: None = Depends(require_authenticated),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> dict[str, Any]:
        """Retry a failed or stuck job by requeuing it.

        Args:
            job_id: Job ID
            job_type: Type of job to retry

        Returns:
            Dictionary with retry status
        """
        # Get the appropriate job model based on type
        if job_type in ("metatag_issue", "metatag_volume"):
            job = await session.get(MetatagJob, job_id)  # type: ignore[name-defined]
            model_class = MetatagJob  # type: ignore[name-defined]
            queue = metatag_queue
        elif job_type == "bulk_operation":
            try:
                job = await session.get(BulkOperationJob, job_id)  # type: ignore[name-defined]
                model_class = BulkOperationJob  # type: ignore[name-defined]
                queue = bulk_operation_queue
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Bulk operation jobs table not available",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid job type: {job_type}"
            )

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"{job_type} job not found"
            )

        # Check if job can be retried
        retryable_statuses = ("queued", "retry", "failed")
        if hasattr(job, "status") and job.status not in retryable_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job status is '{job.status}', only jobs with status 'queued', 'retry', or 'failed' can be retried",
            )

        # Reset job status and clear error
        if hasattr(job, "status"):
            job.status = "queued"  # type: ignore[assignment]
        if hasattr(job, "error"):
            job.error = None
        if hasattr(job, "retry_count"):
            # Reset retry_count to 0 to allow fresh retry
            job.retry_count = 0

        await session.commit()

        # Requeue the job
        await queue.put(job_id)

        logger.info("Retried job", job_id=job_id, job_type=job_type)

        return {
            "job_id": job_id,
            "job_type": job_type,
            "status": "queued",
            "message": f"{job_type} job requeued for retry",
        }

    @router.get("/api/queue", tags=["queue"])
    async def list_queue_tasks(
        type: str | None = Query(
            None,
            description="Filter by task type (metatag_issue, metatag_volume)",
        ),
        status: str | None = Query(
            None,
            description="Filter by status (queued, processing, completed, failed, retry)",
        ),
        volume_id: str | None = Query(None, description="Filter by volume ID"),
        _: None = Depends(require_authenticated),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> dict[str, Any]:
        """List all active user-initiated tasks in the queue.

        Returns tasks that are queued, downloading, or processing.
        Supports filtering by task type and status.
        """
        tasks: list[dict[str, Any]] = []

        # Get metatag jobs if type is None, "metatag_issue", or "metatag_volume"
        if type is None or type in ("metatag_issue", "metatag_volume"):
            query = select(MetatagJob)  # type: ignore[name-defined]
            if volume_id:
                query = query.where(MetatagJob.volume_id == volume_id)
            if status:
                query = query.where(MetatagJob.status == status)
            else:
                # Default: show active tasks (queued, processing, retry)
                query = query.where(MetatagJob.status.in_(("queued", "processing", "retry")))
            if type == "metatag_issue":
                query = query.where(MetatagJob.job_type == "metatag_issue")
            elif type == "metatag_volume":
                query = query.where(MetatagJob.job_type == "metatag_volume")
            query = query.order_by(col(MetatagJob.created_at).desc())
            result = await session.exec(query)
            jobs = result.all()
            for job in jobs:
                # Fetch volume and issue for additional info
                volume = await session.get(LibraryVolume, job.volume_id) if job.volume_id else None
                issue = await session.get(LibraryIssue, job.issue_id) if job.issue_id else None

                # Extract filename from issue_file_path
                file_filename = None
                if issue and issue.file_path:
                    file_filename = Path(issue.file_path).name

                tasks.append(
                    {
                        "id": job.id,
                        "type": job.job_type,
                        "volume_id": job.volume_id,
                        "volume_title": volume.title if volume else None,
                        "issue_id": job.issue_id,
                        "issue_number": job.issue_number or (issue.number if issue else None),
                        "issue_file_path": issue.file_path if issue else None,
                        "file_filename": file_filename,
                        "status": job.status,
                        "error": job.error,
                        "attempts": job.retry_count,
                        "created_at": job.created_at,
                        "updated_at": job.updated_at,
                    }
                )

        # Apply status filter if specified (already applied per task type)
        if status and type is None:
            # If filtering by status and no specific type, filter all tasks
            tasks = [task for task in tasks if task.get("status") == status]

        return {
            "tasks": tasks,
            "count": len(tasks),
        }

    @router.get("/api/activity", tags=["activity"])
    async def list_activity_tasks(
        type: str | None = Query(
            None,
            description="Filter by task type (metatag_issue, metatag_volume)",
        ),
        status: str | None = Query(
            None, description="Filter by status (completed, failed, cancelled)"
        ),
        volume_id: str | None = Query(None, description="Filter by volume ID"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum number of results to return"),
        _: None = Depends(require_authenticated),
        session: SQLModelAsyncSession = Depends(get_db_session),
    ) -> dict[str, Any]:
        """List all completed user-initiated tasks (history).

        Returns tasks that are completed, failed, or cancelled.
        Supports filtering by task type and status.
        """
        tasks: list[dict[str, Any]] = []

        # Get metatag jobs if type is None, "metatag_issue", or "metatag_volume"
        if type is None or type in ("metatag_issue", "metatag_volume"):
            query = select(MetatagJob)  # type: ignore[name-defined]
            if volume_id:
                query = query.where(MetatagJob.volume_id == volume_id)
            if status:
                query = query.where(MetatagJob.status == status)
            else:
                # Default: show completed and failed tasks
                query = query.where(MetatagJob.status.in_(("completed", "failed")))
            if type == "metatag_issue":
                query = query.where(MetatagJob.job_type == "metatag_issue")
            elif type == "metatag_volume":
                query = query.where(MetatagJob.job_type == "metatag_volume")
            query = query.order_by(col(MetatagJob.updated_at).desc()).limit(limit)
            result = await session.exec(query)
            jobs = result.all()
            for job in jobs:
                # Fetch volume and issue for additional info
                volume = await session.get(LibraryVolume, job.volume_id) if job.volume_id else None
                issue = await session.get(LibraryIssue, job.issue_id) if job.issue_id else None

                # Extract filename from issue_file_path
                file_filename = None
                if issue and issue.file_path:
                    file_filename = Path(issue.file_path).name

                tasks.append(
                    {
                        "id": job.id,
                        "type": job.job_type,
                        "volume_id": job.volume_id,
                        "volume_title": volume.title if volume else None,
                        "issue_id": job.issue_id,
                        "issue_number": job.issue_number or (issue.number if issue else None),
                        "issue_file_path": issue.file_path if issue else None,
                        "file_filename": file_filename,
                        "status": job.status,
                        "error": job.error,
                        "attempts": job.retry_count,
                        "created_at": job.created_at,
                        "updated_at": job.updated_at,
                    }
                )

        # Get bulk operation jobs if type is None or "bulk_operation"
        if type is None or type == "bulk_operation":
            try:
                query = select(BulkOperationJob)  # type: ignore[name-defined]
                if status:
                    query = query.where(BulkOperationJob.status == status)
                else:
                    # Default: show active tasks (queued, processing)
                    query = query.where(BulkOperationJob.status.in_(("queued", "processing")))
                query = query.order_by(col(BulkOperationJob.created_at).desc())
                result = await session.exec(query)
                jobs = result.all()
                for job in jobs:
                    tasks.append(
                        {
                            "id": job.id,
                            "type": "bulk_operation",
                            "operation_type": job.operation_type,
                            "context_id": job.context_id,
                            "status": job.status,
                            "progress": job.progress,
                            "total": job.total,
                            "success_count": job.success_count,
                            "error_count": job.error_count,
                            "skipped_count": job.skipped_count,
                            "error": job.error,
                            "created_at": job.created_at,
                            "updated_at": job.updated_at,
                        }
                    )
            except Exception:
                # Table doesn't exist yet (migration not run) - silently skip
                pass

        # Get bulk operation jobs if type is None or "bulk_operation"
        if type is None or type == "bulk_operation":
            try:
                query = select(BulkOperationJob)  # type: ignore[name-defined]
                if status:
                    query = query.where(BulkOperationJob.status == status)
                else:
                    # Default: show completed and failed tasks
                    query = query.where(BulkOperationJob.status.in_(("completed", "failed")))
                query = query.order_by(col(BulkOperationJob.updated_at).desc()).limit(limit)
                result = await session.exec(query)
                jobs = result.all()
                for job in jobs:
                    tasks.append(
                        {
                            "id": job.id,
                            "type": "bulk_operation",
                            "operation_type": job.operation_type,
                            "context_id": job.context_id,
                            "status": job.status,
                            "progress": job.progress,
                            "total": job.total,
                            "success_count": job.success_count,
                            "error_count": job.error_count,
                            "skipped_count": job.skipped_count,
                            "error": job.error,
                            "created_at": job.created_at,
                            "updated_at": job.updated_at,
                            "completed_at": job.completed_at,
                        }
                    )
            except Exception:
                # Table doesn't exist yet (migration not run) - silently skip
                pass

        # Apply status filter if specified (already applied per task type)
        if status and type is None:
            # If filtering by status and no specific type, filter all tasks
            tasks = [task for task in tasks if task.get("status") == status]

        # Sort by updated_at descending
        tasks.sort(key=lambda x: x.get("updated_at", 0), reverse=True)

        # Apply limit
        tasks = tasks[:limit]

        return {
            "tasks": tasks,
            "count": len(tasks),
        }

    return router
