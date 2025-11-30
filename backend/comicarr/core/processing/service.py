"""Processing service for orchestrating post-download tasks.

TODO: This module is part of the unused WorkerManager pattern.
It needs to be adapted to the current stateful model approach if implemented.
ConversionJob and RenameJob models are not currently pushed to main.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.processing.models import MediaSettings
from comicarr.db.models import Library

# TODO: ConversionJob and RenameJob are not currently implemented
# from comicarr.db.models import ConversionJob, RenameJob
ConversionJob: type[Any] = Any  # type: ignore[assignment, misc]
RenameJob: type[Any] = Any  # type: ignore[assignment, misc]

if TYPE_CHECKING:
    from comicarr.db.models import LibraryIssue, LibraryVolume

logger = structlog.get_logger("comicarr.processing.service")


class ProcessingService:
    """Service for managing post-download processing jobs."""

    def __init__(
        self,
        rename_queue: asyncio.Queue[str] | None = None,
        conversion_queue: asyncio.Queue[str] | None = None,
    ) -> None:
        """Initialize processing service.

        Args:
            rename_queue: Async queue for rename job IDs
            conversion_queue: Async queue for conversion job IDs
        """
        self.rename_queue = rename_queue
        self.conversion_queue = conversion_queue
        self.logger = structlog.get_logger("comicarr.processing.service")

    async def queue_post_processing(
        self,
        session: SQLModelAsyncSession,
        issue: LibraryIssue,
        volume: LibraryVolume,
        file_path: Path,
    ) -> None:
        """Queue post-processing jobs after download completes.

        Args:
            session: Database session
            issue: Issue that was downloaded
            volume: Volume containing the issue
            file_path: Path to downloaded file (relative to library root)
        """
        # Get library and settings
        library = await session.get(Library, volume.library_id)
        if not library:
            self.logger.error("Library not found", library_id=volume.library_id)
            return

        settings = MediaSettings.model_validate(library.settings)

        self.logger.debug(
            "Queueing post-processing",
            issue_id=issue.id,
            volume_id=volume.id,
            library_id=library.id,
            file_path=str(file_path),
        )

        if settings.processing_order == "rename_then_convert":
            # Queue rename first
            if settings.rename_downloaded_files:
                await self._queue_rename_job(session, issue, volume, file_path)
            # Conversion will be queued after rename completes
        else:
            # Queue conversion first
            if settings.convert_files and settings.preferred_format != "No Conversion":
                await self._queue_conversion_job(
                    session, issue, volume, file_path, settings.preferred_format
                )
            # Rename will be queued after conversion completes

    async def queue_conversion_after_rename(
        self,
        session: SQLModelAsyncSession,
        issue: LibraryIssue,
        volume: LibraryVolume,
        file_path: Path,
    ) -> None:
        """Queue conversion job after rename completes.

        Args:
            session: Database session
            issue: Issue that was renamed
            volume: Volume containing the issue
            file_path: Path to renamed file (relative to library root)
        """
        # Get library and settings
        library = await session.get(Library, volume.library_id)
        if not library:
            return

        settings = MediaSettings.model_validate(library.settings)

        if settings.convert_files and settings.preferred_format != "No Conversion":
            await self._queue_conversion_job(
                session, issue, volume, file_path, settings.preferred_format
            )

    async def queue_rename_after_conversion(
        self,
        session: SQLModelAsyncSession,
        issue: LibraryIssue,
        volume: LibraryVolume,
        file_path: Path,
    ) -> None:
        """Queue rename job after conversion completes.

        Args:
            session: Database session
            issue: Issue that was converted
            volume: Volume containing the issue
            file_path: Path to converted file (relative to library root)
        """
        # Get library and settings
        library = await session.get(Library, volume.library_id)
        if not library:
            return

        settings = MediaSettings.model_validate(library.settings)

        if settings.rename_downloaded_files:
            await self._queue_rename_job(session, issue, volume, file_path)

    async def _queue_rename_job(
        self,
        session: SQLModelAsyncSession,
        issue: LibraryIssue,
        volume: LibraryVolume,
        file_path: Path,
    ) -> None:
        """Create and queue a rename job.

        Args:
            session: Database session
            issue: Issue to rename
            volume: Volume containing the issue
            file_path: Current file path (relative to library root)
        """
        # Check if rename job already exists
        existing = await session.exec(
            select(RenameJob).where(
                RenameJob.issue_id == issue.id,
                col(RenameJob.status).in_(("queued", "renaming", "retry")),
            )
        )
        if existing.first():
            self.logger.debug("Rename job already exists", issue_id=issue.id)
            return

        rename_job = RenameJob(
            volume_id=volume.id,
            issue_id=issue.id,
            issue_number=getattr(issue, "number", None),
            source_file_path=str(file_path),
            status="queued",
        )
        session.add(rename_job)
        await session.commit()
        await session.refresh(rename_job)

        if self.rename_queue:
            await self.rename_queue.put(rename_job.id)
            self.logger.info("Queued rename job", job_id=rename_job.id, issue_id=issue.id)

    async def _queue_conversion_job(
        self,
        session: SQLModelAsyncSession,
        issue: LibraryIssue,
        volume: LibraryVolume,
        file_path: Path,
        target_format: str,
    ) -> None:
        """Create and queue a conversion job.

        Args:
            session: Database session
            issue: Issue to convert
            volume: Volume containing the issue
            file_path: Current file path (relative to library root)
            target_format: Target format (e.g., "CBZ")
        """
        # Check if conversion job already exists
        existing = await session.exec(
            select(ConversionJob).where(
                ConversionJob.issue_id == issue.id,
                col(ConversionJob.status).in_(("queued", "converting", "retry")),
            )
        )
        if existing.first():
            self.logger.debug("Conversion job already exists", issue_id=issue.id)
            return

        conversion_job = ConversionJob(
            volume_id=volume.id,
            issue_id=issue.id,
            issue_number=getattr(issue, "number", None),
            source_file_path=str(file_path),
            target_format=target_format,
            status="queued",
        )
        session.add(conversion_job)
        await session.commit()
        await session.refresh(conversion_job)

        if self.conversion_queue:
            await self.conversion_queue.put(conversion_job.id)
            self.logger.info(
                "Queued conversion job",
                job_id=conversion_job.id,
                issue_id=issue.id,
                target_format=target_format,
            )
