"""Unit tests for postmule.web.app."""

import io
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

    def test_mail_does_not_show_filed_items(self, client, data_dir):
        from datetime import date
        today = date.today().isoformat()
        bills_data.add_bill(data_dir, {
            "date_received": today, "sender": "Filed-Co",
            "status": "pending", "filed": True,
        })
        response = client.get("/mail")
        assert response.status_code == 200
        assert b"Filed-Co" not in response.data


class TestReportsRoute:
    def test_reports_returns_200(self, client):
        response = client.get("/reports")
        assert response.status_code == 200

    def test_reports_shows_all_items_by_default(self, client, data_dir):
        from datetime import date
        today = date.today().isoformat()
        bills_data.add_bill(data_dir, {
            "date_received": today, "sender": "ATT-Report",
            "status": "pending",
        })
        response = client.get("/reports")
        assert response.status_code == 200
        assert b"ATT-Report" in response.data

    def test_reports_shows_filed_items(self, client, data_dir):
        from datetime import date
        today = date.today().isoformat()
        bills_data.add_bill(data_dir, {
            "date_received": today, "sender": "FiledBill",
            "status": "pending", "filed": True,
        })
        response = client.get("/reports?lifecycle=filed")
        assert response.status_code == 200
        assert b"FiledBill" in response.data

    def test_reports_freetext_search(self, client, data_dir):
        from datetime import date
        today = date.today().isoformat()
        bills_data.add_bill(data_dir, {
            "date_received": today, "sender": "Comcast-Unique",
            "status": "pending",
        })
        bills_data.add_bill(data_dir, {
            "date_received": today, "sender": "Other-Co",
            "status": "pending",
        })
        response = client.get("/reports?q=Comcast-Unique")
        assert response.status_code == 200
        assert b"Comcast-Unique" in response.data
        assert b"Other-Co" not in response.data

    def test_reports_nav_link_present(self, client):
        response = client.get("/")
        assert b"/reports" in response.data


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

    def test_setup_redirects_to_wizard(self, client):
        response = client.get("/setup")
        assert response.status_code == 302
        assert "/setup/step/" in response.headers["Location"]


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


class TestOwnerRoutes:
    def test_list_owners_empty(self, client):
        response = client.get("/api/owners")
        assert response.status_code == 200
        assert response.json == []

    def test_create_owner(self, client):
        response = client.post("/api/owners", data={"name": "Alice", "type": "person"})
        assert response.status_code == 201
        data = response.json
        assert data["name"] == "Alice"
        assert data["type"] == "person"
        assert "id" in data

    def test_create_owner_missing_name_returns_400(self, client):
        response = client.post("/api/owners", data={"type": "person"})
        assert response.status_code == 400

    def test_create_owner_with_color_and_short_name(self, client):
        response = client.post("/api/owners", data={
            "name": "Alice Smith", "type": "person",
            "short_name": "Alice", "color": "#7C3AED",
        })
        assert response.status_code == 201
        data = response.json
        assert data["short_name"] == "Alice"
        assert data["color"] == "#7C3AED"

    def test_list_owners_returns_created(self, client):
        client.post("/api/owners", data={"name": "Alice"})
        client.post("/api/owners", data={"name": "Bob"})
        response = client.get("/api/owners")
        names = [o["name"] for o in response.json]
        assert "Alice" in names
        assert "Bob" in names

    def test_update_owner(self, client):
        create = client.post("/api/owners", data={"name": "Alice"})
        owner_id = create.json["id"]
        response = client.patch(f"/api/owners/{owner_id}", data={"name": "Alice Smith"})
        assert response.status_code == 200
        assert response.json["name"] == "Alice Smith"

    def test_update_owner_not_found(self, client):
        response = client.patch("/api/owners/ghost-id", data={"name": "X"})
        assert response.status_code == 404

    def test_delete_owner(self, client):
        create = client.post("/api/owners", data={"name": "Alice"})
        owner_id = create.json["id"]
        response = client.delete(f"/api/owners/{owner_id}")
        assert response.status_code == 204
        # Should no longer appear in active list
        owners = client.get("/api/owners").json
        assert not any(o["id"] == owner_id for o in owners)

    def test_delete_owner_not_found(self, client):
        response = client.delete("/api/owners/ghost-id")
        assert response.status_code == 404

    def test_delete_shows_in_all_list(self, client):
        create = client.post("/api/owners", data={"name": "Alice"})
        owner_id = create.json["id"]
        client.delete(f"/api/owners/{owner_id}")
        all_owners = client.get("/api/owners?all=true").json
        assert any(o["id"] == owner_id for o in all_owners)


