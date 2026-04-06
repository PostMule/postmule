"""Unit tests for setup wizard API endpoints (/setup/api/test-gmail, /setup/api/test-gemini)."""

from __future__ import annotations

import imaplib
import json
from unittest.mock import MagicMock, patch

import pytest

from postmule.web.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(data_dir=tmp_path)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _post(client, url, payload):
    return client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
    )


# ---------------------------------------------------------------------------
# POST /setup/api/test-gmail
# ---------------------------------------------------------------------------

class TestTestGmail:
    def test_missing_fields_returns_error(self, client):
        r = _post(client, "/setup/api/test-gmail", {})
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is False
        assert data["error"]

    def test_missing_password_returns_error(self, client):
        r = _post(client, "/setup/api/test-gmail", {"gmail_address": "u@gmail.com"})
        data = r.get_json()
        assert data["ok"] is False

    def test_missing_address_returns_error(self, client):
        r = _post(client, "/setup/api/test-gmail", {"app_password": "xxxx"})
        data = r.get_json()
        assert data["ok"] is False

    def test_successful_login_returns_ok(self, client):
        mock_conn = MagicMock()
        with patch("imaplib.IMAP4_SSL", return_value=mock_conn) as mock_imap:
            r = _post(client, "/setup/api/test-gmail", {
                "gmail_address": "user@gmail.com",
                "app_password": "abcd efgh ijkl mnop",
            })
        data = r.get_json()
        assert data["ok"] is True
        assert data["error"] is None
        mock_conn.login.assert_called_once_with("user@gmail.com", "abcd efgh ijkl mnop")
        mock_conn.logout.assert_called_once()

    def test_imap_auth_failure_returns_plain_english(self, client):
        mock_conn = MagicMock()
        mock_conn.login.side_effect = imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] Invalid credentials")
        with patch("imaplib.IMAP4_SSL", return_value=mock_conn):
            r = _post(client, "/setup/api/test-gmail", {
                "gmail_address": "user@gmail.com",
                "app_password": "wrong",
            })
        data = r.get_json()
        assert data["ok"] is False
        assert "App Password" in data["error"] or "Login failed" in data["error"]

    def test_connection_error_returns_plain_english(self, client):
        with patch("imaplib.IMAP4_SSL", side_effect=OSError("Network unreachable")):
            r = _post(client, "/setup/api/test-gmail", {
                "gmail_address": "user@gmail.com",
                "app_password": "abcd efgh ijkl mnop",
            })
        data = r.get_json()
        assert data["ok"] is False
        assert "imap.gmail.com" in data["error"] or "internet" in data["error"].lower()

    def test_whitespace_trimmed_from_inputs(self, client):
        mock_conn = MagicMock()
        with patch("imaplib.IMAP4_SSL", return_value=mock_conn):
            r = _post(client, "/setup/api/test-gmail", {
                "gmail_address": "  user@gmail.com  ",
                "app_password": "  abcd efgh  ",
            })
        mock_conn.login.assert_called_once_with("user@gmail.com", "abcd efgh")


# ---------------------------------------------------------------------------
# POST /setup/api/test-gemini
# ---------------------------------------------------------------------------

class TestTestGemini:
    def test_missing_key_returns_error(self, client):
        r = _post(client, "/setup/api/test-gemini", {})
        data = r.get_json()
        assert data["ok"] is False
        assert data["error"]

    def test_empty_key_returns_error(self, client):
        r = _post(client, "/setup/api/test-gemini", {"gemini_key": "   "})
        data = r.get_json()
        assert data["ok"] is False

    def test_successful_key_returns_ok(self, client):
        with patch("postmule.web.routes.setup._probe_gemini_key", return_value=(True, None)) as mock_probe:
            r = _post(client, "/setup/api/test-gemini", {"gemini_key": "AIzaSyFake123"})
        data = r.get_json()
        assert data["ok"] is True
        assert data["error"] is None
        mock_probe.assert_called_once_with("AIzaSyFake123")

    def test_invalid_key_returns_plain_english(self, client):
        err = "Invalid API key — double-check what you copied from Google AI Studio."
        with patch("postmule.web.routes.setup._probe_gemini_key", return_value=(False, err)):
            r = _post(client, "/setup/api/test-gemini", {"gemini_key": "bad-key"})
        data = r.get_json()
        assert data["ok"] is False
        assert "key" in data["error"].lower() or "invalid" in data["error"].lower()

    def test_network_error_returns_message(self, client):
        err = "Gemini connection failed: Connection refused"
        with patch("postmule.web.routes.setup._probe_gemini_key", return_value=(False, err)):
            r = _post(client, "/setup/api/test-gemini", {"gemini_key": "AIzaSyFake123"})
        data = r.get_json()
        assert data["ok"] is False
        assert data["error"]

    def test_key_whitespace_trimmed(self, client):
        with patch("postmule.web.routes.setup._probe_gemini_key", return_value=(True, None)) as mock_probe:
            r = _post(client, "/setup/api/test-gemini", {"gemini_key": "  AIzaSyFake123  "})
        mock_probe.assert_called_once_with("AIzaSyFake123")
