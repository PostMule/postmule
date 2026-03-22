"""
Shared pytest fixtures for PostMule tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def minimal_config_data() -> dict:
    """A valid minimal config dict that passes _validate()."""
    return {
        "app": {"dry_run": False},
        "notifications": {"alert_email": "test@example.com"},
        "llm": {
            "providers": [{"type": "gemini", "enabled": True}],
            "classification_confidence_threshold": 0.80,
        },
        "email": {
            "providers": [{"type": "gmail", "enabled": True, "address": "test@gmail.com"}]
        },
        "storage": {
            "providers": [{"type": "google_drive", "enabled": True, "root_folder": "PostMule"}]
        },
        "data_protection": {"max_files_moved_per_run": 50},
        "deployment": {"dashboard_port": 5000},
    }


@pytest.fixture
def config_file(tmp_path: Path, minimal_config_data: dict) -> Path:
    """Write a valid minimal config.yaml to a temp directory and return the path."""
    path = tmp_path / "config.yaml"
    with path.open("w") as f:
        yaml.dump(minimal_config_data, f)
    return path


@pytest.fixture
def credentials_yaml(tmp_path: Path) -> Path:
    """Write a minimal credentials.yaml to a temp directory and return the path."""
    data = {
        "google": {"client_id": "test-id", "client_secret": "test-secret", "refresh_token": "test-token"},
        "gemini": {"api_key": "test-gemini-key"},
    }
    path = tmp_path / "credentials.yaml"
    with path.open("w") as f:
        yaml.dump(data, f)
    return path