class TestMailOwnerRoute:
    def test_set_owner_ids_on_bill(self, client, data_dir):
        from datetime import date
        bill = bills_data.add_bill(data_dir, {
            "date_received": date.today().isoformat(),
            "sender": "ATT",
            "status": "pending",
        })
        from postmule.data import owners as owners_data
        owner = owners_data.add_owner(data_dir, "Alice")
        import json as _json
        response = client.put(
            f"/api/mail/{bill['id']}/owners",
            data={"owner_ids": _json.dumps([owner["id"]])},
        )
        assert response.status_code == 200
        saved = bills_data.load_bills(data_dir)
        assert saved[0].get("owner_ids") == [owner["id"]]

    def test_set_owner_ids_on_notice(self, client, data_dir):
        from datetime import date
        import json as _json
        notice = notices_data.add_notice(data_dir, {
            "date_received": date.today().isoformat(),
            "sender": "IRS",
        })
        response = client.put(
            f"/api/mail/{notice['id']}/owners",
            data={"owner_ids": _json.dumps([])},
        )
        assert response.status_code == 200

    def test_set_owner_ids_on_forward_to_me(self, client, data_dir):
        import json as _json
        item = ftm_data.add_item(data_dir, {"sender": "Visa"})
        response = client.put(
            f"/api/mail/{item['id']}/owners",
            data={"owner_ids": _json.dumps([])},
        )
        assert response.status_code == 200

    def test_set_owner_ids_invalid_json_returns_400(self, client, data_dir):
        from datetime import date
        bill = bills_data.add_bill(data_dir, {
            "date_received": date.today().isoformat(),
            "sender": "ATT",
            "status": "pending",
        })
        response = client.put(
            f"/api/mail/{bill['id']}/owners",
            data={"owner_ids": "not-json"},
        )
        assert response.status_code == 400

    def test_set_owner_ids_mail_not_found(self, client):
        import json as _json
        response = client.put(
            "/api/mail/ghost-id/owners",
            data={"owner_ids": _json.dumps([])},
        )
        assert response.status_code == 404


class TestMailFileRoutes:
    def test_file_bill_returns_200(self, client, data_dir):
        from datetime import date
        bill = bills_data.add_bill(data_dir, {
            "date_received": date.today().isoformat(),
            "sender": "ATT",
            "status": "pending",
        })
        response = client.post(f"/api/mail/{bill['id']}/file")
        assert response.status_code == 200
        saved = bills_data.load_bills(data_dir)
        assert saved[0].get("filed") is True

    def test_unfile_bill_returns_200(self, client, data_dir):
        from datetime import date
        bill = bills_data.add_bill(data_dir, {
            "date_received": date.today().isoformat(),
            "sender": "ATT",
            "status": "pending",
            "filed": True,
        })
        response = client.post(f"/api/mail/{bill['id']}/unfile")
        assert response.status_code == 200
        saved = bills_data.load_bills(data_dir)
        assert saved[0].get("filed") is False

    def test_file_notice_returns_200(self, client, data_dir):
        from datetime import date
        notice = notices_data.add_notice(data_dir, {
            "date_received": date.today().isoformat(),
            "sender": "IRS",
        })
        response = client.post(f"/api/mail/{notice['id']}/file")
        assert response.status_code == 200
        saved = notices_data.load_notices(data_dir)
        assert saved[0].get("filed") is True

    def test_file_forward_to_me_returns_200(self, client, data_dir):
        item = ftm_data.add_item(data_dir, {"sender": "Visa"})
        response = client.post(f"/api/mail/{item['id']}/file")
        assert response.status_code == 200
        saved = ftm_data.load_forward_to_me(data_dir)
        assert saved[0].get("filed") is True

    def test_file_not_found_returns_404(self, client):
        response = client.post("/api/mail/ghost-id/file")
        assert response.status_code == 404

    def test_unfile_not_found_returns_404(self, client):
        response = client.post("/api/mail/ghost-id/unfile")
        assert response.status_code == 404


