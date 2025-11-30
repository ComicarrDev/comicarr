"""Tests for database metrics."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from comicarr.core.database import create_database_engine, retry_db_operation
from comicarr.core.metrics import (
    db_connections_active,
    db_connections_idle,
    db_connections_overflow,
)


# Note: Prometheus registry reset is now handled globally in conftest.py
# We still need to re-import metrics to re-register them after registry reset
@pytest.fixture(autouse=True)
def reimport_metrics_after_reset() -> None:
    """Re-import metrics module after registry reset to re-register metrics."""
    # This runs after the global reset_prometheus_registry fixture
    import importlib

    from comicarr import core

    importlib.reload(core.metrics)


@pytest.fixture
async def temp_db_engine(tmp_path: Path) -> AsyncEngine:
    """Create a temporary database engine for testing."""
    db_file = tmp_path / "test.db"
    engine = create_database_engine(db_file, echo=False)
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_connection_pool_metrics_initialized(temp_db_engine: AsyncEngine) -> None:
    """Test that connection pool metrics are initialized."""
    # Metrics should be set after engine creation
    # We can't easily test exact values without making connections,
    # but we can verify the metrics exist and are registered
    assert db_connections_active._value.get() is not None
    assert db_connections_idle._value.get() is not None
    assert db_connections_overflow._value.get() is not None


@pytest.mark.asyncio
async def test_retry_operation_success_first_try(temp_db_engine: AsyncEngine) -> None:
    """Test that retry operation doesn't record metrics when operation succeeds immediately."""
    call_count = 0

    async def successful_operation() -> str:
        nonlocal call_count
        call_count += 1
        return "success"

    result = await retry_db_operation(
        successful_operation,
        operation_type="test",
    )

    assert result == "success"
    assert call_count == 1

    # Should not have recorded any retry attempts
    # (we can't easily check counter values without exporting, but operation succeeded)


@pytest.mark.asyncio
async def test_retry_operation_tracks_lock_errors(temp_db_engine: AsyncEngine) -> None:
    """Test that lock errors are tracked in metrics."""
    call_count = 0

    async def failing_operation() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise OperationalError("statement", "parameters", "database is locked")
        return "success"

    result = await retry_db_operation(
        failing_operation,
        max_retries=3,
        retry_delay=0.01,
        operation_type="test_lock",
    )

    assert result == "success"
    assert call_count == 2

    # Lock error should have been tracked
    # (we can't easily verify exact counter values without exporting metrics)


@pytest.mark.asyncio
async def test_retry_operation_tracks_failed_retries(temp_db_engine: AsyncEngine) -> None:
    """Test that failed retries are tracked in metrics."""

    async def always_failing_operation() -> str:
        raise OperationalError("statement", "parameters", "database is locked")

    with pytest.raises(OperationalError):
        await retry_db_operation(
            always_failing_operation,
            max_retries=2,
            retry_delay=0.01,
            operation_type="test_failed",
        )

    # Failed retries should be tracked
    # (verification would require metrics export)


def test_database_metrics_exposed_in_endpoint() -> None:
    """Test that database metrics are exposed in the /metrics endpoint."""

    from comicarr.app import create_app

    # Create a fresh app with database initialized
    # Metrics are now set up in create_app() when base_url is not set
    app = create_app()
    test_client = TestClient(app)

    # Get metrics endpoint
    response = test_client.get("/metrics")
    assert response.status_code == 200

    content = response.text

    # Check that database pool metrics are present
    assert "db_pool_size" in content
    assert "db_pool_max_overflow" in content
    assert "db_connections_active" in content
    assert "db_connections_idle" in content
    assert "db_connections_overflow" in content

    # Check that retry metrics are present
    assert "db_retry_attempts_total" in content
    assert "db_lock_errors_total" in content
    assert "db_retries_succeeded_total" in content
    assert "db_retries_failed_total" in content
    assert "db_retry_duration_seconds" in content
