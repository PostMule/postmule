"""Unit tests for postmule.providers.email.gmail."""

import base64
from unittest.mock import MagicMock, patch

import pytest

from postmule.providers.email.gmail import (
    EmailMessage,
    GmailProvider,
    _flatten_parts,
    _parse_email_date,
)


class TestFlattenParts:
    def test_single_part(self):
        payload = {"mimeType": "text/plain", "body": {}}
        parts = _flatten_parts(payload)
        assert len(parts) == 1
        assert parts[0] == payload

    def test_nested_multipart(self):
        payload = {
            "parts": [
                {"mimeType": "text/plain", "body": {}},
                {"mimeType": "text/html", "body": {}},
            ]
        }
        parts = _flatten_parts(payload)
        assert len(parts) == 2

    def test_deeply_nested(self):
        payload = {
            "parts": [
                {
                    "parts": [
                        {"mimeType": "application/pdf", "body": {}},
                    ]
                }
            ]
        }
        parts = _flatten_parts(payload)
        assert len(parts) == 1
        assert parts[0]["mimeType"] == "application/pdf"


class TestParseEmailDate:
    def test_valid_rfc2822_date(self):
        result = _parse_email_date("Thu, 01 Jan 2025 12:00:00 +0000")
        assert result == "2025-01-01"

    def test_invalid_date_returns_today(self):
        from datetime import date
        result = _parse_email_date("not a date")
        assert result == date.today().isoformat()

    def test_empty_string_returns_today(self):
        from datetime import date
        result = _parse_email_date("")
        assert result == date.today().isoformat()


class TestGmailProviderInit:
    def test_default_label_name(self):
        provider = GmailProvider(credentials={})
        assert provider.label_name == "PostMule"

    def test_custom_label_name(self):
        provider = GmailProvider(credentials={}, label_name="PostMule")
        assert provider.label_name == "PostMule"


class TestGetOrCreateLabel:
    def _make_provider_with_mock_service(self, labels=None):
        provider = GmailProvider(credentials={"refresh_token": "x", "client_id": "y", "client_secret": "z"})
        svc = MagicMock()
        svc.users().labels().list().execute.return_value = {
            "labels": labels or []
        }
        provider._service = svc
        return provider, svc

    def test_returns_existing_label_id(self):
        provider, svc = self._make_provider_with_mock_service(
            labels=[{"id": "label-postmule", "name": "PostMule"}]
        )
        label_id = provider._get_or_create_label()
        assert label_id == "label-postmule"

    def test_creates_label_when_not_found(self):
        provider, svc = self._make_provider_with_mock_service(labels=[])
        svc.users().labels().create().execute.return_value = {"id": "new-label-id"}
        label_id = provider._get_or_create_label()
        assert label_id == "new-label-id"

    def test_caches_label_id(self):
        provider, svc = self._make_provider_with_mock_service(
            labels=[{"id": "label-postmule", "name": "PostMule"}]
        )
        provider._get_or_create_label()
        provider._get_or_create_label()  # Second call should use cache
        assert svc.users().labels().list().execute.call_count == 1


class TestListUnprocessedEmails:
    def _make_provider(self):
        provider = GmailProvider(credentials={})
        svc = MagicMock()
        # Mock label creation
        svc.users().labels().list().execute.return_value = {
            "labels": [{"id": "lbl1", "name": "VPM"}]
        }
        provider._service = svc
        return provider, svc

    def test_returns_empty_when_no_messages(self):
        provider, svc = self._make_provider()
        svc.users().messages().list().execute.return_value = {"messages": []}
        emails = provider.list_unprocessed_emails()
        assert emails == []

    def test_loads_message_details(self):
        provider, svc = self._make_provider()
        svc.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1"}]
        }
        # Mock message fetch with PDF attachment
        pdf_data = base64.urlsafe_b64encode(b"%PDF fake").decode()
        svc.users().messages().get().execute.return_value = {
            "id": "msg1",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "[Scan Request] Mail"},
                    {"name": "From", "value": "noreply@virtualpostmail.com"},
                    {"name": "Date", "value": "Thu, 01 Jan 2025 12:00:00 +0000"},
                ],
                "parts": [
                    {
                        "filename": "scan.pdf",
                        "mimeType": "application/pdf",
                        "body": {"data": pdf_data},
                    }
                ],
            },
        }
        emails = provider.list_unprocessed_emails()
        assert len(emails) == 1
        assert emails[0].message_id == "msg1"
        assert len(emails[0].attachments) == 1

    def test_skips_message_load_errors(self):
        provider, svc = self._make_provider()
        svc.users().messages().list().execute.return_value = {
            "messages": [{"id": "bad-msg"}]
        }
        svc.users().messages().get().execute.side_effect = Exception("API error")
        emails = provider.list_unprocessed_emails()
        assert emails == []


class TestMarkAsProcessed:
    def test_applies_label(self):
        provider = GmailProvider(credentials={})
        svc = MagicMock()
        svc.users().labels().list().execute.return_value = {
            "labels": [{"id": "lbl1", "name": "PostMule"}]
        }
        provider._service = svc
        provider.mark_as_processed("msg-abc")
        svc.users().messages().modify.assert_called_once()
        call_kwargs = svc.users().messages().modify.call_args[1]
        assert call_kwargs["id"] == "msg-abc"
        assert "lbl1" in call_kwargs["body"]["addLabelIds"]


class TestExtractPdfAttachments:
    def test_extracts_inline_pdf(self):
        provider = GmailProvider(credentials={})
        svc = MagicMock()
        pdf_data = base64.urlsafe_b64encode(b"%PDF data").decode()
        msg = {
            "payload": {
                "parts": [
                    {
                        "filename": "doc.pdf",
                        "mimeType": "application/pdf",
                        "body": {"data": pdf_data},
                    }
                ]
            }
        }
        result = provider._extract_pdf_attachments(svc, "msg1", msg)
        assert len(result) == 1
        assert result[0]["name"] == "doc.pdf"
        assert result[0]["data"] == b"%PDF data"

    def test_fetches_attachment_by_id(self):
        provider = GmailProvider(credentials={})
        svc = MagicMock()
        pdf_data = base64.urlsafe_b64encode(b"%PDF attached").decode()
        svc.users().messages().attachments().get().execute.return_value = {
            "data": pdf_data
        }
        msg = {
            "payload": {
                "parts": [
                    {
                        "filename": "attach.pdf",
                        "mimeType": "application/pdf",
                        "body": {"attachmentId": "att-123"},
                    }
                ]
            }
        }
        result = provider._extract_pdf_attachments(svc, "msg1", msg)
        assert len(result) == 1
        assert result[0]["data"] == b"%PDF attached"

    def test_skips_non_pdf_parts(self):
        provider = GmailProvider(credentials={})
        svc = MagicMock()
        msg = {
            "payload": {
                "parts": [
                    {
                        "filename": "image.jpg",
                        "mimeType": "image/jpeg",
                        "body": {"data": "fake"},
                    }
                ]
            }
        }
        result = provider._extract_pdf_attachments(svc, "msg1", msg)
        assert result == []