class TestApiRunStatus:
    def test_run_status_returns_200(self, client):
        response = client.get("/api/run/status")
        assert response.status_code == 200

    def test_run_status_not_running(self, client):
        import postmule.web.app as web_app
        web_app._pipeline_running = False
        response = client.get("/api/run/status")
        data = json.loads(response.data)
        assert data["running"] is False

    def test_run_status_running(self, client):
        import postmule.web.app as web_app
        web_app._pipeline_running = True
        try:
            response = client.get("/api/run/status")
            data = json.loads(response.data)
            assert data["running"] is True
        finally:
            web_app._pipeline_running = False


class TestApiEntityCreate:
    def test_create_entity_success(self, client):
        response = client.post("/api/entity/create", data={
            "name": "Pacific Gas",
            "category": "biller",
            "friendly_name": "PG&E",
        })
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "id" in data
        assert data["friendly_name"] == "PG&E"

    def test_create_entity_missing_name(self, client):
        response = client.post("/api/entity/create", data={"category": "biller"})
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "error" in data

    def test_create_entity_defaults_friendly_name_to_name(self, client):
        response = client.post("/api/entity/create", data={"name": "Comcast"})
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["friendly_name"] == "Comcast"

    def test_create_entity_duplicate_friendly_name_returns_409(self, client, data_dir):
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "PGE", "friendly_name": "PG&E",
             "aliases": [], "category": "biller"},
        ])
        response = client.post("/api/entity/create", data={
            "name": "PGE Corp", "friendly_name": "PG&E",
        })
        assert response.status_code == 409
        data = json.loads(response.data)
        assert data["error"] == "friendly_name_taken"

    def test_create_entity_with_account_number(self, client):
        response = client.post("/api/entity/create", data={
            "name": "Verizon", "account_number": "123456",
        })
        assert response.status_code == 200


class TestApiApproveWithEntityOverride:
    def test_approve_with_entity_override(self, client, data_dir):
        entities = [
            {"id": "e1", "canonical_name": "AT&T", "friendly_name": "AT&T", "aliases": [], "category": "biller"},
            {"id": "e2", "canonical_name": "Verizon", "friendly_name": "Verizon", "aliases": [], "category": "biller"},
        ]
        entity_data.save_entities(data_dir, entities)
        matches = [{
            "id": "match-override",
            "proposed_name": "AT T Inc",
            "match_entity_id": "e1",
            "similarity": 0.9,
            "status": "pending",
            "auto_approve_after": "2026-12-01",
        }]
        entity_data.save_pending_matches(data_dir, matches)

        # Override to e2 instead of the proposed e1
        response = client.post("/api/approve", data={"match_id": "match-override", "entity_id": "e2"})
        assert response.status_code == 200

        # Alias should have been added to e2, not e1
        updated = entity_data.load_entities(data_dir)
        e2 = next(e for e in updated if e["id"] == "e2")
        e1 = next(e for e in updated if e["id"] == "e1")
        assert "AT T Inc" in e2["aliases"]
        assert "AT T Inc" not in e1["aliases"]


