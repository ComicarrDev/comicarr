"""Tests for authentication API routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from comicarr.app import create_app
from comicarr.core.config import reload_settings
from comicarr.core.security import SecurityConfig


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
    from prometheus_client import REGISTRY

    REGISTRY._collector_to_names = {}
    REGISTRY._names_to_collectors = {}

    app = create_app()
    return TestClient(app)


def test_session_endpoint_no_config(client: TestClient):
    """Test /api/auth/session when no config exists."""
    response = client.get("/api/auth/session")

    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is False
    assert data["auth_method"] == "none"
    assert data["setup_required"] is True


def test_setup_endpoint(temp_config_dir: Path, client: TestClient):
    """Test initial setup endpoint."""
    response = client.post(
        "/api/auth/setup",
        json={
            "username": "testuser",
            "password": "testpass123",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "Setup completed" in data["message"]

    # Verify config was created
    config = SecurityConfig.load()
    assert config is not None
    assert config.auth_method == "forms"
    assert config.username == "testuser"
    assert config.password_hash is not None


def test_setup_endpoint_already_configured(temp_config_dir: Path, client: TestClient):
    """Test setup endpoint when already configured."""
    # Create existing config
    config = SecurityConfig(
        auth_method="forms",
        username="existing_user",
        password_hash="$2b$12$existing",
    )
    config.save()

    # Try to setup again (should fail)
    response = client.post(
        "/api/auth/setup",
        json={
            "username": "newuser",
            "password": "newpass",
        },
    )

    assert response.status_code == 409
    data = response.json()
    assert "already exists" in data["detail"].lower()


def test_login_endpoint_none_auth(temp_config_dir: Path, client: TestClient):
    """Test login endpoint when auth_method is 'none'."""
    # Create config with 'none' auth
    config = SecurityConfig(auth_method="none")
    config.save()

    response = client.post(
        "/api/auth/login",
        json={
            "username": "any",
            "password": "any",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


def test_login_endpoint_forms_auth(temp_config_dir: Path, client: TestClient):
    """Test login endpoint with forms authentication."""
    # Setup first
    setup_response = client.post(
        "/api/auth/setup",
        json={
            "username": "testuser",
            "password": "testpass123",
        },
    )
    assert setup_response.status_code == 200

    # Now try to login with correct credentials
    login_response = client.post(
        "/api/auth/login",
        json={
            "username": "testuser",
            "password": "testpass123",
        },
    )

    assert login_response.status_code == 200
    data = login_response.json()
    assert data["success"] is True

    # Verify session was created
    session_response = client.get("/api/auth/session")
    assert session_response.status_code == 200
    session_data = session_response.json()
    assert session_data["authenticated"] is True


def test_login_endpoint_wrong_credentials(temp_config_dir: Path, client: TestClient):
    """Test login endpoint with wrong credentials."""
    # Setup first
    setup_response = client.post(
        "/api/auth/setup",
        json={
            "username": "testuser",
            "password": "testpass123",
        },
    )
    assert setup_response.status_code == 200

    # Try to login with wrong password
    login_response = client.post(
        "/api/auth/login",
        json={
            "username": "testuser",
            "password": "wrongpass",
        },
    )

    assert login_response.status_code == 401
    data = login_response.json()
    assert "Invalid" in data["detail"]


def test_logout_endpoint(temp_config_dir: Path, client: TestClient):
    """Test logout endpoint."""
    # Setup and login first
    client.post(
        "/api/auth/setup",
        json={
            "username": "testuser",
            "password": "testpass123",
        },
    )
    client.post(
        "/api/auth/login",
        json={
            "username": "testuser",
            "password": "testpass123",
        },
    )

    # Verify authenticated
    session_response = client.get("/api/auth/session")
    assert session_response.json()["authenticated"] is True

    # Logout
    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 200

    # Verify session is cleared
    session_response = client.get("/api/auth/session")
    assert session_response.json()["authenticated"] is False
