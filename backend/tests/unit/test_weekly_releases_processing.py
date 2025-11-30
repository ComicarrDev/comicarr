"""Tests for weekly releases processing functionality."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from comicarr.core.database import create_database_engine, create_session_factory
from comicarr.core.weekly_releases.processing import _create_volume_from_comicvine
from comicarr.db.models import (
    Library,
    LibraryIssue,
    LibraryVolume,
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


class TestCreateVolumeFromComicVine:
    """Test _create_volume_from_comicvine function."""

    @pytest.mark.asyncio
    async def test_creates_volume_with_issues(self, session: AsyncSession, test_library: Library):
        """Test that volume is created with all issues from ComicVine."""
        comicvine_id = 12345

        # Mock ComicVine API responses
        volume_data = {
            "id": comicvine_id,
            "name": "Test Volume",
            "start_year": "2025",
            "publisher": {"name": "Test Publisher"},
            "description": "Test description",
            "site_detail_url": "https://comicvine.gamespot.com/test",
            "image": {"medium_url": "https://example.com/image.jpg"},
            "count_of_issues": 2,
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
            {
                "id": 1002,
                "issue_number": "2",
                "name": "Issue #2",
                "cover_date": "2025-02-01",
                "description": "Second issue",
                "site_detail_url": "https://comicvine.gamespot.com/issue2",
                "image": {"medium_url": "https://example.com/issue2.jpg"},
            },
        ]

        with (
            patch("comicarr.core.weekly_releases.processing.fetch_comicvine") as mock_fetch,
            patch(
                "comicarr.core.weekly_releases.processing.fetch_comicvine_issues"
            ) as mock_fetch_issues,
            patch("comicarr.core.weekly_releases.processing._get_external_apis") as mock_get_apis,
            patch(
                "comicarr.core.weekly_releases.processing.normalize_comicvine_payload"
            ) as mock_normalize,
        ):

            # Setup mocks
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

            mock_fetch.return_value = {"results": volume_data}
            mock_fetch_issues.return_value = issues_data

            # Create volume
            volume = await _create_volume_from_comicvine(
                session=session,
                comicvine_id=comicvine_id,
                library_id=test_library.id,
            )

            # Verify volume was created
            assert volume is not None
            assert volume.comicvine_id == comicvine_id
            assert volume.title == "Test Volume"
            assert volume.library_id == test_library.id

            # Verify issues were created
            from sqlmodel import select

            issues_result = await session.exec(
                select(LibraryIssue).where(LibraryIssue.volume_id == volume.id)
            )
            issues = issues_result.all()
            assert len(issues) == 2

            # Verify issue details
            issue1 = next((i for i in issues if i.number == "1"), None)
            assert issue1 is not None
            assert issue1.comicvine_id == 1001
            assert issue1.title == "Issue #1"

            issue2 = next((i for i in issues if i.number == "2"), None)
            assert issue2 is not None
            assert issue2.comicvine_id == 1002
            assert issue2.title == "Issue #2"

    @pytest.mark.asyncio
    async def test_returns_existing_volume(self, session: AsyncSession, test_library: Library):
        """Test that existing volume is returned instead of creating duplicate."""
        comicvine_id = 12345

        # Create existing volume
        existing_volume = LibraryVolume(
            id=uuid.uuid4().hex,
            library_id=test_library.id,
            title="Existing Volume",
            comicvine_id=comicvine_id,
        )
        session.add(existing_volume)
        await session.commit()

        # Try to create volume with same ComicVine ID
        volume = await _create_volume_from_comicvine(
            session=session,
            comicvine_id=comicvine_id,
            library_id=test_library.id,
        )

        # Should return existing volume
        assert volume.id == existing_volume.id
        assert volume.title == "Existing Volume"

        # Verify no duplicate was created
        from sqlmodel import select

        volumes_result = await session.exec(
            select(LibraryVolume).where(
                LibraryVolume.comicvine_id == comicvine_id,
                LibraryVolume.library_id == test_library.id,
            )
        )
        volumes = volumes_result.all()
        assert len(volumes) == 1

    @pytest.mark.asyncio
    async def test_handles_missing_comicvine_data(
        self, session: AsyncSession, test_library: Library
    ):
        """Test that missing ComicVine data raises appropriate error."""
        comicvine_id = 99999

        with (
            patch("comicarr.core.weekly_releases.processing.fetch_comicvine") as mock_fetch,
            patch("comicarr.core.weekly_releases.processing._get_external_apis") as mock_get_apis,
            patch(
                "comicarr.core.weekly_releases.processing.normalize_comicvine_payload"
            ) as mock_normalize,
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

            # Return empty results
            mock_fetch.return_value = {"results": None}

            # Should raise ValueError
            with pytest.raises(ValueError, match="ComicVine volume.*not found"):
                await _create_volume_from_comicvine(
                    session=session,
                    comicvine_id=comicvine_id,
                    library_id=test_library.id,
                )