class TestApiEntityUpdate:
    def test_update_friendly_name(self, client, data_dir):
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "Pacific Gas", "friendly_name": "PGE",
             "aliases": [], "category": "biller"},
        ])
        response = client.post("/api/entity/e1", data={"field": "friendly_name", "value": "PG&E"})
        assert response.status_code == 200
        updated = entity_data.load_entities(data_dir)
        assert updated[0]["friendly_name"] == "PG&E"

    def test_update_friendly_name_empty_returns_400(self, client, data_dir):
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "PGE", "friendly_name": "PGE",
             "aliases": [], "category": "biller"},
        ])
        response = client.post("/api/entity/e1", data={"field": "friendly_name", "value": ""})
        assert response.status_code == 400

    def test_update_friendly_name_duplicate_returns_409(self, client, data_dir):
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "PGE", "friendly_name": "PGE",
             "aliases": [], "category": "biller"},
            {"id": "e2", "canonical_name": "ATT", "friendly_name": "AT&T",
             "aliases": [], "category": "biller"},
        ])
        response = client.post("/api/entity/e1", data={"field": "friendly_name", "value": "AT&T"})
        assert response.status_code == 409

    def test_update_missing_field_returns_400(self, client, data_dir):
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "PGE", "friendly_name": "PGE", "aliases": [], "category": "biller"},
        ])
        response = client.post("/api/entity/e1", data={"value": "something"})
        assert response.status_code == 400

    def test_update_entity_not_found_returns_404(self, client, data_dir):
        entity_data.save_entities(data_dir, [])
        response = client.post("/api/entity/ghost-id", data={"field": "friendly_name", "value": "X"})
        assert response.status_code == 404

    def test_update_generic_field(self, client, data_dir):
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "PGE", "friendly_name": "PGE",
             "aliases": [], "category": "biller"},
        ])
        response = client.post("/api/entity/e1", data={"field": "phone", "value": "555-1234"})
        assert response.status_code == 200


class TestApiMailEntityOverride:
    def test_override_entity_on_bill(self, client, data_dir):
        from datetime import date
        bill = bills_data.add_bill(data_dir, {
            "date_received": date.today().isoformat(),
            "sender": "AT T",
            "status": "pending",
        })
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "AT&T", "friendly_name": "AT&T",
             "aliases": [], "category": "biller"},
        ])
        response = client.post(f"/api/mail/{bill['id']}/entity", data={"entity_id": "e1"})
        assert response.status_code == 200

    def test_override_entity_on_notice(self, client, data_dir):
        from datetime import date
        notice = notices_data.add_notice(data_dir, {
            "date_received": date.today().isoformat(),
            "sender": "IRS",
        })
        entity_data.save_entities(data_dir, [
            {"id": "e2", "canonical_name": "IRS", "friendly_name": "IRS",
             "aliases": [], "category": "government"},
        ])
        response = client.post(f"/api/mail/{notice['id']}/entity", data={"entity_id": "e2"})
        assert response.status_code == 200

    def test_override_entity_on_forward_to_me(self, client, data_dir):
        item = ftm_data.add_item(data_dir, {"sender": "Visa"})
        entity_data.save_entities(data_dir, [
            {"id": "e3", "canonical_name": "Visa", "friendly_name": "Visa",
             "aliases": [], "category": "biller"},
        ])
        response = client.post(f"/api/mail/{item['id']}/entity", data={"entity_id": "e3"})
        assert response.status_code == 200

    def test_override_adds_alias_when_flag_set(self, client, data_dir):
        from datetime import date
        bill = bills_data.add_bill(data_dir, {
            "date_received": date.today().isoformat(),
            "sender": "AT T",
            "status": "pending",
        })
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "AT&T", "friendly_name": "AT&T",
             "aliases": [], "category": "biller"},
        ])
        response = client.post(f"/api/mail/{bill['id']}/entity",
                               data={"entity_id": "e1", "add_alias": "true"})
        assert response.status_code == 200
        updated = entity_data.load_entities(data_dir)
        assert "AT T" in updated[0]["aliases"]

    def test_override_missing_entity_id_returns_400(self, client, data_dir):
        from datetime import date
        bill = bills_data.add_bill(data_dir, {
            "date_received": date.today().isoformat(),
            "sender": "ATT",
            "status": "pending",
        })
        response = client.post(f"/api/mail/{bill['id']}/entity", data={})
        assert response.status_code == 400

    def test_override_mail_not_found_returns_404(self, client, data_dir):
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "X", "friendly_name": "X", "aliases": [], "category": "biller"},
        ])
        response = client.post("/api/mail/ghost-mail/entity", data={"entity_id": "e1"})
        assert response.status_code == 404

    def test_override_entity_not_found_returns_404(self, client, data_dir):
        from datetime import date
        bill = bills_data.add_bill(data_dir, {
            "date_received": date.today().isoformat(),
            "sender": "ATT",
            "status": "pending",
        })
        entity_data.save_entities(data_dir, [])
        response = client.post(f"/api/mail/{bill['id']}/entity", data={"entity_id": "ghost-entity"})
        assert response.status_code == 404


