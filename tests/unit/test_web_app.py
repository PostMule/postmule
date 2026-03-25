"""Unit tests for postmule.web.app."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import postmule.web.app as web_app
from postmule.web.app import app, create_app
from postmule.data import bills as bills_data
from postmule.data import entities as entity_data
from postmule.data import forward_to_me as ftm_data
from postmule.data import notices as notices_data
from postmule.data import run_log as run_log_data


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path


@pytest.fixture
def client(data_dir):
    test_app = create_app(data_dir=data_dir)
    test_app.config["TESTING"] = True
    with test_app.test_client() as c:
        yield c


class TestHomeRoute:
    def test_home_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_home_shows_dashboard(self, client):
        assert b"Dashboard" in client.get("/").data or b"PostMule" in client.get("/").data

    def test_home_shows_pending_counts(self, client, data_dir):
        ftm_data.add_item(data_dir, {"sender": "Visa", "forwarding_status": "pending"})
        response = client.get("/")
        assert response.status_code == 200

    def test_home_with_last_run(self, client, data_dir):
        run_log_data.append_run(data_dir, {
            "run_id": "test",
            "start_time": "2025-01-01T02:00:00",
            "end_time": "2025-01-01T02:05:00",
            "status": "success",
        })
        response = client.get("/")
        assert response.status_code == 200


class TestMailRoute:
    def test_mail_returns_200(self, client):
        response = client.get("/mail")
        assert response.status_code == 200

    def test_mail_shows_bills(self, client, data_dir):
        from datetime import date
        today = date.today().isoformat()
        bills_data.add_bill(data_dir, {
            "date_received": today,
            "sender": "ATT",
            "amount_due": 94.0,
            "due_date": today,
            "status": "pending",
        })
        response = client.get("/mail")
        assert response.status_code == 200
        assert b"ATT" in response.data

    def test_mail_with_year_param(self, client):
        response = client.get("/mail?year=2024")
        assert response.status_code == 200


class TestBillsRoute:
    def test_bills_redirects_to_mail(self, client):
        response = client.get("/bills")
        assert response.status_code == 302
        assert "/mail" in response.headers["Location"]

    def test_bills_shows_bill_data_via_redirect(self, client, data_dir):
        from datetime import date
        today = date.today().isoformat()
        bills_data.add_bill(data_dir, {
            "date_received": today,
            "sender": "Comcast",
            "amount_due": 120.0,
            "due_date": today,
            "status": "pending",
        })
        response = client.get("/bills", follow_redirects=True)
        assert response.status_code == 200
        assert b"Comcast" in response.data


class TestForwardRoute:
    def test_forward_redirects_to_mail(self, client):
        response = client.get("/forward")
        assert response.status_code == 302
        assert "/mail" in response.headers["Location"]

    def test_forward_shows_pending_items_via_redirect(self, client, data_dir):
        ftm_data.add_item(data_dir, {"sender": "Chase", "forwarding_status": "pending", "summary": "New card"})
        response = client.get("/forward", follow_redirects=True)
        assert response.status_code == 200
        assert b"Chase" in response.data


class TestPendingRoute:
    def test_pending_redirects_to_mail(self, client):
        response = client.get("/pending")
        assert response.status_code == 302
        assert "/mail" in response.headers["Location"]

    def test_pending_redirects_to_unassigned_tab(self, client):
        response = client.get("/pending")
        assert b"unassigned" in response.headers["Location"].encode()


class TestEntitiesRoute:
    def test_entities_returns_200(self, client):
        response = client.get("/entities")
        assert response.status_code == 200


class TestLogsRoute:
    def test_logs_returns_200(self, client):
        response = client.get("/logs")
        assert response.status_code == 200

    def test_logs_shows_no_log_message_when_missing(self, client):
        response = client.get("/logs")
        assert b"No log file found" in response.data or response.status_code == 200


class TestProvidersRoute:
    def test_providers_returns_200(self, client):
        response = client.get("/providers")
        assert response.status_code == 200

    def test_providers_shows_page(self, client):
        response = client.get("/providers")
        assert b"Providers" in response.data

    def test_connections_redirects_to_providers(self, client):
        response = client.get("/connections")
        assert response.status_code == 301
        assert "/providers" in response.headers["Location"]

    def test_setup_redirects_to_providers(self, client):
        response = client.get("/setup")
        assert response.status_code == 302
        assert "/providers" in response.headers["Location"]


class TestApiApprove:
    def test_approve_missing_match_id(self, client):
        response = client.post("/api/approve", data={})
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data

    def test_approve_valid_match(self, client, data_dir):
        # Create an entity and pending match
        entities = [{"id": "e1", "canonical_name": "AT&T", "aliases": ["ATT"], "type": "Corporation"}]
        entity_data.save_entities(data_dir, entities)
        matches = [{
            "id": "match-1",
            "proposed_name": "AT T",
            "match_entity_id": "e1",
            "similarity": 0.9,
            "status": "pending",
            "auto_approve_after": "2025-04-01",
        }]
        entity_data.save_pending_matches(data_dir, matches)

        response = client.post("/api/approve", data={"match_id": "match-1"})
        assert response.status_code == 200

    def test_approve_nonexistent_match(self, client, data_dir):
        entity_data.save_pending_matches(data_dir, [])
        response = client.post("/api/approve", data={"match_id": "nonexistent"})
        assert response.status_code == 404


class TestApiDeny:
    def test_deny_missing_match_id(self, client):
        response = client.post("/api/deny", data={})
        assert response.status_code == 400

    def test_deny_valid_match(self, client, data_dir):
        matches = [{"id": "match-2", "status": "pending", "proposed_name": "Test"}]
        entity_data.save_pending_matches(data_dir, matches)
        response = client.post("/api/deny", data={"match_id": "match-2"})
        assert response.status_code == 200

    def test_deny_nonexistent_match(self, client, data_dir):
        entity_data.save_pending_matches(data_dir, [])
        response = client.post("/api/deny", data={"match_id": "no-such-id"})
        assert response.status_code == 404


class TestAuth:
    @pytest.fixture
    def auth_client(self, data_dir):
        """Client with a password configured."""
        test_app = create_app(data_dir=data_dir)
        test_app.config["TESTING"] = True
        with patch("postmule.web.app._dashboard_password", return_value="secret"):
            test_app.secret_key = b"test-key"
            with test_app.test_client() as c:
                yield c

    def test_login_page_accessible(self, auth_client):
        with patch("postmule.web.app._dashboard_password", return_value="secret"):
            response = auth_client.get("/login")
        assert response.status_code == 200

    def test_correct_password_grants_access(self, auth_client):
        with patch("postmule.web.app._dashboard_password", return_value="secret"):
            response = auth_client.post("/login", data={"password": "secret"})
        assert response.status_code == 302  # redirect to home

    def test_wrong_password_denied(self, auth_client):
        with patch("postmule.web.app._dashboard_password", return_value="secret"):
            response = auth_client.post("/login", data={"password": "wrong"})
        assert response.status_code == 200
        assert b"Incorrect password" in response.data

    def test_lockout_after_max_attempts(self, auth_client):
        web_app._failed_attempts.clear()
        with patch("postmule.web.app._dashboard_password", return_value="secret"):
            for _ in range(web_app._MAX_LOGIN_ATTEMPTS):
                auth_client.post("/login", data={"password": "wrong"})
            response = auth_client.post("/login", data={"password": "wrong"})
        assert b"Too many failed attempts" in response.data
        web_app._failed_attempts.clear()

    def test_lockout_clears_on_success(self, auth_client):
        web_app._failed_attempts.clear()
        ip = "127.0.0.1"
        # Simulate some failed attempts (below lockout)
        web_app._failed_attempts[ip] = [time.time()] * 2
        with patch("postmule.web.app._dashboard_password", return_value="secret"):
            auth_client.post("/login", data={"password": "secret"})
        assert ip not in web_app._failed_attempts
        web_app._failed_attempts.clear()

    def test_session_timeout_redirects(self, auth_client):
        with patch("postmule.web.app._dashboard_password", return_value="secret"):
            # Log in
            auth_client.post("/login", data={"password": "secret"})
            # Manually expire the session auth_time
            with auth_client.session_transaction() as sess:
                sess["auth_time"] = time.time() - web_app._SESSION_TIMEOUT - 1
            response = auth_client.get("/")
        assert response.status_code == 302

    def test_no_auth_when_no_password(self, client):
        """When no password is configured, all pages accessible without login."""
        response = client.get("/")
        assert response.status_code == 200

    def test_derive_secret_key_stable_with_password(self):
        with patch("postmule.web.app._dashboard_password", return_value="mypassword"):
            key1 = web_app._derive_secret_key()
            key2 = web_app._derive_secret_key()
        assert key1 == key2
        assert len(key1) == 32  # SHA-256 output

    def test_derive_secret_key_changes_with_password(self):
        with patch("postmule.web.app._dashboard_password", return_value="pass1"):
            key1 = web_app._derive_secret_key()
        with patch("postmule.web.app._dashboard_password", return_value="pass2"):
            key2 = web_app._derive_secret_key()
        assert key1 != key2


class TestApiRun:
    def setup_method(self):
        web_app._pipeline_running = False

    def test_run_triggers_process(self, client):
        with patch("postmule.web.app._config", new=MagicMock()):
            with patch("postmule.web.app._dashboard_password", return_value=None):
                with patch("threading.Thread") as mock_thread:
                    mock_thread.return_value.start = MagicMock()
                    response = client.post("/api/run", data={})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["ok"] is True

    def test_run_dry_run_flag(self, client):
        with patch("postmule.web.app._config", new=MagicMock()):
            with patch("postmule.web.app._dashboard_password", return_value=None):
                with patch("threading.Thread") as mock_thread:
                    mock_thread.return_value.start = MagicMock()
                    response = client.post("/api/run", data={"dry_run": "true"})
        assert response.status_code == 200

    def test_run_no_config_returns_500(self, client):
        # _config is None when no config file was provided to create_app
        with patch("postmule.web.app._dashboard_password", return_value=None):
            response = client.post("/api/run", data={})
        assert response.status_code == 500
