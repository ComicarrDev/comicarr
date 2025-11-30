"""Tests for metrics functionality."""

import pytest
from fastapi.testclient import TestClient

from comicarr.app import create_app

# Note: Prometheus registry reset is now handled globally in conftest.py


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    app = create_app()
    # Metrics are now set up in create_app() when base_url is not set
    return TestClient(app)


def test_metrics_endpoint(client: TestClient) -> None:
    """Test Prometheus metrics endpoint exists and returns metrics."""
    response = client.get("/metrics")
    assert response.status_code == 200
    # Prometheus format: text/plain; version=1.0.0; charset=utf-8
    assert "text/plain" in response.headers["content-type"]
    assert "charset=utf-8" in response.headers["content-type"]

    content = response.text
    # Check that Prometheus metrics are present (prometheus-fastapi-instrumentator creates these)
    assert "http_requests_total" in content or "http_request_duration" in content
    assert "HELP" in content  # Prometheus metrics format includes HELP comments
    assert "TYPE" in content  # Prometheus metrics format includes TYPE comments


def test_metrics_collect_after_request(client: TestClient) -> None:
    """Test that metrics are collected after making requests."""
    # Make a request to generate metrics
    client.get("/api/")

    # Check metrics endpoint
    response = client.get("/metrics")
    assert response.status_code == 200
    content = response.text

    # Should have metrics for our request
    assert "/api/" in content or "/api" in content
