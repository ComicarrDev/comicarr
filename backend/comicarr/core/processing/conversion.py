"""Conversion worker for processing format conversion jobs.

TODO: This module is part of the unused WorkerManager pattern.
It needs to be adapted to the current stateful model approach if implemented.
ConversionJob model is not currently pushed to main.
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

# TODO: ConversionJob is not currently implemented
# from comicarr.db.models import ConversionJob
ConversionJob: type[Any] = Any  # type: ignore[assignment, misc]

if TYPE_CHECKING:
    pass

logger = structlog.get_logger("comicarr.processing.conversion")


class ConversionWorker:
    """Worker for processing file format conversion jobs."""

    def __init__(
        self,
        naming_service: NamingService,
        processing_service: Any,  # ProcessingService (avoid circular import)
    ) -> None:
        """Initialize conversion worker.

        Args:
            naming_service: Service for rendering naming templates
            processing_service: Processing service for queueing follow-up jobs
        """
        self.naming_service = naming_service
        self.processing_service = processing_service
        self.logger = structlog.get_logger("comicarr.processing.conversion")

    async def process_job(
        self,
        session: SQLModelAsyncSession,
        job_id: str,
    ) -> None:
        """Process a conversion job.

        Args:
            session: Database session
            job_id: Conversion job ID
        """
        job = await session.get(ConversionJob, job_id)
        if not job:
            self.logger.warning("Conversion job not found", job_id=job_id)
            return

        if job.status not in ("queued", "retry"):
            self.logger.debug(
                "Conversion job not in processable state",
                job_id=job_id,
                status=job.status,
            )
            return

        # Update status
        job.status = "converting"
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

            # Check if already in target format
            source_ext = source_path.suffix.upper()
            target_ext = f".{job.target_format.lower()}"

            if source_ext == target_ext:
                # Already in target format, skip conversion
                self.logger.info(
                    "File already in target format, skipping conversion",
                    job_id=job_id,
                    format=job.target_format,
                )
                job.target_file_path = job.source_file_path
                job.status = "completed"
                job.updated_at = int(time.time())
                if hasattr(issue, "status"):
                    issue.status = "ready"
                await session.commit()
                return

            # Perform conversion
            target_path = await self._convert_file(source_path, target_ext)

            # Update job and issue
            job.target_file_path = str(target_path.relative_to(library_root))
            job.status = "completed"
            job.updated_at = int(time.time())

            issue.file_path = job.target_file_path
            issue.status = "ready"  # Fully processed
            await session.commit()

            # Queue rename if needed (convert_then_rename order)
            if settings.processing_order == "convert_then_rename":
                await self.processing_service.queue_rename_after_conversion(
                    session,
                    issue,
                    volume,
                    Path(job.target_file_path),
                )

            self.logger.info(
                "Conversion job completed",
                job_id=job_id,
                source_format=source_ext,
                target_format=target_ext,
            )

        except Exception as e:
            self.logger.error(
                "Conversion job failed",
                job_id=job_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            job.status = "failed"
            job.error = str(e)
            job.updated_at = int(time.time())
            await session.commit()
            raise

    async def _convert_file(self, source_path: Path, target_ext: str) -> Path:
        """Convert file to target format.

        Args:
            source_path: Source file path
            target_ext: Target extension (e.g., ".cbz")

        Returns:
            Path to converted file
        """
        # For now, only implement ZIP <-> CBZ (they're the same format)
        # More formats can be added later (RAR, 7Z, etc.)

        if target_ext == ".cbz" and source_path.suffix.lower() == ".zip":
            # ZIP to CBZ is just a rename
            target_path = source_path.with_suffix(target_ext)
            source_path.rename(target_path)
            return target_path

        if target_ext == ".zip" and source_path.suffix.lower() == ".cbz":
            # CBZ to ZIP is just a rename
            target_path = source_path.with_suffix(target_ext)
            source_path.rename(target_path)
            return target_path

        # For other conversions, we'd need to extract and re-archive
        # This is a placeholder - implement based on your needs
        raise NotImplementedError(
            f"Conversion from {source_path.suffix} to {target_ext} not yet implemented"
        )
