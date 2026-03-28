"""
Config loader — reads config.yaml, validates required fields, provides typed access.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")


class ConfigError(Exception):
    """Raised when config.yaml is missing, unreadable, or has invalid values."""


class Config:
    """Wrapper around the parsed config dict with helper accessors."""

    def __init__(self, data: dict[str, Any], path: Path) -> None:
        self._data = data
        self.path = path

    def get(self, *keys: str, default: Any = None) -> Any:
        """Drill into nested keys: config.get('llm', 'providers') -> list."""
        node = self._data
        for key in keys:
            if not isinstance(node, dict):
                return default
            node = node.get(key, default)
            if node is default:
                return default
        return node

    def require(self, *keys: str) -> Any:
        """Like get() but raises ConfigError if the value is missing or empty."""
        value = self.get(*keys)
        if value is None or value == "":
            path_str = " -> ".join(keys)
            raise ConfigError(
                f"Required config value missing: {path_str}\n"
                f"Edit {self.path} and set a value for '{keys[-1]}'."
            )
        return value

    @property
    def dry_run(self) -> bool:
        return bool(self.get("app", "dry_run", default=False))

    @property
    def alert_email(self) -> str:
        return self.require("notifications", "alert_email")

    @property
    def alert_email_secondary(self) -> str:
        return self.get("notifications", "alert_email_secondary", default="") or ""

    @property
    def alert_recipients(self) -> list[str]:
        """All alert recipient addresses (primary + optional secondary)."""
        recipients = [self.alert_email]
        secondary = self.alert_email_secondary
        if secondary and secondary not in recipients:
            recipients.append(secondary)
        return recipients

    @property
    def confidence_threshold(self) -> float:
        return float(self.get("llm", "classification_confidence_threshold", default=0.80))

    @property
    def max_files_per_run(self) -> int:
        return int(self.get("data_protection", "max_files_moved_per_run", default=50))

    @property
    def dashboard_port(self) -> int:
        return int(self.get("deployment", "dashboard_port", default=5000))

    def email_providers_by_role(self, role: str) -> list[dict]:
        """Return enabled email provider entries with the given role."""
        return [
            p for p in (self.get("email", "providers") or [])
            if p.get("role") == role and p.get("enabled", True)
        ]

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    def __repr__(self) -> str:
        return f"Config(path={self.path})"


def load_config(path: Path | str | None = None) -> Config:
    """
    Load and return a Config from path (default: config.yaml in cwd).

    Raises ConfigError if the file is missing, invalid YAML, or fails validation.
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH

    if not config_path.exists():
        raise ConfigError(
            f"Config file not found: {config_path}\n"
            "Copy config.example.yaml to config.yaml and fill in your settings."
        )

    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConfigError(
            f"config.yaml has a syntax error:\n{exc}\n"
            "Check for missing quotes, bad indentation, or invalid characters."
        ) from exc

    if not isinstance(data, dict):
        raise ConfigError(
            "config.yaml is empty or not a valid key-value file.\n"
            "It should start with top-level keys like 'app:', 'schedule:', etc."
        )

    cfg = Config(data, config_path)
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    """Fail fast on the most common config mistakes."""
    errors: list[str] = []

    alert_email = cfg.get("notifications", "alert_email")
    if not alert_email:
        errors.append(
            "notifications -> alert_email is not set.\n"
            "  Set it to the email address where you want to receive alerts."
        )

    llm_providers = cfg.get("llm", "providers") or []
    if not any(p.get("enabled") for p in llm_providers):
        errors.append(
            "llm -> providers: no provider is enabled.\n"
            "  Set at least one provider's 'enabled' to true (e.g. gemini)."
        )

    email_providers = cfg.get("email", "providers") or []
    if not any(p.get("enabled") for p in email_providers):
        errors.append(
            "email -> providers: no provider is enabled.\n"
            "  Set at least one provider's 'enabled' to true (e.g. gmail)."
        )

    storage_providers = cfg.get("storage", "providers") or []
    if not any(p.get("enabled") for p in storage_providers):
        errors.append(
            "storage -> providers: no provider is enabled.\n"
            "  Set at least one provider's 'enabled' to true (e.g. google_drive)."
        )

    if errors:
        bullet_list = "\n\n".join(f"  * {e}" for e in errors)
        raise ConfigError(
            f"config.yaml has {len(errors)} problem(s) to fix:\n\n"
            f"{bullet_list}\n\n"
            "Edit config.yaml to resolve these before running PostMule."
        )