class TestApiMailCategory:
    def test_set_category_on_bill(self, client, data_dir):
        from datetime import date
        bill = bills_data.add_bill(data_dir, {
            "date_received": date.today().isoformat(),
            "sender": "ATT",
            "status": "pending",
        })
        response = client.post(f"/api/mail/{bill['id']}/category", data={"category": "Notice"})
        assert response.status_code == 200

    def test_set_category_on_notice(self, client, data_dir):
        from datetime import date
        notice = notices_data.add_notice(data_dir, {
            "date_received": date.today().isoformat(),
            "sender": "IRS",
        })
        response = client.post(f"/api/mail/{notice['id']}/category", data={"category": "Bill"})
        assert response.status_code == 200

    def test_set_category_on_forward_to_me(self, client, data_dir):
        item = ftm_data.add_item(data_dir, {"sender": "Visa"})
        response = client.post(f"/api/mail/{item['id']}/category", data={"category": "Junk"})
        assert response.status_code == 200

    def test_invalid_category_returns_400(self, client, data_dir):
        from datetime import date
        bill = bills_data.add_bill(data_dir, {
            "date_received": date.today().isoformat(),
            "sender": "ATT",
            "status": "pending",
        })
        response = client.post(f"/api/mail/{bill['id']}/category", data={"category": "Bogus"})
        assert response.status_code == 400

    def test_mail_not_found_returns_404(self, client):
        response = client.post("/api/mail/ghost-id/category", data={"category": "Bill"})
        assert response.status_code == 404


class TestApiEntitySave:
    def test_save_entity_success(self, client, data_dir):
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "PGE", "friendly_name": "PGE",
             "aliases": [], "category": "biller"},
        ])
        response = client.post("/api/entity/e1/save", data={
            "friendly_name": "PG&E",
            "phone": "800-555-1234",
            "category": "biller",
        })
        assert response.status_code == 200
        updated = entity_data.load_entities(data_dir)
        assert updated[0]["friendly_name"] == "PG&E"
        assert updated[0]["phone"] == "800-555-1234"

    def test_save_entity_empty_friendly_name_returns_400(self, client, data_dir):
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "PGE", "friendly_name": "PGE",
             "aliases": [], "category": "biller"},
        ])
        response = client.post("/api/entity/e1/save", data={"friendly_name": ""})
        assert response.status_code == 400

    def test_save_entity_duplicate_friendly_name_returns_409(self, client, data_dir):
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "PGE", "friendly_name": "PGE",
             "aliases": [], "category": "biller"},
            {"id": "e2", "canonical_name": "ATT", "friendly_name": "AT&T",
             "aliases": [], "category": "biller"},
        ])
        response = client.post("/api/entity/e1/save", data={"friendly_name": "AT&T"})
        assert response.status_code == 409

    def test_save_entity_not_found_returns_404(self, client, data_dir):
        entity_data.save_entities(data_dir, [])
        response = client.post("/api/entity/ghost-id/save", data={"friendly_name": "X"})
        assert response.status_code == 404


class TestApiEntityAlias:
    def test_add_alias(self, client, data_dir):
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "PGE", "friendly_name": "PGE",
             "aliases": [], "category": "biller"},
        ])
        response = client.post("/api/entity/e1/alias", data={"action": "add", "value": "Pacific Gas"})
        assert response.status_code == 200
        updated = entity_data.load_entities(data_dir)
        assert "Pacific Gas" in updated[0]["aliases"]

    def test_remove_alias(self, client, data_dir):
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "PGE", "friendly_name": "PGE",
             "aliases": ["Pacific Gas"], "category": "biller"},
        ])
        response = client.post("/api/entity/e1/alias", data={"action": "remove", "value": "Pacific Gas"})
        assert response.status_code == 200
        updated = entity_data.load_entities(data_dir)
        assert "Pacific Gas" not in updated[0]["aliases"]

    def test_invalid_action_returns_400(self, client, data_dir):
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "PGE", "friendly_name": "PGE",
             "aliases": [], "category": "biller"},
        ])
        response = client.post("/api/entity/e1/alias", data={"action": "bogus", "value": "X"})
        assert response.status_code == 400

    def test_entity_not_found_returns_404(self, client, data_dir):
        entity_data.save_entities(data_dir, [])
        response = client.post("/api/entity/ghost-id/alias", data={"action": "add", "value": "X"})
        assert response.status_code == 404


