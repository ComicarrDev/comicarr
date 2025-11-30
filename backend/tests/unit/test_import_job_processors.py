"""Tests for import job processors (scanning and processing)."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from comicarr.core.database import create_database_engine, create_session_factory
from comicarr.core.import_processing_job_processor import process_import_processing_job
from comicarr.core.import_scanning_job_processor import process_import_scanning_job
from comicarr.db.models import (
    ImportJob,
    ImportPendingFile,
    ImportProcessingJob,
    ImportScanningJob,
    Library,
)


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """Create a database session for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test.db"

    try:
        engine = create_database_engine(str(db_path), echo=False)
        async_session_factory = create_session_factory(engine)

        # Set global session factory so job processors can use it
        from comicarr.core.database import set_global_session_factory

        set_global_session_factory(async_session_factory)

        from comicarr.db.models import metadata

        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

        async with async_session_factory() as session:
            yield session

        await engine.dispose()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def test_library(session: AsyncSession) -> Library:
    """Create a test library with real directory."""
    temp_dir = Path(tempfile.mkdtemp())
    library = Library(
        id=uuid.uuid4().hex,
        name="Test Library",
        library_root=str(temp_dir),
        default=True,
        enabled=True,
    )
    session.add(library)
    await session.commit()
    await session.refresh(library)
    yield library
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def test_import_job(session: AsyncSession, test_library: Library) -> ImportJob:
    """Create a test import job."""
    temp_dir = Path(tempfile.mkdtemp())
    job = ImportJob(
        id=uuid.uuid4().hex,
        library_id=test_library.id,
        scan_type="external_folder",
        folder_path=str(temp_dir),
        link_files=False,
        status="scanning",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    job._temp_dir = temp_dir
    return job


class TestImportScanningJobProcessor:
    """Test process_import_scanning_job function."""

    @pytest.mark.asyncio
    async def test_scans_folder_and_creates_pending_files(
        self, session: AsyncSession, test_library: Library, test_import_job: ImportJob
    ):
        """Test that scanning job scans folder and creates pending files."""
        # Create scanning job
        scanning_job = ImportScanningJob(
            id=uuid.uuid4().hex,
            import_job_id=test_import_job.id,
            status="queued",
            progress_current=0,
            progress_total=0,
        )
        session.add(scanning_job)
        await session.commit()

        # Create test files in folder
        temp_dir = Path(test_import_job.folder_path)
        (temp_dir / "Series A #1.cbz").write_bytes(b"fake data" * 1000)
        (temp_dir / "Series B #2.cbz").write_bytes(b"fake data" * 1000)

        try:
            # Process scanning job
            await process_import_scanning_job(session, scanning_job.id)

            # Refresh job
            await session.refresh(scanning_job)

            # Verify job completed
            assert scanning_job.status == "completed"
            assert scanning_job.progress_current == scanning_job.progress_total
            assert scanning_job.progress_total >= 2  # At least 2 files

            # Verify pending files were created
            from sqlmodel import select

            pending_result = await session.exec(
                select(ImportPendingFile).where(
                    ImportPendingFile.import_job_id == test_import_job.id
                )
            )
            pending_files = pending_result.all()
            assert len(pending_files) >= 2

        finally:
            if hasattr(test_import_job, "_temp_dir"):
                shutil.rmtree(test_import_job._temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_handles_nonexistent_folder(self, session: AsyncSession, test_library: Library):
        """Test that scanning job handles nonexistent folder gracefully."""
        # Create import job with nonexistent folder
        job = ImportJob(
            id=uuid.uuid4().hex,
            library_id=test_library.id,
            scan_type="external_folder",
            folder_path="/nonexistent/folder",
            link_files=False,
            status="scanning",
        )
        session.add(job)
        await session.commit()

        # Create scanning job
        scanning_job = ImportScanningJob(
            id=uuid.uuid4().hex,
            import_job_id=job.id,
            status="queued",
            progress_current=0,
            progress_total=0,
        )
        session.add(scanning_job)
        await session.commit()

        # Process scanning job
        await process_import_scanning_job(session, scanning_job.id)

        # Refresh job
        await session.refresh(scanning_job)

        # Should fail
        assert scanning_job.status == "failed"
        assert scanning_job.error is not None


class TestImportProcessingJobProcessor:
    """Test process_import_processing_job function."""

    @pytest.mark.asyncio
    async def test_processes_pending_files_with_import_status(
        self, session: AsyncSession, test_library: Library, test_import_job: ImportJob
    ):
        """Test that processing job processes files with 'import' status."""
        # Create temp files
        temp_dir = Path(tempfile.mkdtemp())
        file1 = temp_dir / "File1.cbz"
        file2 = temp_dir / "File2.cbz"
        file1.write_bytes(b"fake data" * 1000)
        file2.write_bytes(b"fake data" * 1000)

        try:
            # Create pending files with 'import' status
            pending_file1 = ImportPendingFile(
                id=uuid.uuid4().hex,
                import_job_id=test_import_job.id,
                file_path=str(file1),
                file_name="File1.cbz",
                file_size=file1.stat().st_size,
                file_extension=".cbz",
                status="import",
            )
            pending_file2 = ImportPendingFile(
                id=uuid.uuid4().hex,
                import_job_id=test_import_job.id,
                file_path=str(file2),
                file_name="File2.cbz",
                file_size=file2.stat().st_size,
                file_extension=".cbz",
                status="import",
            )
            session.add(pending_file1)
            session.add(pending_file2)
            await session.commit()

            # Create processing job
            processing_job = ImportProcessingJob(
                id=uuid.uuid4().hex,
                import_job_id=test_import_job.id,
                status="queued",
                progress_current=0,
                progress_total=2,
            )
            session.add(processing_job)
            await session.commit()

            # Mock the _process_pending_file to avoid file system operations
            with patch(
                "comicarr.core.import_processing_job_processor._process_pending_file"
            ) as mock_process:
                mock_process.return_value = (True, None)  # Success

                # Process job
                await process_import_processing_job(session, processing_job.id)

                # Verify both files were processed
                assert mock_process.call_count == 2

                # Refresh job
                await session.refresh(processing_job)

                # Verify job completed
                assert processing_job.status == "completed"
                assert processing_job.progress_current == 2

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_skips_files_not_in_import_status(
        self, session: AsyncSession, test_import_job: ImportJob
    ):
        """Test that files not in 'import' status are skipped."""
        # Create pending files with different statuses
        pending_file1 = ImportPendingFile(
            id=uuid.uuid4().hex,
            import_job_id=test_import_job.id,
            file_path="/test/file1.cbz",
            file_name="File1.cbz",
            file_size=1000,
            file_extension=".cbz",
            status="pending",  # Not 'import'
        )
        pending_file2 = ImportPendingFile(
            id=uuid.uuid4().hex,
            import_job_id=test_import_job.id,
            file_path="/test/file2.cbz",
            file_name="File2.cbz",
            file_size=1000,
            file_extension=".cbz",
            status="import",  # This one should be processed
        )
        session.add(pending_file1)
        session.add(pending_file2)
        await session.commit()

        # Create processing job
        processing_job = ImportProcessingJob(
            id=uuid.uuid4().hex,
            import_job_id=test_import_job.id,
            status="queued",
            progress_current=0,
            progress_total=1,  # Only one file should be processed
        )
        session.add(processing_job)
        await session.commit()

        # Mock the _process_pending_file
        with patch(
            "comicarr.core.import_processing_job_processor._process_pending_file"
        ) as mock_process:
            mock_process.return_value = (True, None)

            # Process job
            await process_import_processing_job(session, processing_job.id)

            # Verify only one file was processed
            assert mock_process.call_count == 1

            # Refresh job
            await session.refresh(processing_job)
            assert processing_job.progress_current == 1

    @pytest.mark.asyncio
    async def test_tracks_errors_during_processing(
        self, session: AsyncSession, test_import_job: ImportJob
    ):
        """Test that errors during processing are tracked."""
        # Create pending file
        pending_file = ImportPendingFile(
            id=uuid.uuid4().hex,
            import_job_id=test_import_job.id,
            file_path="/test/file.cbz",
            file_name="File.cbz",
            file_size=1000,
            file_extension=".cbz",
            status="import",
        )
        session.add(pending_file)
        await session.commit()

        # Create processing job
        processing_job = ImportProcessingJob(
            id=uuid.uuid4().hex,
            import_job_id=test_import_job.id,
            status="queued",
            progress_current=0,
            progress_total=1,
        )
        session.add(processing_job)
        await session.commit()

        # Mock the _process_pending_file to return error
        with patch(
            "comicarr.core.import_processing_job_processor._process_pending_file"
        ) as mock_process:
            mock_process.return_value = (False, "Test error message")

            # Process job
            await process_import_processing_job(session, processing_job.id)

            # Refresh job
            await session.refresh(processing_job)

            # Verify error was tracked
            assert processing_job.error_count > 0
            assert processing_job.status == "completed"  # Job completes even with errors
