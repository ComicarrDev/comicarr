"""Tests for middleware functionality."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from comicarr.app import create_app


@pytest.fixture(autouse=True)
def reset_prometheus_registry():
    """Reset Prometheus registry before each test to avoid duplicate metric errors."""
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    app = create_app()
    return TestClient(app)


def test_trace_id_header_added_to_response(client: TestClient) -> None:
    """Test that X-Trace-ID header is added to responses."""
    response = client.get("/api/")

    assert response.status_code == 200
    assert "X-Trace-ID" in response.headers

    trace_id = response.headers["X-Trace-ID"]
    assert isinstance(trace_id, str)
    assert len(trace_id) == 32  # UUID4 hex = 32 characters


def test_trace_id_header_preserved(client: TestClient) -> None:
    """Test that existing X-Trace-ID header is preserved."""
    trace_id = "custom-trace-id-12345678901234567890123456789012"  # 32 chars

    response = client.get("/api/", headers={"X-Trace-ID": trace_id})

    assert response.status_code == 200
    assert response.headers["X-Trace-ID"] == trace_id


def test_trace_id_in_response_body(client: TestClient) -> None:
    """Test that trace_id is included in response body."""
    response = client.get("/api/")

    assert response.status_code == 200
    data = response.json()

    assert "trace_id" in data
    assert isinstance(data["trace_id"], str)
    assert len(data["trace_id"]) == 32


def test_trace_id_consistent_across_request(client: TestClient) -> None:
    """Test that trace_id is consistent throughout a request."""
    response = client.get("/api/")

    assert response.status_code == 200

    # Trace ID from header
    header_trace_id = response.headers["X-Trace-ID"]

    # Trace ID from body
    data = response.json()
    body_trace_id = data.get("trace_id")

    # They should match
    assert header_trace_id == body_trace_id


def test_trace_id_different_for_each_request(client: TestClient) -> None:
    """Test that each request gets a different trace ID."""
    response1 = client.get("/api/")
    response2 = client.get("/api/")

    trace_id1 = response1.headers["X-Trace-ID"]
    trace_id2 = response2.headers["X-Trace-ID"]

    # Should be different (extremely unlikely to be the same)
    assert trace_id1 != trace_id2


def test_health_endpoint_has_trace_id(client: TestClient) -> None:
    """Test that health endpoint also includes trace ID."""
    response = client.get("/api/health")

    assert response.status_code == 200
    assert "X-Trace-ID" in response.headers

    data = response.json()
    assert "trace_id" in data
