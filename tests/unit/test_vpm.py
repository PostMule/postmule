"""
Unit tests for postmule/providers/mailbox/vpm.py
and postmule/agents/mailbox_ingestion.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from postmule.providers.mailbox.vpm import (
    MailItem,
    VpmProvider,
    _parse_vpm_date,
)


# ---------------------------------------------------------------------------
# _parse_vpm_date
# ---------------------------------------------------------------------------

class TestParseVpmDate:
    def test_iso_format(self):
        assert _parse_vpm_date("2025-11-15") == "2025-11-15"

    def test_us_slash_format(self):
        assert _parse_vpm_date("11/15/2025") == "2025-11-15"

    def test_iso_datetime(self):
        assert _parse_vpm_date("2025-11-15T14:30:00") == "2025-11-15"

    def test_iso_datetime_z(self):
        assert _parse_vpm_date("2025-11-15T14:30:00Z") == "2025-11-15"

    def test_empty_string_returns_today(self):
        from datetime import date
        result = _parse_vpm_date("")
        assert result == date.today().isoformat()

    def test_unparseable_returns_today(self):
        from datetime import date
        result = _parse_vpm_date("not-a-date")
        assert result == date.today().isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session_mock(responses):
    """
    Build a mock requests.Session where session.post() returns items from responses list.
    Each element of responses is a mock response.
    """
    session = MagicMock()
    session.post.side_effect = responses
    return session


def _json_response(data: dict, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    resp.headers = {"Content-Type": "application/json"}
    return resp


def _pdf_response(pdf_bytes: bytes = b"%PDF-1.4 fake"):
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {"Content-Type": "application/pdf"}
    resp.content = pdf_bytes
    resp.raise_for_status = MagicMock()
    return resp


def _make_provider(username="user@example.com", password="secret"):
    p = VpmProvider(username, password)
    return p


# ---------------------------------------------------------------------------
# VpmProvider._login
# ---------------------------------------------------------------------------

class TestVpmLogin:
    def test_successful_login_returns_token(self):
        provider = _make_provider()
        login_resp = _json_response({"success": True, "token": "tok123"})

        with patch("requests.Session") as MockSession:
            MockSession.return_value.post.return_value = login_resp
            MockSession.return_value.headers = {}
            token = provider._login()

        assert token == "tok123"

    def test_login_raises_on_failure(self):
        provider = _make_provider()
        login_resp = _json_response({"success": False, "error": "invalid credentials"})

        with patch("requests.Session") as MockSession:
            MockSession.return_value.post.return_value = login_resp
            MockSession.return_value.headers = {}
            with pytest.raises(RuntimeError, match="invalid credentials"):
                provider._login()

    def test_login_raises_when_no_token_in_response(self):
        provider = _make_provider()
        login_resp = _json_response({"success": True, "token": ""})

        with patch("requests.Session") as MockSession:
            MockSession.return_value.post.return_value = login_resp
            MockSession.return_value.headers = {}
            with pytest.raises(RuntimeError, match="no token"):
                provider._login()

    def test_login_sends_correct_payload(self):
        provider = _make_provider("u@x.com", "pw")
        login_resp = _json_response({"success": True, "token": "abc"})

        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_session.post.return_value = login_resp
            mock_session.headers = {}
            provider._login()

        call_kwargs = mock_session.post.call_args
        assert call_kwargs.kwargs["data"]["action"] == "doLogin"
        assert call_kwargs.kwargs["data"]["login"] == "u@x.com"
        assert call_kwargs.kwargs["data"]["password"] == "pw"


# ---------------------------------------------------------------------------
# VpmProvider.list_unprocessed_items
# ---------------------------------------------------------------------------

class TestListUnprocessedItems:
    def _setup_provider_with_token(self, items):
        """Return a provider that has a cached token and returns given items."""
        provider = _make_provider()
        provider._token = "cached_token"
        list_resp = _json_response({"success": True, "items": items})

        session = MagicMock()
        session.post.return_value = list_resp
        provider._session = session
        return provider

    def test_returns_unviewed_items(self):
        provider = self._setup_provider_with_token([
            {"mailItemID": "101", "receivedDate": "2025-11-15", "senderName": "ACME", "scanDate": "2025-11-16", "viewed": False},
            {"mailItemID": "102", "receivedDate": "2025-11-14", "senderName": "FedEx", "scanDate": "2025-11-15", "viewed": False},
        ])
        items = provider.list_unprocessed_items()
        assert len(items) == 2
        assert items[0].mail_item_id == "101"
        assert items[0].received_date == "2025-11-15"
        assert items[0].sender == "ACME"

    def test_skips_viewed_items(self):
        provider = self._setup_provider_with_token([
            {"mailItemID": "101", "receivedDate": "2025-11-15", "senderName": "ACME", "scanDate": "2025-11-16", "viewed": True},
            {"mailItemID": "102", "receivedDate": "2025-11-14", "senderName": "FedEx", "scanDate": "2025-11-15", "viewed": False},
        ])
        items = provider.list_unprocessed_items()
        assert len(items) == 1
        assert items[0].mail_item_id == "102"

    def test_skips_items_with_status_viewed(self):
        provider = self._setup_provider_with_token([
            {"mailItemID": "103", "receivedDate": "2025-11-10", "senderName": "UPS", "scanDate": "2025-11-11", "status": "viewed"},
        ])
        items = provider.list_unprocessed_items()
        assert len(items) == 0

    def test_skips_items_without_id(self):
        provider = self._setup_provider_with_token([
            {"receivedDate": "2025-11-10", "senderName": "UPS", "scanDate": "2025-11-11"},
        ])
        items = provider.list_unprocessed_items()
        assert len(items) == 0

    def test_returns_empty_list_when_no_items(self):
        provider = self._setup_provider_with_token([])
        items = provider.list_unprocessed_items()
        assert items == []

    def test_raises_on_api_failure(self):
        provider = _make_provider()
        provider._token = "tok"
        provider._session = MagicMock()
        provider._session.post.return_value = _json_response(
            {"success": False, "error": "server error"}
        )
        with pytest.raises(RuntimeError, match="listMail failed"):
            provider.list_unprocessed_items()

    def test_accepts_mailItems_key(self):
        """VPM API may return items under 'mailItems' rather than 'items'."""
        provider = _make_provider()
        provider._token = "tok"
        provider._session = MagicMock()
        provider._session.post.return_value = _json_response({
            "success": True,
            "mailItems": [
                {"mailItemID": "200", "receivedDate": "2025-11-01", "senderName": "X", "scanDate": "2025-11-02"}
            ],
        })
        items = provider.list_unprocessed_items()
        assert len(items) == 1
        assert items[0].mail_item_id == "200"

    def test_accepts_alternative_field_names(self):
        """Some VPM accounts use dateReceived/sender/dateScan naming."""
        provider = _make_provider()
        provider._token = "tok"
        provider._session = MagicMock()
        provider._session.post.return_value = _json_response({
            "success": True,
            "items": [
                {"id": "301", "dateReceived": "11/20/2025", "sender": "Dept of Water", "dateScan": "11/21/2025"},
            ],
        })
        items = provider.list_unprocessed_items()
        assert len(items) == 1
        assert items[0].mail_item_id == "301"
        assert items[0].received_date == "2025-11-20"
        assert items[0].sender == "Dept of Water"


# ---------------------------------------------------------------------------
# VpmProvider.download_pdf
# ---------------------------------------------------------------------------

class TestDownloadPdf:
    def test_returns_pdf_bytes(self):
        provider = _make_provider()
        provider._token = "tok"
        provider._session = MagicMock()
        provider._session.post.return_value = _pdf_response(b"%PDF-1.4 real")

        result = provider.download_pdf("101")
        assert result == b"%PDF-1.4 real"

    def test_raises_on_empty_response(self):
        provider = _make_provider()
        provider._token = "tok"
        provider._session = MagicMock()
        resp = _pdf_response(b"")
        resp.content = b""
        provider._session.post.return_value = resp

        with pytest.raises(RuntimeError, match="empty PDF"):
            provider.download_pdf("101")

    def test_raises_on_json_error_response(self):
        provider = _make_provider()
        provider._token = "tok"
        provider._session = MagicMock()
        err_resp = _json_response({"success": False, "error": "item not found"})
        provider._session.post.return_value = err_resp

        with pytest.raises(RuntimeError):
            provider.download_pdf("999")

    def test_sends_correct_payload(self):
        provider = _make_provider()
        provider._token = "tok123"
        provider._session = MagicMock()
        provider._session.post.return_value = _pdf_response(b"%PDF content")

        provider.download_pdf("42")

        call_data = provider._session.post.call_args.kwargs["data"]
        assert call_data["action"] == "getMailItemImagePDF"
        assert call_data["token"] == "tok123"
        assert call_data["mailItemID"] == "42"

    def test_accepts_octet_stream_content_type(self):
        provider = _make_provider()
        provider._token = "tok"
        provider._session = MagicMock()
        resp = _pdf_response(b"%PDF-octet")
        resp.headers = {"Content-Type": "application/octet-stream"}
        provider._session.post.return_value = resp

        result = provider.download_pdf("55")
        assert result == b"%PDF-octet"


# ---------------------------------------------------------------------------
# VpmProvider.mark_as_processed
# ---------------------------------------------------------------------------

class TestMarkAsProcessed:
    def test_successful_mark(self):
        provider = _make_provider()
        provider._token = "tok"
        provider._session = MagicMock()
        provider._session.post.return_value = _json_response({"success": True})

        provider.mark_as_processed("101")  # should not raise

    def test_raises_on_failure(self):
        provider = _make_provider()
        provider._token = "tok"
        provider._session = MagicMock()
        provider._session.post.return_value = _json_response(
            {"success": False, "error": "item already marked"}
        )

        with pytest.raises(RuntimeError, match="doMarkAsViewed failed"):
            provider.mark_as_processed("101")

    def test_sends_correct_payload(self):
        provider = _make_provider()
        provider._token = "tok_x"
        provider._session = MagicMock()
        provider._session.post.return_value = _json_response({"success": True})

        provider.mark_as_processed("77")

        call_data = provider._session.post.call_args.kwargs["data"]
        assert call_data["action"] == "doMarkAsViewed"
        assert call_data["token"] == "tok_x"
        assert call_data["mailItemID"] == "77"


# ---------------------------------------------------------------------------
# VpmProvider token expiry / re-authentication
# ---------------------------------------------------------------------------

class TestTokenExpiry:
    def test_re_authenticates_on_auth_error(self):
        """If an API call returns a login error, provider re-auths and retries."""
        provider = _make_provider()
        provider._token = "expired_token"

        auth_error_resp = _json_response({"success": False, "error": "please login again"})
        re_login_resp = _json_response({"success": True, "token": "fresh_token"})
        retry_resp = _json_response({"success": True, "items": []})

        session = MagicMock()
        # First call: auth error; second call: re-login; third call: successful listMail
        session.post.side_effect = [auth_error_resp, re_login_resp, retry_resp]
        provider._session = session

        items = provider.list_unprocessed_items()
        assert items == []
        assert provider._token == "fresh_token"


# ---------------------------------------------------------------------------
# mailbox_ingestion.run_vpm_ingestion
# ---------------------------------------------------------------------------

class TestRunVpmIngestion:
    def _make_vpm(self, items=None, pdf_bytes=b"%PDF fake"):
        vpm = MagicMock()
        vpm.list_unprocessed_items.return_value = items or []
        vpm.download_pdf.return_value = pdf_bytes
        vpm.mark_as_processed.return_value = None
        return vpm

    def _make_drive(self, drive_id="drive_abc"):
        drive = MagicMock()
        drive.upload_pdf.return_value = drive_id
        return drive

    def test_no_items_returns_empty_result(self, tmp_path):
        from postmule.agents.mailbox_ingestion import run_vpm_ingestion
        vpm = self._make_vpm(items=[])
        drive = self._make_drive()

        result = run_vpm_ingestion(vpm, drive, "inbox_id", tmp_path)

        assert result.emails_found == 0
        assert result.ingested == []
        vpm.download_pdf.assert_not_called()

    def test_downloads_and_uploads_pdf(self, tmp_path):
        from postmule.agents.mailbox_ingestion import run_vpm_ingestion
        items = [MailItem("101", "2025-11-15", "ACME", "2025-11-16")]
        vpm = self._make_vpm(items=items, pdf_bytes=b"%PDF-1.4 real")
        drive = self._make_drive("drv_id_1")

        result = run_vpm_ingestion(vpm, drive, "inbox_id", tmp_path)

        assert result.emails_found == 1
        assert result.pdfs_uploaded == 1
        assert len(result.ingested) == 1
        assert result.ingested[0].drive_file_id == "drv_id_1"
        assert result.ingested[0].received_date == "2025-11-15"
        assert result.ingested[0].source_email_id == "101"
        vpm.mark_as_processed.assert_called_once_with("101")

    def test_pdf_saved_to_disk(self, tmp_path):
        from postmule.agents.mailbox_ingestion import run_vpm_ingestion
        items = [MailItem("202", "2025-11-20", "Sender", "2025-11-21")]
        vpm = self._make_vpm(items=items, pdf_bytes=b"%PDF bytes")
        drive = self._make_drive()

        run_vpm_ingestion(vpm, drive, "inbox_id", tmp_path)

        saved = list(tmp_path.glob("*.pdf"))
        assert len(saved) == 1
        assert saved[0].read_bytes() == b"%PDF bytes"

    def test_dry_run_does_not_upload_or_mark(self, tmp_path):
        from postmule.agents.mailbox_ingestion import run_vpm_ingestion
        items = [MailItem("303", "2025-11-15", "X", "2025-11-16")]
        vpm = self._make_vpm(items=items)
        drive = self._make_drive()

        result = run_vpm_ingestion(vpm, drive, "inbox_id", tmp_path, dry_run=True)

        assert result.pdfs_uploaded == 1
        assert len(result.ingested) == 1
        assert result.ingested[0].drive_file_id == ""
        drive.upload_pdf.assert_not_called()
        vpm.mark_as_processed.assert_not_called()

    def test_download_failure_skips_item(self, tmp_path):
        from postmule.agents.mailbox_ingestion import run_vpm_ingestion
        items = [MailItem("404", "2025-11-15", "X", "2025-11-16")]
        vpm = self._make_vpm(items=items)
        vpm.download_pdf.side_effect = RuntimeError("network error")
        drive = self._make_drive()

        result = run_vpm_ingestion(vpm, drive, "inbox_id", tmp_path)

        assert result.pdfs_uploaded == 0
        assert len(result.errors) == 1
        assert "404" in result.errors[0]
        vpm.mark_as_processed.assert_not_called()

    def test_upload_failure_skips_mark_as_processed(self, tmp_path):
        from postmule.agents.mailbox_ingestion import run_vpm_ingestion
        items = [MailItem("505", "2025-11-15", "Y", "2025-11-16")]
        vpm = self._make_vpm(items=items)
        drive = self._make_drive()
        drive.upload_pdf.side_effect = RuntimeError("drive full")

        result = run_vpm_ingestion(vpm, drive, "inbox_id", tmp_path)

        assert result.pdfs_uploaded == 0
        assert len(result.errors) == 1
        vpm.mark_as_processed.assert_not_called()

    def test_list_failure_returns_error_result(self, tmp_path):
        from postmule.agents.mailbox_ingestion import run_vpm_ingestion
        vpm = MagicMock()
        vpm.list_unprocessed_items.side_effect = RuntimeError("VPM API down")
        drive = self._make_drive()

        result = run_vpm_ingestion(vpm, drive, "inbox_id", tmp_path)

        assert result.emails_found == 0
        assert len(result.errors) == 1
        assert "VPM API down" in result.errors[0]

    def test_mark_failure_is_non_fatal(self, tmp_path):
        """A failure in mark_as_processed should log a warning but not abort."""
        from postmule.agents.mailbox_ingestion import run_vpm_ingestion
        items = [MailItem("606", "2025-11-15", "Z", "2025-11-16")]
        vpm = self._make_vpm(items=items)
        vpm.mark_as_processed.side_effect = RuntimeError("mark failed")
        drive = self._make_drive()

        result = run_vpm_ingestion(vpm, drive, "inbox_id", tmp_path)

        assert result.pdfs_uploaded == 1
        assert result.errors == []  # mark failure is a warning, not an error

    def test_filename_includes_date_and_item_id(self, tmp_path):
        from postmule.agents.mailbox_ingestion import run_vpm_ingestion
        items = [MailItem("ID42", "2025-11-15", "Sender", "2025-11-16")]
        vpm = self._make_vpm(items=items)
        drive = self._make_drive()

        run_vpm_ingestion(vpm, drive, "inbox_id", tmp_path)

        saved = list(tmp_path.glob("*.pdf"))
        assert len(saved) == 1
        assert "2025-11-15" in saved[0].name
        assert "ID42" in saved[0].name
