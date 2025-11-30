"""Tests for security configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_security_config_defaults():
    """Test SecurityConfig default values."""
    config = SecurityConfig()

    assert config.auth_method == "none"
    assert config.username is None
    assert config.password_hash is None


def test_security_config_forms():
    """Test SecurityConfig with forms authentication."""
    config = SecurityConfig(
        auth_method="forms",
        username="testuser",
        password_hash="$2b$12$testhash",
    )

    assert config.auth_method == "forms"
    assert config.username == "testuser"
    assert config.password_hash == "$2b$12$testhash"


def test_security_config_exists(temp_config_dir: Path):
    """Test checking if security config file exists."""
    config = SecurityConfig()

    # File should not exist initially
    assert config.exists() is False

    # Create the file
    security_file = temp_config_dir / "security.json"
    security_file.write_text('{"auth_method": "none"}')

    # Now it should exist
    assert config.exists() is True


def test_security_config_load_nonexistent(temp_config_dir: Path):
    """Test loading security config when file doesn't exist."""
    config = SecurityConfig.load()

    assert config is None


def test_security_config_load_existing(temp_config_dir: Path):
    """Test loading existing security config."""
    security_file = temp_config_dir / "security.json"
    security_file.write_text(
        json.dumps(
            {
                "auth_method": "forms",
                "username": "testuser",
                "password_hash": "$2b$12$testhash",
            }
        )
    )

    config = SecurityConfig.load()

    assert config is not None
    assert config.auth_method == "forms"
    assert config.username == "testuser"
    assert config.password_hash == "$2b$12$testhash"


def test_security_config_save(temp_config_dir: Path):
    """Test saving security config."""
    config = SecurityConfig(
        auth_method="forms",
        username="testuser",
        password_hash="$2b$12$testhash",
    )

    config.save()

    # Verify file was created
    security_file = temp_config_dir / "security.json"
    assert security_file.exists()

    # Verify contents
    with security_file.open() as f:
        data = json.load(f)

    assert data["auth_method"] == "forms"
    assert data["username"] == "testuser"
    assert data["password_hash"] == "$2b$12$testhash"


def test_security_config_is_configured_none():
    """Test is_configured() with 'none' auth method."""
    config = SecurityConfig(auth_method="none")

    assert config.is_configured() is True


def test_security_config_is_configured_forms_complete():
    """Test is_configured() with complete 'forms' config."""
    config = SecurityConfig(
        auth_method="forms",
        username="testuser",
        password_hash="$2b$12$testhash",
    )

    assert config.is_configured() is True


def test_security_config_is_configured_forms_incomplete():
    """Test is_configured() with incomplete 'forms' config."""
    # Missing username
    config1 = SecurityConfig(
        auth_method="forms",
        password_hash="$2b$12$testhash",
    )
    assert config1.is_configured() is False

    # Missing password_hash
    config2 = SecurityConfig(
        auth_method="forms",
        username="testuser",
    )
    assert config2.is_configured() is False

    # Missing both
    config3 = SecurityConfig(auth_method="forms")
    assert config3.is_configured() is False
