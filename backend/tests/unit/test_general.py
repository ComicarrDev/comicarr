"""Tests for general routes."""

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from comicarr.app import create_app


@pytest.fixture(autouse=True)
def reset_prometheus_registry():
    """Reset Prometheus registry before each test to avoid duplicate metric errors.

    This is needed because prometheus-fastapi-instrumentator registers metrics
    in the global registry, and creating the app multiple times would cause
    duplicate registration errors.
    """
    # Clear all collectors from the registry
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    app = create_app()
    return TestClient(app)


def test_root_endpoint(client: TestClient) -> None:
    """Test root endpoint returns hello world."""
    response = client.get("/api/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Hello, Comicarr!"
    assert data["version"] == "0.1.0"
    assert data["status"] == "ok"
    # Trace ID should be included
    assert "trace_id" in data
    assert isinstance(data["trace_id"], str)


def test_health_endpoint(client: TestClient) -> None:
    """Test health endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    # Trace ID should be included
    assert "trace_id" in data
    assert isinstance(data["trace_id"], str)
