"""Unit tests for email account management routes in connections blueprint (#68)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

import postmule.web.app as web_app
from postmule.web.app import create_app


@pytest.fixture
def config_path(tmp_path):
    data = {
        "app": {"dry_run": False},
        "notifications": {"alert_email": "test@example.com"},
        "llm": {"providers": [{"service": "gemini", "enabled": True}]},
        "email": {
            "providers": [
                {
                    "id": "aaaa-1111",
                    "service": "gmail",
                    "role": "mailbox_notifications",
                    "enabled": True,
                    "address": "notify@gmail.com",
                }
            ]
        },
        "storage": {"providers": [{"service": "google_drive", "enabled": True, "root_folder": "PM"}]},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(data))
    return path


@pytest.fixture
def enc_path(tmp_path):
    return tmp_path / "credentials.enc"


@pytest.fixture
def client(tmp_path, config_path, enc_path):
    # Save and restore module-level globals to avoid cross-test contamination.
    saved = (web_app._config, web_app._config_raw, web_app._config_path, web_app._enc_path)
    test_app = create_app(config_path=config_path, data_dir=tmp_path, enc_path=enc_path)
    test_app.config["TESTING"] = True
    try:
        with test_app.test_client() as c:
            yield c
    finally:
        web_app._config, web_app._config_raw, web_app._config_path, web_app._enc_path = saved


def _read_providers(config_path):
    return yaml.safe_load(config_path.read_text()).get("email", {}).get("providers", [])


class TestAddEmailAccount:
    def test_add_account_appends_to_config(self, client, config_path):
        resp = client.post("/api/email/accounts", data={
            "service": "imap",
            "role": "bill_intake",
            "address": "bills@example.com",
        })
        assert resp.status_code in (200, 302)
        providers = _read_providers(config_path)
        assert len(providers) == 2
        new = providers[1]
        assert new["service"] == "imap"
        assert new["role"] == "bill_intake"
        assert new["address"] == "bills@example.com"

    def test_add_account_generates_uuid(self, client, config_path):
        client.post("/api/email/accounts", data={"service": "gmail", "role": "mailbox_notifications"})
        providers = _read_providers(config_path)
        assert len(providers[1]["id"]) == 36  # UUID4 string length

    def test_add_account_enabled_true_by_default(self, client, config_path):
        client.post("/api/email/accounts", data={"service": "imap", "role": "bill_intake"})
        providers = _read_providers(config_path)
        assert providers[1]["enabled"] is True

    def test_add_account_rejects_invalid_service(self, client, config_path):
        resp = client.post("/api/email/accounts", data={
            "service": "invalid_service",
            "role": "bill_intake",
        })
        assert resp.status_code in (200, 302)
        providers = _read_providers(config_path)
        assert len(providers) == 1  # unchanged

    def test_add_account_rejects_invalid_role(self, client, config_path):
        resp = client.post("/api/email/accounts", data={
            "service": "imap",
            "role": "not_a_real_role",
        })
        assert resp.status_code in (200, 302)
        providers = _read_providers(config_path)
        assert len(providers) == 1  # unchanged


class TestRemoveEmailAccount:
    def test_remove_existing_account(self, client, config_path):
        resp = client.post("/api/email/accounts/aaaa-1111/remove")
        assert resp.status_code in (200, 302)
        providers = _read_providers(config_path)
        assert len(providers) == 0

    def test_remove_nonexistent_account_redirects_with_error(self, client, config_path):
        resp = client.post("/api/email/accounts/no-such-id/remove")
        assert resp.status_code in (200, 302)
        # Config unchanged
        providers = _read_providers(config_path)
        assert len(providers) == 1


class TestEnableDisableEmailAccount:
    def test_disable_account(self, client, config_path):
        client.post("/api/email/accounts/aaaa-1111/disable")
        providers = _read_providers(config_path)
        assert providers[0]["enabled"] is False

    def test_enable_account(self, client, config_path):
        # Disable first
        client.post("/api/email/accounts/aaaa-1111/disable")
        # Then enable
        client.post("/api/email/accounts/aaaa-1111/enable")
        providers = _read_providers(config_path)
        assert providers[0]["enabled"] is True

    def test_enable_nonexistent_redirects_with_error(self, client, config_path):
        resp = client.post("/api/email/accounts/no-such-id/enable")
        assert resp.status_code in (200, 302)
        # Config unchanged
        providers = _read_providers(config_path)
        assert providers[0]["enabled"] is True


class TestSaveServiceConfigWithAccountId:
    def test_saves_imap_host_to_correct_account(self, client, config_path):
        resp = client.post(
            "/api/providers/email/imap/config",
            data={"account_id": "aaaa-1111", "host": "imap.example.com", "port": "993"},
        )
        assert resp.status_code in (200, 302)
        providers = _read_providers(config_path)
        assert providers[0]["host"] == "imap.example.com"
        assert providers[0]["port"] == "993"

    def test_returns_error_for_missing_account(self, client, config_path):
        resp = client.post(
            "/api/providers/email/imap/config",
            data={"account_id": "no-such-id", "host": "imap.example.com"},
        )
        assert resp.status_code in (200, 302)
        # Original account unchanged
        providers = _read_providers(config_path)
        assert "host" not in providers[0]
