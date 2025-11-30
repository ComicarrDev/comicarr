"""Tests for bootstrap logic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from comicarr.core.bootstrap import bootstrap_security
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


def test_bootstrap_security_existing_config(temp_config_dir: Path):
    """Test bootstrap when security config already exists."""
    # Create existing config
    security_file = temp_config_dir / "security.json"
    security_file.write_text(
        json.dumps(
            {
                "auth_method": "forms",
                "username": "existing_user",
                "password_hash": "$2b$12$existing",
            }
        )
    )

    # Bootstrap should not create a new config
    bootstrap_security()

    # Verify config still exists and wasn't modified
    config = SecurityConfig.load()
    assert config is not None
    assert config.username == "existing_user"


def test_bootstrap_security_from_env_vars(temp_config_dir: Path, monkeypatch):
    """Test bootstrap creating config from environment variables."""
    # Set environment variables
    monkeypatch.setenv("COMICARR_USERNAME", "env_user")
    monkeypatch.setenv("COMICARR_PASSWORD", "env_password")

    # Bootstrap should create config from env vars
    bootstrap_security()

    # Verify config was created
    config = SecurityConfig.load()
    assert config is not None
    assert config.auth_method == "forms"
    assert config.username == "env_user"
    assert config.password_hash is not None
    assert config.password_hash.startswith("$2b$")  # Valid bcrypt hash


def test_bootstrap_security_no_env_vars(temp_config_dir: Path, monkeypatch):
    """Test bootstrap when no env vars are set."""
    # Ensure env vars are not set
    monkeypatch.delenv("COMICARR_USERNAME", raising=False)
    monkeypatch.delenv("COMICARR_PASSWORD", raising=False)

    # Bootstrap should not create config
    bootstrap_security()

    # Verify no config was created
    config = SecurityConfig.load()
    assert config is None

    # Verify file doesn't exist
    security_file = temp_config_dir / "security.json"
    assert not security_file.exists()


def test_bootstrap_security_partial_env_vars(temp_config_dir: Path, monkeypatch):
    """Test bootstrap when only one env var is set."""
    # Set only username
    monkeypatch.setenv("COMICARR_USERNAME", "env_user")
    monkeypatch.delenv("COMICARR_PASSWORD", raising=False)

    # Bootstrap should not create config (both required)
    bootstrap_security()

    # Verify no config was created
    config = SecurityConfig.load()
    assert config is None
