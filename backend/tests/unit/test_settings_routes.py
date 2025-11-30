"""Tests for settings API routes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from comicarr.app import create_app
from comicarr.core.config import reload_settings
from comicarr.core.security import SecurityConfig


@pytest.fixture
def temp_data_dir(monkeypatch, tmp_path: Path):
    """Create a temporary data directory for testing."""
    # Create subdirectories
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "database").mkdir(parents=True)

    # Override data_dir in settings
    settings = reload_settings()
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    return tmp_path


@pytest.fixture
def client(temp_data_dir: Path) -> TestClient:
    """Create test client with temporary data directory."""
    app = create_app()
    return TestClient(app)


def test_get_host_settings_defaults(client: TestClient) -> None:
    """Test getting host settings with defaults."""
    response = client.get("/api/settings/host")
    assert response.status_code == 200
    data = response.json()

    assert "bind_address" in data
    assert "port" in data
    assert "base_url" in data
    # Values may differ if settings.json exists, but structure should be correct
    assert isinstance(data["bind_address"], str)
    assert isinstance(data["port"], int)
    assert isinstance(data["base_url"], str)


def test_update_host_settings(client: TestClient, temp_data_dir: Path) -> None:
    """Test updating host settings."""
    payload = {"bind_address": "0.0.0.0", "port": 9000, "base_url": "/comicarr"}

    response = client.put("/api/settings/host", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["bind_address"] == "0.0.0.0"
    assert data["port"] == 9000
    assert data["base_url"] == "/comicarr"

    # Verify settings were saved to file in nested format
    settings_file = temp_data_dir / "config" / "settings.json"
    assert settings_file.exists()

    with settings_file.open() as f:
        saved_data = json.load(f)

    assert "host" in saved_data
    assert saved_data["host"]["bind_address"] == "0.0.0.0"
    assert saved_data["host"]["port"] == 9000
    assert saved_data["host"]["base_url"] == "/comicarr"


def test_update_host_settings_invalid_port(client: TestClient) -> None:
    """Test updating host settings with invalid port."""
    payload = {"bind_address": "127.0.0.1", "port": 70000, "base_url": ""}  # Invalid

    response = client.put("/api/settings/host", json=payload)
    assert response.status_code == 400


def test_update_host_settings_invalid_base_url(client: TestClient) -> None:
    """Test updating host settings with invalid base_url."""
    payload = {
        "bind_address": "127.0.0.1",
        "port": 8000,
        "base_url": "invalid",  # Must start with /
    }

    response = client.put("/api/settings/host", json=payload)
    assert response.status_code == 400


def test_get_security_settings_defaults(client: TestClient) -> None:
    """Test getting security settings with defaults."""
    response = client.get("/api/settings/security")
    assert response.status_code == 200
    data = response.json()

    assert data["auth_method"] == "none"
    assert data["username"] is None
    assert data["has_password"] is False
    assert data["api_key"] is None
    assert data["has_api_key"] is False


def test_update_security_settings_forms_auth(client: TestClient, temp_data_dir: Path) -> None:
    """Test updating security settings to enable forms auth."""
    payload = {"auth_method": "forms", "username": "testuser", "password": "testpass123"}

    response = client.put("/api/settings/security", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["auth_method"] == "forms"
    assert data["username"] == "testuser"
    assert data["has_password"] is True

    # Verify security config was saved
    security_file = temp_data_dir / "config" / "security.json"
    assert security_file.exists()

    config = SecurityConfig.load()
    assert config is not None
    assert config.auth_method == "forms"
    assert config.username == "testuser"
    assert config.password_hash is not None


def test_update_security_settings_api_key(client: TestClient, temp_data_dir: Path) -> None:
    """Test updating security settings API key."""
    payload = {
        "auth_method": "none",
        "api_key": "test-api-key-1234567890123456789012345678901234567890",
    }

    response = client.put("/api/settings/security", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["api_key"] == "test-api-key-1234567890123456789012345678901234567890"
    assert data["has_api_key"] is True

    # Verify security config was saved
    config = SecurityConfig.load()
    assert config is not None
    assert config.api_key == "test-api-key-1234567890123456789012345678901234567890"


def test_update_security_settings_clear_api_key(client: TestClient, temp_data_dir: Path) -> None:
    """Test clearing API key by setting it to empty string."""
    # First set an API key
    payload1 = {"auth_method": "none", "api_key": "test-key"}
    client.put("/api/settings/security", json=payload1)

    # Then clear it
    payload2 = {"auth_method": "none", "api_key": ""}
    response = client.put("/api/settings/security", json=payload2)
    assert response.status_code == 200
    data = response.json()

    assert data["api_key"] is None
    assert data["has_api_key"] is False


def test_get_external_apis_defaults(client: TestClient) -> None:
    """Test getting external APIs settings with defaults."""
    response = client.get("/api/settings/external-apis")
    assert response.status_code == 200
    data = response.json()

    assert "comicvine" in data
    comicvine = data["comicvine"]
    assert comicvine["api_key"] is None
    assert comicvine["base_url"] == "https://comicvine.gamespot.com/api"
    assert comicvine["enabled"] is False


def test_update_external_apis_comicvine(client: TestClient, temp_data_dir: Path) -> None:
    """Test updating Comicvine external API settings."""
    payload = {
        "comicvine": {
            "api_key": "test-key-123",
            "base_url": "https://comicvine.gamespot.com/api",
            "enabled": True,
        }
    }

    response = client.put("/api/settings/external-apis", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["comicvine"]["api_key"] == "test-key-123"
    assert data["comicvine"]["enabled"] is True

    # Verify settings were saved to file
    settings_file = temp_data_dir / "config" / "settings.json"
    assert settings_file.exists()

    with settings_file.open() as f:
        saved_data = json.load(f)

    assert "external_apis" in saved_data
    assert saved_data["external_apis"]["comicvine"]["api_key"] == "test-key-123"
    assert saved_data["external_apis"]["comicvine"]["enabled"] is True
