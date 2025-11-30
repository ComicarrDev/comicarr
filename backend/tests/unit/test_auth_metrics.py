"""Tests for authentication metrics."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from comicarr.app import create_app
from comicarr.core.config import reload_settings
from comicarr.core.metrics import auth_login_failures_total


@pytest.fixture
def temp_config_dir(monkeypatch, tmp_path: Path):
    """Create a temporary config directory for testing."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    # Override data_dir in settings (config_dir is a property derived from data_dir)
    settings = reload_settings()
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    return config_dir


@pytest.fixture
def client(temp_config_dir: Path):
    """Create a test client."""
    # Clear Prometheus registry to avoid duplicate metric registration
    REGISTRY._collector_to_names = {}
    REGISTRY._names_to_collectors = {}

    app = create_app()
    return TestClient(app)


def test_login_failure_invalid_username_metric(temp_config_dir: Path, client: TestClient):
    """Test that login failure with invalid username increments metric."""
    # Setup authentication first
    setup_response = client.post(
        "/api/auth/setup",
        json={
            "username": "testuser",
            "password": "testpass123",
        },
    )
    assert setup_response.status_code == 200

    # Reset metric to known state
    auth_login_failures_total._metrics.clear()

    # Try to login with wrong username
    login_response = client.post(
        "/api/auth/login",
        json={
            "username": "wronguser",
            "password": "testpass123",
        },
    )

    assert login_response.status_code == 401

    # Check that metric was incremented
    metric_value = auth_login_failures_total.labels(reason="invalid_username")._value._value
    assert metric_value == 1.0


def test_login_failure_invalid_password_metric(temp_config_dir: Path, client: TestClient):
    """Test that login failure with invalid password increments metric."""
    # Setup authentication first
    setup_response = client.post(
        "/api/auth/setup",
        json={
            "username": "testuser",
            "password": "testpass123",
        },
    )
    assert setup_response.status_code == 200

    # Reset metric to known state
    auth_login_failures_total._metrics.clear()

    # Try to login with wrong password
    login_response = client.post(
        "/api/auth/login",
        json={
            "username": "testuser",
            "password": "wrongpass",
        },
    )

    assert login_response.status_code == 401

    # Check that metric was incremented
    metric_value = auth_login_failures_total.labels(reason="invalid_password")._value._value
    assert metric_value == 1.0


def test_login_failure_not_configured_metric(temp_config_dir: Path, client: TestClient):
    """Test that login failure when not configured increments metric."""
    # Reset metric to known state
    auth_login_failures_total._metrics.clear()

    # Try to login without setup
    login_response = client.post(
        "/api/auth/login",
        json={
            "username": "testuser",
            "password": "testpass123",
        },
    )

    assert login_response.status_code == 503

    # Check that metric was incremented
    metric_value = auth_login_failures_total.labels(reason="not_configured")._value._value
    assert metric_value == 1.0


def test_login_success_no_metric_increment(temp_config_dir: Path, client: TestClient):
    """Test that successful login does not increment failure metric."""
    # Setup authentication first
    setup_response = client.post(
        "/api/auth/setup",
        json={
            "username": "testuser",
            "password": "testpass123",
        },
    )
    assert setup_response.status_code == 200

    # Reset metric to known state
    auth_login_failures_total._metrics.clear()

    # Login successfully
    login_response = client.post(
        "/api/auth/login",
        json={
            "username": "testuser",
            "password": "testpass123",
        },
    )

    assert login_response.status_code == 200

    # Check that no metrics were incremented (all should be 0 or not exist)
    # We can't easily check for "doesn't exist", but we can verify values are 0
    for reason in ["invalid_username", "invalid_password", "not_configured"]:
        try:
            metric_value = auth_login_failures_total.labels(reason=reason)._value._value
            assert metric_value == 0.0
        except KeyError:
            # Metric label doesn't exist yet, which is fine
            pass
