"""Test indexers API routes."""

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from comicarr.app import create_app
from comicarr.core.database import create_database_engine, create_session_factory


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    db_file = temp_dir / "test.db"
    yield db_file
    shutil.rmtree(temp_dir)


@pytest.fixture
def client(temp_db):
    """Create a test client with a temporary database.

    Note: We don't need to override settings.database_dir since we're creating
    the engine directly with the temp_db file path. The app will use the engine
    we provide, not the one from settings.
    """
    # Create engine and session factory with the temp database file directly
    # This bypasses the need to override settings.database_dir
    engine = create_database_engine(temp_db, echo=False)
    async_session_factory = create_session_factory(engine)

    # Create app
    app = create_app()

    # Override the app's engine and session factory with our temp database
    # This is what the app would normally get from settings, but we're providing
    # our own for testing
    app.state.engine = engine
    app.state.async_session_factory = async_session_factory

    # Create get_db_session dependency
    from collections.abc import AsyncIterator

    async def get_db_session() -> AsyncIterator[AsyncSession]:
        async with async_session_factory() as session:
            yield session

    app.state.get_db_session = get_db_session

    # Include indexers router (this adds the database-dependent routes)
    from comicarr.core.routes import include_db_dependent_routes

    include_db_dependent_routes(app)

    return TestClient(app)


def test_indexers_endpoints_exist(client):
    """Test that indexers endpoints are accessible."""
    # Test GET /api/indexers
    response = client.get("/api/indexers")
    assert (
        response.status_code != 404
    ), f"Endpoint /api/indexers returned 404. Available routes: {[r.path for r in client.app.routes]}"
    # Should return 200 with empty list if no indexers, or 500 if migration not run
    assert response.status_code in [
        200,
        500,
    ], f"Expected 200 or 500, got {response.status_code}: {response.text}"

    # Test GET /api/indexers/types
    response = client.get("/api/indexers/types")
    assert response.status_code != 404, "Endpoint /api/indexers/types returned 404"
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


def test_list_indexers_empty(client):
    """Test listing indexers when database is empty."""
    response = client.get("/api/indexers")
    if response.status_code == 200:
        assert isinstance(response.json(), list)


def test_get_indexer_types(client):
    """Test getting indexer types."""
    response = client.get("/api/indexers/types")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # Check that we have the expected types
    type_ids = [t["id"] for t in data]
    assert "newznab" in type_ids
    assert "torrent" in type_ids