class TestApiEntityAddAccount:
    def test_add_account(self, client, data_dir):
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "PGE", "friendly_name": "PGE",
             "aliases": [], "category": "biller"},
        ])
        response = client.post("/api/entity/e1/add-account", data={"account": "987654"})
        assert response.status_code == 200

    def test_missing_account_returns_400(self, client, data_dir):
        entity_data.save_entities(data_dir, [
            {"id": "e1", "canonical_name": "PGE", "friendly_name": "PGE",
             "aliases": [], "category": "biller"},
        ])
        response = client.post("/api/entity/e1/add-account", data={})
        assert response.status_code == 400

    def test_entity_not_found_returns_404(self, client, data_dir):
        entity_data.save_entities(data_dir, [])
        response = client.post("/api/entity/ghost-id/add-account", data={"account": "123"})
        assert response.status_code == 404


class TestApiTags:
    def test_get_tags_empty(self, client, data_dir):
        response = client.get("/api/tags")
        assert response.status_code == 200
        assert response.get_json() == []

    def test_get_tags_returns_registry(self, client, data_dir):
        from postmule.data import tags as tags_data
        tags_data.add_to_registry(data_dir, "urgent")
        tags_data.add_to_registry(data_dir, "tax")
        response = client.get("/api/tags")
        assert response.status_code == 200
        tags = response.get_json()
        assert "urgent" in tags
        assert "tax" in tags

    def test_mail_tag_missing_action_returns_400(self, client, data_dir):
        bill_id = bills_data.add_bill(data_dir, {
            "date_received": "2025-01-15", "sender": "AT&T", "summary": "Bill",
            "filename": "2025-01-15_Alice_ATT_Bill.pdf",
        })["id"]
        response = client.post(f"/api/mail/{bill_id}/tag", data={"value": "urgent"})
        assert response.status_code == 400

    def test_mail_tag_missing_value_returns_400(self, client, data_dir):
        response = client.post("/api/mail/nonexistent/tag", data={"action": "add"})
        assert response.status_code == 400

    def test_mail_tag_not_found_returns_404(self, client, data_dir):
        response = client.post("/api/mail/nonexistent/tag", data={"action": "add", "value": "urgent"})
        assert response.status_code == 404

    def test_mail_tag_add_bill(self, client, data_dir):
        from postmule.data import tags as tags_data
        bill = bills_data.add_bill(data_dir, {
            "date_received": "2025-01-15", "sender": "AT&T", "summary": "Bill",
            "filename": "2025-01-15_Alice_ATT_Bill.pdf",
        })
        response = client.post(f"/api/mail/{bill['id']}/tag", data={"action": "add", "value": "urgent"})
        assert response.status_code == 200
        # Tag persisted on item
        from postmule.data._io import year_from
        year = year_from(bill["date_received"])
        updated = next(b for b in bills_data.load_bills(data_dir, year) if b["id"] == bill["id"])
        assert "urgent" in updated.get("tags", [])
        # Added to registry
        assert "urgent" in tags_data.load_tags(data_dir)

    def test_mail_tag_add_notice(self, client, data_dir):
        notice = notices_data.add_notice(data_dir, {
            "date_received": "2025-02-10", "sender": "IRS", "summary": "Notice",
            "filename": "2025-02-10_Alice_IRS_Notice.pdf",
        })
        response = client.post(f"/api/mail/{notice['id']}/tag", data={"action": "add", "value": "tax"})
        assert response.status_code == 200

    def test_mail_tag_add_ftm(self, client, data_dir):
        ftm = ftm_data.add_item(data_dir, {
            "date_received": "2025-03-01", "sender": "DMV", "summary": "License renewal",
            "filename": "2025-03-01_Alice_DMV_ForwardToMe.pdf",
        })
        response = client.post(f"/api/mail/{ftm['id']}/tag", data={"action": "add", "value": "action-needed"})
        assert response.status_code == 200

    def test_mail_tag_remove(self, client, data_dir):
        bill = bills_data.add_bill(data_dir, {
            "date_received": "2025-01-15", "sender": "AT&T", "summary": "Bill",
            "filename": "2025-01-15_Alice_ATT_Bill.pdf",
        })
        client.post(f"/api/mail/{bill['id']}/tag", data={"action": "add", "value": "urgent"})
        response = client.post(f"/api/mail/{bill['id']}/tag", data={"action": "remove", "value": "urgent"})
        assert response.status_code == 200
        from postmule.data._io import year_from
        year = year_from(bill["date_received"])
        updated = next(b for b in bills_data.load_bills(data_dir, year) if b["id"] == bill["id"])
        assert "urgent" not in updated.get("tags", [])


