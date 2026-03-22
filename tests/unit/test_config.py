"""Unit tests for postmule.core.config."""

from pathlib import Path

import pytest
import yaml

from postmule.core.config import Config, ConfigError, load_config


class TestConfigGet:
    def test_get_nested_value(self, minimal_config_data):
        cfg = Config(minimal_config_data, Path("config.yaml"))
        assert cfg.get("notifications", "alert_email") == "test@example.com"

    def test_get_missing_returns_default(self, minimal_config_data):
        cfg = Config(minimal_config_data, Path("config.yaml"))
        assert cfg.get("nonexistent", "key", default="fallback") == "fallback"

    def test_get_default_none(self, minimal_config_data):
        cfg = Config(minimal_config_data, Path("config.yaml"))
        assert cfg.get("nonexistent") is None

    def test_require_raises_on_missing(self, minimal_config_data):
        cfg = Config(minimal_config_data, Path("config.yaml"))
        with pytest.raises(ConfigError, match="Required config value missing"):
            cfg.require("nonexistent", "key")

    def test_require_raises_on_empty_string(self, minimal_config_data):
        minimal_config_data["notifications"]["alert_email"] = ""
        cfg = Config(minimal_config_data, Path("config.yaml"))
        with pytest.raises(ConfigError):
            cfg.require("notifications", "alert_email")


class TestConfigProperties:
    def test_dry_run_false_by_default(self, minimal_config_data):
        cfg = Config(minimal_config_data, Path("config.yaml"))
        assert cfg.dry_run is False

    def test_dry_run_true(self, minimal_config_data):
        minimal_config_data["app"]["dry_run"] = True
        cfg = Config(minimal_config_data, Path("config.yaml"))
        assert cfg.dry_run is True

    def test_confidence_threshold_default(self, minimal_config_data):
        cfg = Config(minimal_config_data, Path("config.yaml"))
        assert cfg.confidence_threshold == 0.80

    def test_max_files_per_run(self, minimal_config_data):
        cfg = Config(minimal_config_data, Path("config.yaml"))
        assert cfg.max_files_per_run == 50


class TestLoadConfig:
    def test_loads_valid_config(self, config_file):
        cfg = load_config(config_file)
        assert cfg.get("notifications", "alert_email") == "test@example.com"

    def test_raises_if_file_missing(self, tmp_path):
        with pytest.raises(ConfigError, match="Config file not found"):
            load_config(tmp_path / "nonexistent.yaml")

    def test_raises_on_invalid_yaml(self, tmp_path):
        bad = tmp_path / "config.yaml"
        bad.write_text("key: [unclosed bracket")
        with pytest.raises(ConfigError, match="syntax error"):
            load_config(bad)

    def test_raises_on_empty_file(self, tmp_path):
        empty = tmp_path / "config.yaml"
        empty.write_text("")
        with pytest.raises(ConfigError, match="empty"):
            load_config(empty)


class TestValidate:
    def test_missing_alert_email_raises(self, tmp_path, minimal_config_data):
        minimal_config_data["notifications"]["alert_email"] = ""
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(minimal_config_data))
        with pytest.raises(ConfigError, match="alert_email"):
            load_config(path)

    def test_no_llm_provider_raises(self, tmp_path, minimal_config_data):
        minimal_config_data["llm"]["providers"] = [{"type": "gemini", "enabled": False}]
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(minimal_config_data))
        with pytest.raises(ConfigError, match="llm"):
            load_config(path)

    def test_no_email_provider_raises(self, tmp_path, minimal_config_data):
        minimal_config_data["email"]["providers"] = [{"type": "gmail", "enabled": False}]
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(minimal_config_data))
        with pytest.raises(ConfigError, match="email"):
            load_config(path)

    def test_no_storage_provider_raises(self, tmp_path, minimal_config_data):
        minimal_config_data["storage"]["providers"] = [{"type": "google_drive", "enabled": False}]
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(minimal_config_data))
        with pytest.raises(ConfigError, match="storage"):
            load_config(path)
