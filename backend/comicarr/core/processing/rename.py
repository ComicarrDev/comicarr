"""Rename worker for processing rename jobs.

TODO: This module is part of the unused WorkerManager pattern.
It needs to be adapted to the current stateful model approach if implemented.
RenameJob model is not currently pushed to main.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from comicarr.core.processing.models import MediaSettings
from comicarr.core.processing.naming import NamingService
from comicarr.db.models import Library

# TODO: RenameJob is not currently implemented
# from comicarr.db.models import RenameJob
RenameJob: type[Any] = Any  # type: ignore[assignment, misc]

if TYPE_CHECKING:
    pass

logger = structlog.get_logger("comicarr.processing.rename")


class RenameWorker:
    """Worker for processing file rename jobs."""

    def __init__(
        self,
        naming_service: NamingService,
        processing_service: Any,  # ProcessingService (avoid circular import)
    ) -> None:
        """Initialize rename worker.

        Args:
            naming_service: Service for rendering naming templates
            processing_service: Processing service for queueing follow-up jobs
        """
        self.naming_service = naming_service
        self.processing_service = processing_service
        self.logger = structlog.get_logger("comicarr.processing.rename")

    async def process_job(
        self,
        session: SQLModelAsyncSession,
        job_id: str,
    ) -> None:
        """Process a rename job.

        Args:
            session: Database session
            job_id: Rename job ID
        """
        job = await session.get(RenameJob, job_id)
        if not job:
            self.logger.warning("Rename job not found", job_id=job_id)
            return

        if job.status not in ("queued", "retry"):
            self.logger.debug(
                "Rename job not in processable state",
                job_id=job_id,
                status=job.status,
            )
            return

        # Update status
        job.status = "renaming"
        job.updated_at = int(time.time())
        await session.commit()
        await session.refresh(job)

        try:
            # Get issue, volume, and library
            from comicarr.db.models import LibraryIssue, LibraryVolume

            issue = await session.get(LibraryIssue, job.issue_id) if job.issue_id else None
            volume = await session.get(LibraryVolume, job.volume_id)

            if not volume:
                raise ValueError(f"Volume {job.volume_id} not found")

            if not issue:
                raise ValueError(f"Issue {job.issue_id} not found")

            # Get library and settings
            library = await session.get(Library, volume.library_id)
            if not library:
                raise ValueError(f"Library {volume.library_id} not found")

            settings = MediaSettings.model_validate(library.settings)
            library_root = Path(library.library_root)

            # Build source path
            source_path = library_root / job.source_file_path

            if not source_path.exists():
                raise FileNotFoundError(f"Source file not found: {source_path}")

            # Generate target filename using library settings
            volume_folder = self.naming_service.render_volume_folder(
                settings.volume_folder_naming,
                volume.title,
                volume.year,
                Publisher=volume.publisher or "Unknown",
            )

            # Determine extension from source file
            ext = source_path.suffix[1:].lower() if source_path.suffix else "cbz"

            issue_filename = self.naming_service.render_issue_filename(
                settings.file_naming_template,
                volume.title,
                issue.number,
                ext=ext,
                release_date=issue.release_date,
                volume_year=volume.year,
            )

            # Build target path using library root
            target_folder = library_root / volume_folder
            target_folder.mkdir(parents=True, exist_ok=True)
            target_path = target_folder / issue_filename

            # Ensure unique filename
            if target_path.exists() and target_path != source_path:
                counter = 1
                stem = target_path.stem
                while target_path.exists():
                    target_path = target_folder / f"{stem} ({counter}){target_path.suffix}"
                    counter += 1

            # Perform rename
            if source_path != target_path:
                source_path.rename(target_path)
                self.logger.info(
                    "File renamed",
                    job_id=job_id,
                    source=str(source_path.relative_to(library_root)),
                    target=str(target_path.relative_to(library_root)),
                )

            # Update job and issue
            job.target_file_path = str(target_path.relative_to(library_root))
            job.status = "completed"
            job.updated_at = int(time.time())

            issue.file_path = job.target_file_path
            issue.status = "processed"  # Ready for conversion
            await session.commit()

            # Queue conversion if needed (rename_then_convert order)
            if settings.processing_order == "rename_then_convert":
                await self.processing_service.queue_conversion_after_rename(
                    session,
                    issue,
                    volume,
                    Path(job.target_file_path),
                )

            self.logger.info("Rename job completed", job_id=job_id)

        except Exception as e:
            self.logger.error(
                "Rename job failed",
                job_id=job_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            job.status = "failed"
            job.error = str(e)
            job.updated_at = int(time.time())
            await session.commit()
            raise