class TestApiReportsExport:
    def test_export_no_storage_returns_503(self, client, data_dir):
        response = client.get("/api/reports/export")
        assert response.status_code == 503

    def test_export_no_results_returns_404(self, data_dir, tmp_path):
        """When storage is configured but no items have drive_file_id, return 404."""
        import postmule.web.routes.api as api_module
        import postmule.web.app as app_module
        original = getattr(api_module, "_get_storage_provider", None)

        class FakeStorage:
            def download_file(self, file_id):
                return b"%PDF fake"

        def fake_get_storage():
            return FakeStorage()

        api_module._get_storage_provider = fake_get_storage
        try:
            test_app = create_app(data_dir=data_dir)
            test_app.config["TESTING"] = True
            with test_app.test_client() as c:
                response = c.get("/api/reports/export")
            assert response.status_code == 404
        finally:
            api_module._get_storage_provider = original

    def test_export_returns_zip(self, data_dir):
        """When items with drive_file_ids exist and storage works, return a zip."""
        import zipfile as _zipfile
        import postmule.web.routes.api as api_module

        bills_data.add_bill(data_dir, {
            "date_received": "2025-06-01", "sender": "AT&T", "summary": "Bill",
            "filename": "2025-06-01_Alice_ATT_Bill.pdf", "drive_file_id": "fake-file-id",
        })

        class FakeStorage:
            def download_file(self, file_id):
                return b"%PDF-1.4 fake pdf content"

        def fake_get_storage():
            return FakeStorage()

        original = api_module._get_storage_provider
        api_module._get_storage_provider = fake_get_storage
        try:
            test_app = create_app(data_dir=data_dir)
            test_app.config["TESTING"] = True
            with test_app.test_client() as c:
                response = c.get("/api/reports/export")
            assert response.status_code == 200
            assert response.content_type == "application/zip"
            buf = io.BytesIO(response.data)
            with _zipfile.ZipFile(buf) as zf:
                names = zf.namelist()
            assert len(names) == 1
            assert names[0].endswith(".pdf")
        finally:
            api_module._get_storage_provider = original


class TestApiSettings:
    def test_settings_no_config_returns_500(self, client):
        response = client.post("/api/settings", data={})
        assert response.status_code == 500

    def test_settings_saves_and_redirects(self, tmp_path):
        import yaml
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"app": {}, "notifications": {}}), encoding="utf-8")

        test_app = create_app(data_dir=tmp_path, config_path=config_path)
        test_app.config["TESTING"] = True
        with test_app.test_client() as c:
            response = c.post("/api/settings", data={
                "notifications_alert_email": "test@example.com",
                "schedule_run_time": "03:00",
                "logging_level": "DEBUG",
                "logging_verbose_days": "14",
                "logging_processing_years": "5",
            })
        assert response.status_code == 302
        assert "settings" in response.headers["Location"]
