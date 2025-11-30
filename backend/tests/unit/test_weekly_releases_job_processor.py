"""Tests for weekly releases job processor."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from comicarr.core.database import create_database_engine, create_session_factory
from comicarr.core.weekly_releases.job_processor import process_weekly_release_job
from comicarr.db.models import (
    Library,
    LibraryIssue,
    LibraryVolume,
    WeeklyReleaseItem,
    WeeklyReleaseProcessingJob,
    WeeklyReleaseWeek,
)


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """Create a database session for testing."""
    import shutil
    import tempfile

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
async def test_week(session: AsyncSession) -> WeeklyReleaseWeek:
    """Create a test week."""
    week = WeeklyReleaseWeek(
        id=uuid.uuid4().hex,
        week_start="2025-11-26",
        status="pending",
    )
    session.add(week)
    await session.commit()
    await session.refresh(week)
    return week


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


class TestProcessWeeklyReleaseJob:
    """Test process_weekly_release_job function."""

    @pytest.mark.asyncio
    async def test_processes_items_with_import_status(
        self,
        session: AsyncSession,
        test_library: Library,
        test_week: WeeklyReleaseWeek,
        test_volume: LibraryVolume,
    ):
        """Test that items with 'import' status are processed."""
        # Create issues for the volume
        issue1 = LibraryIssue(
            id=uuid.uuid4().hex,
            volume_id=test_volume.id,
            number="1",
            status="wanted",
        )
        issue2 = LibraryIssue(
            id=uuid.uuid4().hex,
            volume_id=test_volume.id,
            number="2",
            status="wanted",
        )
        session.add(issue1)
        session.add(issue2)
        await session.commit()

        # Create weekly release items with 'import' status
        item1 = WeeklyReleaseItem(
            id=uuid.uuid4().hex,
            week_id=test_week.id,
            title="Batman #1",
            publisher="DC Comics",
            release_date="2025-11-26",
            metadata_json=json.dumps({"series": "Batman", "issue_number": "1"}),
            source="test",
            status="import",
            matched_volume_id=test_volume.id,
            matched_issue_id=issue1.id,
        )
        item2 = WeeklyReleaseItem(
            id=uuid.uuid4().hex,
            week_id=test_week.id,
            title="Batman #2",
            publisher="DC Comics",
            release_date="2025-11-26",
            metadata_json=json.dumps({"series": "Batman", "issue_number": "2"}),
            source="test",
            status="import",
            matched_volume_id=test_volume.id,
            matched_issue_id=issue2.id,
        )
        session.add(item1)
        session.add(item2)
        await session.commit()

        # Create processing job
        job = WeeklyReleaseProcessingJob(
            id=uuid.uuid4().hex,
            week_id=test_week.id,
            status="queued",
            progress_current=0,
            progress_total=2,
        )
        session.add(job)
        await session.commit()

        # Process job
        await process_weekly_release_job(session, job.id)

        # Refresh job
        await session.refresh(job)

        # Verify job completed
        assert job.status == "completed"
        assert job.progress_current == 2
        assert job.progress_total == 2

        # Verify items were marked as processed
        await session.refresh(item1)
        await session.refresh(item2)
        assert item1.status == "processed"
        assert item2.status == "processed"

    @pytest.mark.asyncio
    async def test_creates_volume_from_comicvine_when_needed(
        self, session: AsyncSession, test_library: Library, test_week: WeeklyReleaseWeek
    ):
        """Test that volumes are created from ComicVine when needed."""
        comicvine_id = 12345

        # Create item with ComicVine ID but no library match
        item = WeeklyReleaseItem(
            id=uuid.uuid4().hex,
            week_id=test_week.id,
            title="New Series #1",
            publisher="Test Publisher",
            release_date="2025-11-26",
            metadata_json=json.dumps({"series": "New Series", "issue_number": "1"}),
            source="test",
            status="import",
            comicvine_volume_id=comicvine_id,
            comicvine_issue_id=1001,
        )
        session.add(item)
        await session.commit()

        # Create processing job
        job = WeeklyReleaseProcessingJob(
            id=uuid.uuid4().hex,
            week_id=test_week.id,
            status="queued",
            progress_current=0,
            progress_total=1,
        )
        session.add(job)
        await session.commit()

        # Mock ComicVine API
        volume_data = {
            "id": comicvine_id,
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
                "id": 1001,
                "issue_number": "1",
                "name": "Issue #1",
                "cover_date": "2025-01-01",
                "description": "First issue",
                "site_detail_url": "https://comicvine.gamespot.com/issue1",
                "image": {"medium_url": "https://example.com/issue1.jpg"},
            },
        ]

        with (
            patch("comicarr.core.weekly_releases.processing.fetch_comicvine") as mock_fetch,
            patch("comicarr.routes.volumes.fetch_comicvine_issues") as mock_fetch_issues,
            patch("comicarr.routes.comicvine.fetch_comicvine") as mock_fetch_comicvine,
            patch("comicarr.routes.settings._get_external_apis") as mock_get_apis,
            patch(
                "comicarr.core.weekly_releases.processing._get_external_apis"
            ) as mock_get_apis_processing,
            patch("comicarr.routes.comicvine.normalize_comicvine_payload") as mock_normalize,
            patch("comicarr.routes.volumes.fetch_comicvine") as mock_fetch_comicvine_route,
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

            mock_fetch.return_value = {"results": volume_data}
            mock_fetch_issues.return_value = issues_data
            # Also mock the route-level fetch_comicvine to prevent actual API calls
            # This is called by fetch_comicvine_issues, so it needs to return issues data
            mock_fetch_comicvine_route.return_value = {"results": issues_data}

            # Mock issue fetch (called when processing tries to fetch issue details)
            issue_data_single = {
                "id": 1001,
                "issue_number": "1",
                "name": "Issue #1",
                "cover_date": "2025-01-01",
                "description": "First issue",
                "site_detail_url": "https://comicvine.gamespot.com/issue1",
                "image": {"medium_url": "https://example.com/issue1.jpg"},
            }

            # mock_fetch_comicvine is used for both volume and issue fetches
            def fetch_comicvine_side_effect(normalized, endpoint, params=None):
                if "issue/4000" in endpoint:
                    return {"results": issue_data_single}
                elif "volume/4050" in endpoint:
                    return {"results": volume_data}
                return {"results": {}}

            mock_fetch_comicvine.side_effect = fetch_comicvine_side_effect

            # Process job
            await process_weekly_release_job(session, job.id)

            # Verify volume was created
            from sqlmodel import select

            volumes_result = await session.exec(
                select(LibraryVolume).where(
                    LibraryVolume.comicvine_id == comicvine_id,
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

    @pytest.mark.asyncio
    async def test_handles_processing_errors(
        self, session: AsyncSession, test_library: Library, test_week: WeeklyReleaseWeek
    ):
        """Test that processing errors are tracked correctly."""
        # Create item with invalid ComicVine ID
        item = WeeklyReleaseItem(
            id=uuid.uuid4().hex,
            week_id=test_week.id,
            title="Invalid #1",
            publisher="Test Publisher",
            release_date="2025-11-26",
            metadata_json=json.dumps({"series": "Invalid", "issue_number": "1"}),
            source="test",
            status="import",
            comicvine_volume_id=99999,  # Invalid ID
        )
        session.add(item)
        await session.commit()

        # Create processing job
        job = WeeklyReleaseProcessingJob(
            id=uuid.uuid4().hex,
            week_id=test_week.id,
            status="queued",
            progress_current=0,
            progress_total=1,
        )
        session.add(job)
        await session.commit()

        # Mock ComicVine API to return error
        with (
            patch("comicarr.routes.comicvine.fetch_comicvine") as mock_fetch,
            patch("comicarr.routes.comicvine._get_external_apis") as mock_get_apis,
            patch("comicarr.routes.comicvine.normalize_comicvine_payload") as mock_normalize,
        ):

            mock_get_apis.return_value = {
                "comicvine": {
                    "api_key": "test_key",
                    "enabled": True,
                    "base_url": "https://comicvine.gamespot.com/api",
                }
            }
            mock_normalize.return_value = {
                "api_key": "test_key",
                "enabled": True,
                "base_url": "https://comicvine.gamespot.com/api",
            }

            # Return empty results (volume not found)
            mock_fetch.return_value = {"results": None}

            # Process job
            await process_weekly_release_job(session, job.id)

            # Refresh job
            await session.refresh(job)

            # Verify error was tracked
            assert job.error_count > 0
            # Job should still complete (with errors)
            assert job.status == "completed"

    @pytest.mark.asyncio
    async def test_skips_already_processed_items(
        self,
        session: AsyncSession,
        test_library: Library,
        test_week: WeeklyReleaseWeek,
        test_volume: LibraryVolume,
    ):
        """Test that items already processed are skipped."""
        issue = LibraryIssue(
            id=uuid.uuid4().hex,
            volume_id=test_volume.id,
            number="1",
            status="ready",
        )
        session.add(issue)
        await session.commit()

        # Create item already marked as processed
        item = WeeklyReleaseItem(
            id=uuid.uuid4().hex,
            week_id=test_week.id,
            title="Batman #1",
            publisher="DC Comics",
            release_date="2025-11-26",
            metadata_json=json.dumps({"series": "Batman", "issue_number": "1"}),
            source="test",
            status="processed",  # Already processed
            matched_volume_id=test_volume.id,
            matched_issue_id=issue.id,
        )
        session.add(item)
        await session.commit()

        # Create processing job
        job = WeeklyReleaseProcessingJob(
            id=uuid.uuid4().hex,
            week_id=test_week.id,
            status="queued",
            progress_current=0,
            progress_total=1,
        )
        session.add(job)
        await session.commit()

        # Process job
        await process_weekly_release_job(session, job.id)

        # Refresh job
        await session.refresh(job)

        # Verify job completed (no items to process)
        assert job.status == "completed"
        assert job.progress_current == 0  # No items processed (all skipped)
