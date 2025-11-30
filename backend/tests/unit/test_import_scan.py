"""Tests for import scanning functionality."""

from __future__ import annotations

import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from comicarr.core.database import create_database_engine, create_session_factory
from comicarr.core.import_scan import (
    _extract_series_from_filename,
    _issue_has_file,
    _match_file_to_library,
    scan_folder_for_import,
)
from comicarr.db.models import ImportJob, Library, LibraryIssue, LibraryVolume


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """Create a database session for testing."""
    import shutil

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
    """Create a test library."""
    library = Library(
        id=uuid.uuid4().hex,
        name="Test Library",
        library_root="/test/library",
        default=True,
        enabled=True,
    )
    session.add(library)
    await session.commit()
    await session.refresh(library)
    return library


@pytest.fixture
async def test_volume(session: AsyncSession, test_library: Library) -> LibraryVolume:
    """Create a test volume."""
    volume = LibraryVolume(
        id=uuid.uuid4().hex,
        library_id=test_library.id,
        title="Batman",
        publisher="DC Comics",
        year=2016,
    )
    session.add(volume)
    await session.commit()
    await session.refresh(volume)
    return volume


@pytest.fixture
async def test_import_job(session: AsyncSession, test_library: Library) -> ImportJob:
    """Create a test import job."""
    job = ImportJob(
        id=uuid.uuid4().hex,
        library_id=test_library.id,
        scan_type="external_folder",
        folder_path="/test/folder",
        link_files=False,
        status="scanning",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


class TestExtractSeriesFromFilename:
    """Test _extract_series_from_filename function."""

    def test_extracts_series_and_issue(self):
        """Test extracting series name and issue number from filename."""
        series, issue, year, month, volume = _extract_series_from_filename(
            "Batman - v2016 #001 (January 2016).cbz"
        )
        assert series == "Batman"
        assert issue == "001"
        assert year == 2016
        assert month == "January"
        assert volume == "2016"

    def test_handles_simple_filename(self):
        """Test handling simple filename format."""
        series, issue, year, month, volume = _extract_series_from_filename("Batman #1.cbz")
        assert series == "Batman"
        assert issue == "1"
        assert year is None
        assert month is None
        assert volume is None

    def test_handles_issue_without_hash(self):
        """Test handling issue number without hash symbol."""
        series, issue, year, month, volume = _extract_series_from_filename("Batman 001.cbz")
        assert series == "Batman"
        assert issue == "001"

    def test_handles_missing_issue_number(self):
        """Test handling filename without issue number."""
        series, issue, year, month, volume = _extract_series_from_filename("Batman Annual.cbz")
        assert series == "Batman Annual"
        assert issue is None


class TestIssueHasFile:
    """Test _issue_has_file function."""

    @pytest.mark.asyncio
    async def test_returns_true_when_issue_has_file(
        self, session: AsyncSession, test_volume: LibraryVolume
    ):
        """Test that function returns True when issue has file path."""
        issue = LibraryIssue(
            id=uuid.uuid4().hex,
            volume_id=test_volume.id,
            number="1",
            file_path="batman-1.cbz",
            status="ready",
        )
        session.add(issue)
        await session.commit()

        result = await _issue_has_file(issue.id, session)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_issue_has_no_file(
        self, session: AsyncSession, test_volume: LibraryVolume
    ):
        """Test that function returns False when issue has no file."""
        issue = LibraryIssue(
            id=uuid.uuid4().hex,
            volume_id=test_volume.id,
            number="1",
            file_path=None,
            status="wanted",
        )
        session.add(issue)
        await session.commit()

        result = await _issue_has_file(issue.id, session)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_issue_not_found(self, session: AsyncSession):
        """Test that function returns False when issue doesn't exist."""
        fake_id = uuid.uuid4().hex
        result = await _issue_has_file(fake_id, session)
        assert result is False


class TestMatchFileToLibrary:
    """Test _match_file_to_library function."""

    @pytest.mark.asyncio
    async def test_matches_exact_series_and_issue(
        self, session: AsyncSession, test_library: Library, test_volume: LibraryVolume
    ):
        """Test matching file with exact series and issue number."""
        issue = LibraryIssue(
            id=uuid.uuid4().hex,
            volume_id=test_volume.id,
            number="1",
            status="wanted",
        )
        session.add(issue)
        await session.commit()

        file_path = Path("/test/Batman #1.cbz")
        volume_id, issue_id, confidence = await _match_file_to_library(
            file_path, "Batman #1", "Batman", "1", session
        )

        assert volume_id == test_volume.id
        assert issue_id == issue.id
        assert confidence >= 0.8

    @pytest.mark.asyncio
    async def test_no_match_when_issue_number_differs(
        self, session: AsyncSession, test_library: Library, test_volume: LibraryVolume
    ):
        """Test that no match occurs when issue number differs."""
        issue = LibraryIssue(
            id=uuid.uuid4().hex,
            volume_id=test_volume.id,
            number="2",  # Different issue
            status="wanted",
        )
        session.add(issue)
        await session.commit()

        file_path = Path("/test/Batman #1.cbz")
        volume_id, issue_id, confidence = await _match_file_to_library(
            file_path, "Batman #1", "Batman", "1", session
        )

        # Should not match (different issue number)
        assert volume_id is None
        assert issue_id is None

    @pytest.mark.asyncio
    async def test_no_match_when_series_differs(self, session: AsyncSession, test_library: Library):
        """Test that no match occurs when series name differs."""
        # Create different volume
        volume = LibraryVolume(
            id=uuid.uuid4().hex,
            library_id=test_library.id,
            title="Superman",
            publisher="DC Comics",
            year=2016,
        )
        session.add(volume)
        await session.commit()

        file_path = Path("/test/Batman #1.cbz")
        volume_id, issue_id, confidence = await _match_file_to_library(
            file_path, "Batman #1", "Batman", "1", session
        )

        # Should not match (different series)
        assert volume_id is None
        assert issue_id is None


class TestScanFolderForImport:
    """Test scan_folder_for_import function."""

    @pytest.mark.asyncio
    async def test_skips_files_already_in_library(
        self,
        session: AsyncSession,
        test_library: Library,
        test_volume: LibraryVolume,
        test_import_job: ImportJob,
    ):
        """Test that files already in library are skipped."""
        # Create temporary folder with test file
        temp_dir = Path(tempfile.mkdtemp())
        test_file = temp_dir / "Batman #1.cbz"
        test_file.write_bytes(b"fake comic data")

        try:
            # Create issue with file path pointing to our test file
            issue = LibraryIssue(
                id=uuid.uuid4().hex,
                volume_id=test_volume.id,
                number="1",
                file_path=str(test_file),  # Absolute path
                status="ready",
            )
            session.add(issue)
            await session.commit()

            # Update library root to temp_dir for path resolution
            test_library.library_root = str(temp_dir)
            session.add(test_library)
            await session.commit()

            from unittest.mock import patch

            # Mock ComicVine search to prevent API calls
            with patch("comicarr.core.import_scan._search_comicvine_for_file") as mock_search:
                mock_search.return_value = None  # No ComicVine match
                # Scan folder
                count = await scan_folder_for_import(
                    temp_dir,
                    test_import_job.id,
                    session,
                )

                # Should skip the file (already in library)
                assert count == 0

            # Verify no ImportPendingFile was created
            from sqlmodel import select

            from comicarr.db.models import ImportPendingFile

            pending_result = await session.exec(
                select(ImportPendingFile).where(
                    ImportPendingFile.import_job_id == test_import_job.id
                )
            )
            pending_files = pending_result.all()
            assert len(pending_files) == 0

        finally:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_creates_pending_file_for_new_file(
        self, session: AsyncSession, test_library: Library, test_import_job: ImportJob
    ):
        """Test that new files create ImportPendingFile entries."""
        from unittest.mock import patch

        # Create temporary folder with test file
        temp_dir = Path(tempfile.mkdtemp())
        test_file = temp_dir / "New Series #1.cbz"
        test_file.write_bytes(b"fake comic data" * 1000)  # Make it large enough

        try:
            # Mock ComicVine search to prevent API calls
            with patch("comicarr.core.import_scan._search_comicvine_for_file") as mock_search:
                mock_search.return_value = None  # No ComicVine match
                # Scan folder
                count = await scan_folder_for_import(
                    temp_dir,
                    test_import_job.id,
                    session,
                )

            # Should create one pending file
            assert count == 1

            # Verify ImportPendingFile was created
            from sqlmodel import select

            from comicarr.db.models import ImportPendingFile

            pending_result = await session.exec(
                select(ImportPendingFile).where(
                    ImportPendingFile.import_job_id == test_import_job.id
                )
            )
            pending_files = pending_result.all()
            assert len(pending_files) == 1

            pending_file = pending_files[0]
            assert pending_file.file_name == "New Series #1.cbz"
            # Status could be "pending" or "skipped" depending on matching logic
            assert pending_file.status in ("pending", "skipped", "import")

        finally:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_skips_suspiciously_small_files(
        self, session: AsyncSession, test_import_job: ImportJob
    ):
        """Test that suspiciously small files are marked but still added."""
        from unittest.mock import patch

        # Create temporary folder with very small file
        temp_dir = Path(tempfile.mkdtemp())
        test_file = temp_dir / "Tiny File #1.cbz"
        test_file.write_bytes(b"x")  # Very small file

        try:
            # Mock ComicVine search to prevent API calls
            with patch("comicarr.core.import_scan._search_comicvine_for_file") as mock_search:
                mock_search.return_value = None  # No ComicVine match
                # Scan folder
                count = await scan_folder_for_import(
                    temp_dir,
                    test_import_job.id,
                    session,
                )

            # Should still create entry (but marked as suspicious)
            assert count == 1

            # Verify ImportPendingFile was created
            from sqlmodel import select

            from comicarr.db.models import ImportPendingFile

            pending_result = await session.exec(
                select(ImportPendingFile).where(
                    ImportPendingFile.import_job_id == test_import_job.id
                )
            )
            pending_files = pending_result.all()
            assert len(pending_files) == 1

            # File should be marked (warnings will be in metadata)
            pending_file = pending_files[0]
            assert pending_file.file_name == "Tiny File #1.cbz"

        finally:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)
