"""Tests for import processing functionality."""

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
from comicarr.core.import_process import _process_pending_file
from comicarr.db.models import ImportJob, ImportPendingFile, Library, LibraryIssue, LibraryVolume


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
    """Create a test library with a real directory."""
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
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


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
async def test_issue(session: AsyncSession, test_volume: LibraryVolume) -> LibraryIssue:
    """Create a test issue."""
    issue = LibraryIssue(
        id=uuid.uuid4().hex,
        volume_id=test_volume.id,
        number="1",
        status="wanted",
    )
    session.add(issue)
    await session.commit()
    await session.refresh(issue)
    return issue


@pytest.fixture
async def test_import_job(session: AsyncSession, test_library: Library) -> ImportJob:
    """Create a test import job."""
    job = ImportJob(
        id=uuid.uuid4().hex,
        library_id=test_library.id,
        scan_type="external_folder",
        folder_path="/test/folder",
        link_files=False,
        status="pending_review",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


@pytest.fixture
async def test_pending_file(
    session: AsyncSession,
    test_import_job: ImportJob,
    test_volume: LibraryVolume,
    test_issue: LibraryIssue,
) -> ImportPendingFile:
    """Create a test pending file."""
    # Create a real file for testing
    temp_dir = Path(tempfile.mkdtemp())
    source_file = temp_dir / "Batman #1.cbz"
    source_file.write_bytes(b"fake comic data" * 1000)

    pending_file = ImportPendingFile(
        id=uuid.uuid4().hex,
        import_job_id=test_import_job.id,
        file_path=str(source_file),
        file_name="Batman #1.cbz",
        file_size=source_file.stat().st_size,
        file_extension=".cbz",
        status="import",
        matched_volume_id=test_volume.id,
        matched_issue_id=test_issue.id,
        matched_confidence=1.0,
    )
    session.add(pending_file)
    await session.commit()
    await session.refresh(pending_file)

    # Store temp_dir for cleanup
    pending_file._temp_dir = temp_dir

    return pending_file


class TestProcessPendingFile:
    """Test _process_pending_file function."""

    @pytest.mark.asyncio
    async def test_processes_file_successfully(
        self,
        session: AsyncSession,
        test_import_job: ImportJob,
        test_library: Library,
        test_volume: LibraryVolume,
        test_issue: LibraryIssue,
        test_pending_file: ImportPendingFile,
    ):
        """Test that file is processed successfully and moved to library."""
        # Process file
        success, error = await _process_pending_file(
            test_pending_file,
            test_import_job,
            test_library,
            session,
        )

        assert success is True
        assert error is None

        # Verify issue was updated
        await session.refresh(test_issue)
        assert test_issue.file_path is not None
        assert test_issue.status == "ready"
        assert test_issue.file_size == test_pending_file.file_size

        # Verify pending file was marked as processed
        await session.refresh(test_pending_file)
        assert test_pending_file.status == "processed"

        # Verify file was moved (original should not exist)
        original_path = Path(test_pending_file.file_path)
        assert not original_path.exists()

        # Verify file exists in library location
        library_path = Path(test_library.library_root) / test_issue.file_path
        assert library_path.exists()

        # Cleanup
        if hasattr(test_pending_file, "_temp_dir"):
            shutil.rmtree(test_pending_file._temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_creates_volume_from_comicvine_when_needed(
        self, session: AsyncSession, test_import_job: ImportJob, test_library: Library
    ):
        """Test that volume is created from ComicVine when needed."""
        # Create temp file
        temp_dir = Path(tempfile.mkdtemp())
        source_file = temp_dir / "New Series #1.cbz"
        source_file.write_bytes(b"fake comic data" * 1000)

        comicvine_volume_id = 12345
        comicvine_issue_id = 1001

        try:
            pending_file = ImportPendingFile(
                id=uuid.uuid4().hex,
                import_job_id=test_import_job.id,
                file_path=str(source_file),
                file_name="New Series #1.cbz",
                file_size=source_file.stat().st_size,
                file_extension=".cbz",
                status="import",
                comicvine_volume_id=comicvine_volume_id,
                comicvine_issue_id=comicvine_issue_id,
            )
            session.add(pending_file)
            await session.commit()

            # Mock ComicVine API
            volume_data = {
                "id": comicvine_volume_id,
                "name": "New Series",
                "start_year": "2025",
                "publisher": {"name": "Test Publisher"},
                "description": "Test description",
                "site_detail_url": "https://comicvine.gamespot.com/test",
                "image": {"medium_url": "https://example.com/image.jpg"},
                "count_of_issues": 1,
            }

            issues_data = [
                {
                    "id": comicvine_issue_id,
                    "issue_number": "1",
                    "name": "Issue #1",
                    "cover_date": "2025-01-01",
                    "description": "First issue",
                    "site_detail_url": "https://comicvine.gamespot.com/issue1",
                    "image": {"medium_url": "https://example.com/issue1.jpg"},
                },
            ]

            with (
                patch(
                    "comicarr.core.weekly_releases.processing.fetch_comicvine"
                ) as mock_fetch_volume,
                patch("comicarr.routes.comicvine.fetch_comicvine") as mock_fetch_comicvine,
                patch("comicarr.routes.volumes.fetch_comicvine_issues") as mock_fetch_issues,
                patch("comicarr.routes.volumes.fetch_comicvine") as mock_fetch_comicvine_route,
                patch("comicarr.routes.settings._get_external_apis") as mock_get_apis,
                patch(
                    "comicarr.core.weekly_releases.processing._get_external_apis"
                ) as mock_get_apis_processing,
                patch("comicarr.routes.comicvine.normalize_comicvine_payload") as mock_normalize,
                patch(
                    "comicarr.core.weekly_releases.processing.build_comicvine_volume_result"
                ) as mock_build,
            ):

                comicvine_settings = {
                    "comicvine": {
                        "api_key": "test_key",
                        "enabled": True,
                        "base_url": "https://comicvine.gamespot.com/api",
                    }
                }
                mock_get_apis.return_value = comicvine_settings
                mock_get_apis_processing.return_value = comicvine_settings
                mock_normalize.return_value = {
                    "api_key": "test_key",
                    "enabled": True,
                    "base_url": "https://comicvine.gamespot.com/api",
                }

                mock_fetch_volume.return_value = {"results": volume_data}
                mock_fetch_issues.return_value = issues_data
                # Mock the route-level fetch_comicvine that fetch_comicvine_issues calls
                mock_fetch_comicvine_route.return_value = {"results": issues_data}

                # Mock issue fetch (called when creating issue from ComicVine)
                # This is called from import_process.py when it tries to create an issue
                issue_data_single = {
                    "id": comicvine_issue_id,
                    "issue_number": "1",
                    "name": "Issue #1",
                    "cover_date": "2025-01-01",
                    "description": "First issue",
                    "site_detail_url": "https://comicvine.gamespot.com/issue1",
                    "image": {"medium_url": "https://example.com/issue1.jpg"},
                }

                # mock_fetch_comicvine is used both for volume and issue fetches
                # Set up side_effect to return different values based on the endpoint
                def fetch_comicvine_side_effect(normalized, endpoint, params=None):
                    if "issue/4000" in endpoint:
                        return {"results": issue_data_single}
                    elif "volume/4050" in endpoint:
                        return {"results": volume_data}
                    return {"results": {}}

                mock_fetch_comicvine.side_effect = fetch_comicvine_side_effect

                # Mock build_comicvine_volume_result to return normalized data
                # Note: build_comicvine_volume_result normalizes publisher and image to strings
                mock_build.return_value = {
                    "id": comicvine_volume_id,
                    "name": "New Series",
                    "start_year": "2025",
                    "publisher": "Test Publisher",  # Normalized to string, not dict
                    "publisher_country": None,
                    "description": "Test description",
                    "site_url": "https://comicvine.gamespot.com/test",
                    "image": "https://example.com/image.jpg",  # Normalized to string, not dict
                    "count_of_issues": 1,
                    "language": None,
                    "volume_tag": None,
                }

                # Process file
                success, error = await _process_pending_file(
                    pending_file,
                    test_import_job,
                    test_library,
                    session,
                )

                # The volume creation might have failed, but we need to check if it actually succeeded
                # Let's verify the mocks were called and check the database
                from sqlmodel import select

                volumes_check = await session.exec(
                    select(LibraryVolume).where(
                        LibraryVolume.comicvine_id == comicvine_volume_id,
                        LibraryVolume.library_id == test_library.id,
                    )
                )
                volumes_check.all()  # Check if volumes exist

                assert success is True, f"Processing failed: {error}"

                # Verify volume was created
                from sqlmodel import select

                volumes_result = await session.exec(
                    select(LibraryVolume).where(
                        LibraryVolume.comicvine_id == comicvine_volume_id,
                        LibraryVolume.library_id == test_library.id,
                    )
                )
                volumes = volumes_result.all()
                assert len(volumes) == 1

                volume = volumes[0]
                assert volume.title == "New Series"

                # Verify issue was created
                issues_result = await session.exec(
                    select(LibraryIssue).where(LibraryIssue.volume_id == volume.id)
                )
                issues = issues_result.all()
                assert len(issues) == 1

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_handles_missing_file(
        self,
        session: AsyncSession,
        test_import_job: ImportJob,
        test_library: Library,
        test_volume: LibraryVolume,
        test_issue: LibraryIssue,
    ):
        """Test that missing file is handled gracefully."""
        # Create pending file pointing to non-existent file
        pending_file = ImportPendingFile(
            id=uuid.uuid4().hex,
            import_job_id=test_import_job.id,
            file_path="/nonexistent/file.cbz",
            file_name="Missing File.cbz",
            file_size=1000,
            file_extension=".cbz",
            status="import",
            matched_volume_id=test_volume.id,
            matched_issue_id=test_issue.id,
            matched_confidence=1.0,
        )
        session.add(pending_file)
        await session.commit()

        # Process file
        success, error = await _process_pending_file(
            pending_file,
            test_import_job,
            test_library,
            session,
        )

        # Should fail
        assert success is False
        assert error is not None
        assert "not found" in error.lower() or "does not exist" in error.lower()

    @pytest.mark.asyncio
    async def test_links_file_when_link_files_enabled(
        self,
        session: AsyncSession,
        test_library: Library,
        test_volume: LibraryVolume,
        test_issue: LibraryIssue,
    ):
        """Test that file is linked when link_files is True."""
        # Create import job with link_files=True
        job = ImportJob(
            id=uuid.uuid4().hex,
            library_id=test_library.id,
            scan_type="external_folder",
            folder_path="/test/folder",
            link_files=True,  # Enable linking
            status="pending_review",
        )
        session.add(job)
        await session.commit()

        # Create temp file
        temp_dir = Path(tempfile.mkdtemp())
        source_file = temp_dir / "Batman #1.cbz"
        source_file.write_bytes(b"fake comic data" * 1000)

        try:
            pending_file = ImportPendingFile(
                id=uuid.uuid4().hex,
                import_job_id=job.id,
                file_path=str(source_file),
                file_name="Batman #1.cbz",
                file_size=source_file.stat().st_size,
                file_extension=".cbz",
                status="import",
                matched_volume_id=test_volume.id,
                matched_issue_id=test_issue.id,
                matched_confidence=1.0,
            )
            session.add(pending_file)
            await session.commit()

            # Process file
            success, error = await _process_pending_file(
                pending_file,
                job,
                test_library,
                session,
            )

            assert success is True

            # Verify original file still exists (linked, not moved)
            assert source_file.exists()

            # Verify link was created
            await session.refresh(test_issue)
            assert test_issue.file_path is not None

            library_path = Path(test_library.library_root) / test_issue.file_path
            assert library_path.exists()
            assert library_path.is_symlink()  # Should be a symlink

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
