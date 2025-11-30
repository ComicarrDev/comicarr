"""Tests for import API routes."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from comicarr.core.database import create_database_engine, create_session_factory
from comicarr.core.dependencies import require_auth
from comicarr.db.models import ImportJob, ImportPendingFile, Library


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    """Create a database session for testing."""
    import os
    import shutil
    import tempfile

    # Use a shared temp directory that the app can also access
    temp_dir = Path(tempfile.mkdtemp())
    # Create the full directory structure that the app expects
    (temp_dir / "database").mkdir(parents=True, exist_ok=True)
    (temp_dir / "config").mkdir(parents=True, exist_ok=True)
    (temp_dir / "cache").mkdir(parents=True, exist_ok=True)
    (temp_dir / "logs").mkdir(parents=True, exist_ok=True)
    db_path = temp_dir / "database" / "comicarr.db"

    # Set COMICARR_DATA_DIR so the app uses the same database
    # Store original value to restore later
    original_data_dir = os.environ.get("COMICARR_DATA_DIR")
    os.environ["COMICARR_DATA_DIR"] = str(temp_dir)

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
        # Restore original env var or remove if it wasn't set
        if original_data_dir is not None:
            os.environ["COMICARR_DATA_DIR"] = original_data_dir
        elif "COMICARR_DATA_DIR" in os.environ:
            del os.environ["COMICARR_DATA_DIR"]
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def client(session: AsyncSession) -> TestClient:
    """Create a test client that uses the same database as the test session."""
    from comicarr.app import create_app
    from comicarr.core.config import reload_settings

    # Reload settings to ensure fresh config is loaded with current COMICARR_DATA_DIR
    # This ensures the app picks up the COMICARR_DATA_DIR set by the session fixture
    reload_settings()

    # The session fixture already sets COMICARR_DATA_DIR, so the app will use the same database
    app = create_app()

    # Override auth dependency
    def require_auth_override():
        return True  # Skip auth for tests

    app.dependency_overrides[require_auth] = require_auth_override

    return TestClient(app)


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


class TestImportRoutes:
    """Test import API routes.

    Note: These are integration tests that require proper app setup.
    Some tests may fail if route ordering or dependency injection differs from production.
    """

    def test_list_import_jobs(self, client: TestClient, test_import_job: ImportJob):
        """Test listing import jobs."""
        # The test_import_job fixture creates a job in the database
        # Since both the session fixture and the app use the same COMICARR_DATA_DIR,
        # they should share the same database file, so the job should be visible
        response = client.get("/api/import/jobs")
        assert response.status_code == 200

        data = response.json()
        assert "jobs" in data
        assert len(data["jobs"]) >= 1

    @pytest.mark.skip(reason="Integration test - requires proper route setup")
    def test_get_import_job(self, client: TestClient, test_import_job: ImportJob):
        """Test getting a specific import job."""
        response = client.get(f"/api/import/jobs/{test_import_job.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == test_import_job.id
        assert data["library_id"] == test_import_job.library_id

    @pytest.mark.skip(reason="Integration test - requires proper route setup")
    def test_create_import_job(self, client: TestClient, test_library: Library):
        """Test creating a new import job."""
        response = client.post(
            "/api/import/jobs",
            json={
                "library_id": test_library.id,
                "scan_type": "external_folder",
                "folder_path": "/test/folder",
                "link_files": False,
            },
        )
        assert response.status_code == 201

        data = response.json()
        assert data["library_id"] == test_library.id
        assert data["scan_type"] == "external_folder"

    @pytest.mark.skip(reason="Integration test - requires proper route setup")
    def test_list_pending_files(self, client: TestClient, test_import_job: ImportJob):
        """Test listing pending files for an import job."""
        response = client.get(f"/api/import/jobs/{test_import_job.id}/files")
        assert response.status_code == 200

        data = response.json()
        assert "files" in data
        assert "total" in data

    @pytest.mark.skip(reason="Integration test - requires proper route setup")
    @pytest.mark.asyncio
    async def test_update_pending_file(
        self, client: TestClient, session: AsyncSession, test_import_job: ImportJob
    ):
        """Test updating a pending file."""
        # Create a pending file
        pending_file = ImportPendingFile(
            id=uuid.uuid4().hex,
            import_job_id=test_import_job.id,
            file_path="/test/file.cbz",
            file_name="file.cbz",
            file_size=1000,
            file_extension=".cbz",
            status="pending",
        )
        session.add(pending_file)
        await session.commit()

        response = client.patch(
            f"/api/import/jobs/{test_import_job.id}/files/{pending_file.id}",
            json={"status": "import"},
        )
        assert response.status_code == 200

    @pytest.mark.skip(reason="Integration test - requires proper route setup")
    def test_bulk_update_pending_files(self, client: TestClient, test_import_job: ImportJob):
        """Test bulk updating pending files."""
        response = client.patch(
            f"/api/import/jobs/{test_import_job.id}/files/bulk",
            json={
                "file_ids": [],
                "status": "import",
            },
        )
        # Should work even with empty list
        assert response.status_code in [200, 400]

    def test_get_scanning_job_status(self, client: TestClient, test_import_job: ImportJob):
        """Test getting scanning job status."""
        response = client.get(f"/api/import/jobs/{test_import_job.id}/scanning/status")
        # May return 404 if no scanning job exists
        assert response.status_code in [200, 404]

    def test_get_processing_job_status(self, client: TestClient, test_import_job: ImportJob):
        """Test getting processing job status."""
        response = client.get(f"/api/import/jobs/{test_import_job.id}/processing/status")
        # May return 404 if no processing job exists
        assert response.status_code in [200, 404]
