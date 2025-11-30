"""Tests for weekly releases matching job processor."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from comicarr.core.database import create_database_engine, create_session_factory
from comicarr.core.weekly_releases.matching_job_processor import process_matching_job
from comicarr.db.models import (
    Library,
    WeeklyReleaseItem,
    WeeklyReleaseMatchingJob,
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


class TestMatchingJobProcessor:
    """Test process_matching_job function."""

    @pytest.mark.asyncio
    async def test_matches_items_to_comicvine(
        self, session: AsyncSession, test_week: WeeklyReleaseWeek
    ):
        """Test that matching job matches items to ComicVine."""
        # Create items without ComicVine matches
        item1 = WeeklyReleaseItem(
            id=uuid.uuid4().hex,
            week_id=test_week.id,
            title="Test Series #1",
            publisher="Test Publisher",
            release_date="2025-11-26",
            metadata_json=json.dumps({"series": "Test Series", "issue_number": "1"}),
            source="test",
            status="pending",
        )
        session.add(item1)
        await session.commit()

        # Create matching job with entry_ids
        job = WeeklyReleaseMatchingJob(
            id=uuid.uuid4().hex,
            week_id=test_week.id,
            match_type="comicvine",
            status="queued",
            progress_current=0,
            progress_total=1,
            entry_ids=[item1.id],  # Set entry_ids so job knows which items to match
        )
        session.add(job)
        await session.commit()

        with (
            patch(
                "comicarr.core.weekly_releases.matching.match_weekly_release_to_comicvine"
            ) as mock_match,
            patch(
                "comicarr.core.weekly_releases.matching._search_comicvine_for_file"
            ) as mock_search,
        ):
            # Mock the matching function to return a match
            mock_match.return_value = {
                "matched": True,
                "comicvine_volume_id": 12345,
                "comicvine_issue_id": 1001,
                "confidence": 0.9,
            }
            # Also mock the internal search function to prevent API calls
            mock_search.return_value = None

            # Process job
            await process_matching_job(session, job.id)

            # Refresh job
            await session.refresh(job)

            # Verify job completed
            assert job.status == "completed"
            assert job.progress_current == 1

    @pytest.mark.asyncio
    async def test_matches_items_to_library(
        self, session: AsyncSession, test_library: Library, test_week: WeeklyReleaseWeek
    ):
        """Test that matching job matches items to library."""
        from comicarr.db.models import LibraryIssue, LibraryVolume

        # Create library volume and issue
        volume = LibraryVolume(
            id=uuid.uuid4().hex,
            library_id=test_library.id,
            title="Test Series",
            publisher="Test Publisher",
            year=2025,
        )
        session.add(volume)

        issue = LibraryIssue(
            id=uuid.uuid4().hex,
            volume_id=volume.id,
            number="1",
            status="wanted",
        )
        session.add(issue)
        await session.commit()

        # Create item that should match
        item = WeeklyReleaseItem(
            id=uuid.uuid4().hex,
            week_id=test_week.id,
            title="Test Series #1",
            publisher="Test Publisher",
            release_date="2025-11-26",
            metadata_json=json.dumps({"series": "Test Series", "issue_number": "1"}),
            source="test",
            status="pending",
        )
        session.add(item)
        await session.commit()

        # Create matching job with entry_ids
        job = WeeklyReleaseMatchingJob(
            id=uuid.uuid4().hex,
            week_id=test_week.id,
            match_type="library",
            status="queued",
            progress_current=0,
            progress_total=1,
            entry_ids=[item.id],  # Set entry_ids so job knows which items to match
        )
        session.add(job)
        await session.commit()

        # Process job
        await process_matching_job(session, job.id)

        # Refresh job and item
        await session.refresh(job)
        await session.refresh(item)

        # Verify job completed
        assert job.status == "completed"

        # Verify item was matched
        assert item.matched_volume_id == volume.id
        assert item.matched_issue_id == issue.id
        assert item.status == "import"  # Should be marked for import if issue has no file
