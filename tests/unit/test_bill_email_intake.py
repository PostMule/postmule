"""Unit tests for postmule.agents.bill_email_intake."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from postmule.agents.bill_email_intake import _build_filename, run_intake
from postmule.agents.email_ingestion import IngestionResult
from postmule.providers.email.base import EmailMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_email(message_id="msg1", received_date="2026-03-24", sender="billing@att.com",
                filename="invoice.pdf", data=b"%PDF-1.4"):
    return EmailMessage(
        message_id=message_id,
        subject="Your AT&T Bill",
        received_date=received_date,
        sender=sender,
        attachments=[{"name": filename, "data": data}],
    )


def _make_provider(emails=None):
    provider = MagicMock()
    provider.list_emails_with_pdf_attachments.return_value = emails if emails is not None else []
    return provider


def _make_drive(drive_id="drive-file-123"):
    drive = MagicMock()
    drive.upload_pdf.return_value = drive_id
    return drive


# ---------------------------------------------------------------------------
# _build_filename
# ---------------------------------------------------------------------------

class TestBuildFilename:
    def test_adds_date_prefix(self):
        name = _build_filename("invoice.pdf", "2026-03-24")
        assert name.startswith("2026-03-24_bill_invoice.pdf")

    def test_adds_pdf_extension_when_missing(self):
        name = _build_filename("statement", "2026-03-24")
        assert name.endswith(".pdf")

    def test_does_not_double_prefix_if_already_dated(self):
        name = _build_filename("2026-03-24_bill_invoice.pdf", "2026-03-24")
        assert name == "2026-03-24_bill_invoice.pdf"

    def test_sanitizes_special_characters(self):
        name = _build_filename("my invoice (final).pdf", "2026-03-24")
        assert " " not in name
        assert "(" not in name
        assert ")" not in name


# ---------------------------------------------------------------------------
# run_intake — no emails
# ---------------------------------------------------------------------------

class TestRunIntakeNoEmails:
    def test_returns_zero_counts_when_no_emails(self, tmp_path):
        provider = _make_provider(emails=[])
        drive = _make_drive()
        result = run_intake(provider, drive, "inbox-id", tmp_path)

        assert result.emails_found == 0
        assert result.pdfs_uploaded == 0
        assert result.ingested == []
        assert result.errors == []

    def test_does_not_call_drive_when_no_emails(self, tmp_path):
        provider = _make_provider(emails=[])
        drive = _make_drive()
        run_intake(provider, drive, "inbox-id", tmp_path)
        drive.upload_pdf.assert_not_called()


# ---------------------------------------------------------------------------
# run_intake — normal flow
# ---------------------------------------------------------------------------

class TestRunIntakeNormalFlow:
    def test_uploads_pdf_and_marks_processed(self, tmp_path):
        email = _make_email()
        provider = _make_provider(emails=[email])
        drive = _make_drive()

        result = run_intake(provider, drive, "inbox-id", tmp_path)

        assert result.emails_found == 1
        assert result.pdfs_uploaded == 1
        assert len(result.ingested) == 1
        assert result.errors == []
        drive.upload_pdf.assert_called_once()
        provider.mark_as_processed.assert_called_once_with("msg1")

    def test_ingested_item_has_correct_fields(self, tmp_path):
        email = _make_email(message_id="abc", received_date="2026-03-24")
        provider = _make_provider(emails=[email])
        drive = _make_drive(drive_id="drv-xyz")

        result = run_intake(provider, drive, "inbox-id", tmp_path)

        item = result.ingested[0]
        assert item.source_email_id == "abc"
        assert item.received_date == "2026-03-24"
        assert item.drive_file_id == "drv-xyz"
        assert item.local_path.exists()

    def test_multiple_attachments_on_one_email(self, tmp_path):
        email = EmailMessage(
            message_id="multi",
            subject="Bills",
            received_date="2026-03-24",
            sender="bills@company.com",
            attachments=[
                {"name": "bill1.pdf", "data": b"%PDF"},
                {"name": "bill2.pdf", "data": b"%PDF"},
            ],
        )
        provider = _make_provider(emails=[email])
        drive = _make_drive()

        result = run_intake(provider, drive, "inbox-id", tmp_path)

        assert result.pdfs_uploaded == 2
        assert len(result.ingested) == 2
        # Email is only marked processed once (after all attachments succeed)
        provider.mark_as_processed.assert_called_once_with("multi")

    def test_multiple_emails(self, tmp_path):
        emails = [_make_email(message_id=f"msg{i}") for i in range(3)]
        provider = _make_provider(emails=emails)
        drive = _make_drive()

        result = run_intake(provider, drive, "inbox-id", tmp_path)

        assert result.emails_found == 3
        assert result.pdfs_uploaded == 3
        assert provider.mark_as_processed.call_count == 3


# ---------------------------------------------------------------------------
# run_intake — dry run
# ---------------------------------------------------------------------------

class TestRunIntakeDryRun:
    def test_dry_run_does_not_upload(self, tmp_path):
        email = _make_email()
        provider = _make_provider(emails=[email])
        drive = _make_drive()

        result = run_intake(provider, drive, "inbox-id", tmp_path, dry_run=True)

        drive.upload_pdf.assert_not_called()
        provider.mark_as_processed.assert_not_called()

    def test_dry_run_still_reports_counts(self, tmp_path):
        email = _make_email()
        provider = _make_provider(emails=[email])
        drive = _make_drive()

        result = run_intake(provider, drive, "inbox-id", tmp_path, dry_run=True)

        assert result.emails_found == 1
        assert result.pdfs_uploaded == 1
        assert len(result.ingested) == 1

    def test_dry_run_ingested_has_no_drive_file_id(self, tmp_path):
        email = _make_email()
        provider = _make_provider(emails=[email])
        drive = _make_drive()

        result = run_intake(provider, drive, "inbox-id", tmp_path, dry_run=True)

        assert result.ingested[0].drive_file_id == ""


# ---------------------------------------------------------------------------
# run_intake — error handling
# ---------------------------------------------------------------------------

class TestRunIntakeErrors:
    def test_list_emails_exception_returns_error(self, tmp_path):
        provider = MagicMock()
        provider.list_emails_with_pdf_attachments.side_effect = RuntimeError("auth failure")
        drive = _make_drive()

        result = run_intake(provider, drive, "inbox-id", tmp_path)

        assert result.emails_found == 0
        assert len(result.errors) == 1
        assert "auth failure" in result.errors[0]

    def test_upload_failure_does_not_mark_processed(self, tmp_path):
        email = _make_email()
        provider = _make_provider(emails=[email])
        drive = MagicMock()
        drive.upload_pdf.side_effect = IOError("network error")

        result = run_intake(provider, drive, "inbox-id", tmp_path)

        provider.mark_as_processed.assert_not_called()
        assert len(result.errors) == 1

    def test_mark_processed_failure_is_non_fatal(self, tmp_path):
        email = _make_email()
        provider = _make_provider(emails=[email])
        provider.mark_as_processed.side_effect = RuntimeError("label error")
        drive = _make_drive()

        result = run_intake(provider, drive, "inbox-id", tmp_path)

        # Upload still succeeds; error in mark_processed is only logged, not in result.errors
        assert result.pdfs_uploaded == 1
        assert result.errors == []

    def test_partial_attachment_failure_leaves_email_unprocessed(self, tmp_path):
        email = EmailMessage(
            message_id="partial",
            subject="Bills",
            received_date="2026-03-24",
            sender="bills@co.com",
            attachments=[
                {"name": "ok.pdf", "data": b"%PDF"},
                {"name": "bad.pdf", "data": b"%PDF"},
            ],
        )
        provider = _make_provider(emails=[email])
        drive = MagicMock()
        # First upload OK, second fails
        drive.upload_pdf.side_effect = [MagicMock(return_value="drv-1"), IOError("fail")]

        result = run_intake(provider, drive, "inbox-id", tmp_path)

        provider.mark_as_processed.assert_not_called()


# ---------------------------------------------------------------------------
# Pipeline integration — bill_intake_providers wired up
# ---------------------------------------------------------------------------

class TestPipelineBillIntakeIntegration:
    """Verify that pipeline step 1b calls run_intake for each bill_intake provider."""

    def test_pipeline_calls_intake_for_each_bill_provider(self, tmp_path):
        from unittest.mock import patch, MagicMock
        import yaml
        from postmule.core.config import load_config
        from postmule.pipeline import Providers, run_daily_pipeline

        cfg_data = {
            "app": {"dry_run": False, "install_dir": str(tmp_path)},
            "notifications": {"alert_email": "test@example.com"},
            "llm": {
                "providers": [{"service": "gemini", "enabled": True}],
                "classification_confidence_threshold": 0.80,
            },
            "email": {"providers": [{"service": "gmail", "enabled": True}]},
            "storage": {"providers": [{"service": "google_drive", "enabled": True}]},
            "data_protection": {"max_files_moved_per_run": 50},
            "deployment": {"dashboard_port": 5000},
        }
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml.dump(cfg_data))
        cfg = load_config(cfg_path)

        # Build providers with two bill_intake providers
        bp1 = _make_provider(emails=[])
        bp2 = _make_provider(emails=[])

        drive = MagicMock()
        drive.ensure_folder_structure.return_value = {"inbox": "inbox-id", "needs_review": "nr"}
        drive.list_folder.return_value = []

        providers = Providers(
            gmail=MagicMock(),
            drive=drive,
            sheets=MagicMock(),
            llm=MagicMock(),
            safety_agent=MagicMock(summary=MagicMock(return_value={})),
            folder_ids={"inbox": "inbox-id", "needs_review": "nr"},
            bill_intake_providers=[bp1, bp2],
        )

        with patch("postmule.pipeline._build_providers", return_value=providers):
            run_daily_pipeline(cfg, {}, tmp_path, dry_run=True)

        bp1.list_emails_with_pdf_attachments.assert_called_once()
        bp2.list_emails_with_pdf_attachments.assert_called_once()

    def test_pipeline_skips_intake_when_no_bill_providers(self, tmp_path):
        from unittest.mock import patch, MagicMock
        import yaml
        from postmule.core.config import load_config
        from postmule.pipeline import Providers, run_daily_pipeline

        cfg_data = {
            "app": {"dry_run": False, "install_dir": str(tmp_path)},
            "notifications": {"alert_email": "test@example.com"},
            "llm": {
                "providers": [{"service": "gemini", "enabled": True}],
                "classification_confidence_threshold": 0.80,
            },
            "email": {"providers": [{"service": "gmail", "enabled": True}]},
            "storage": {"providers": [{"service": "google_drive", "enabled": True}]},
            "data_protection": {"max_files_moved_per_run": 50},
            "deployment": {"dashboard_port": 5000},
        }
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml.dump(cfg_data))
        cfg = load_config(cfg_path)

        drive = MagicMock()
        drive.ensure_folder_structure.return_value = {"inbox": "inbox-id", "needs_review": "nr"}
        drive.list_folder.return_value = []

        providers = Providers(
            gmail=MagicMock(),
            drive=drive,
            sheets=MagicMock(),
            llm=MagicMock(),
            safety_agent=MagicMock(summary=MagicMock(return_value={})),
            folder_ids={"inbox": "inbox-id", "needs_review": "nr"},
            bill_intake_providers=[],  # no bill_intake providers
        )

        with patch("postmule.pipeline._build_providers", return_value=providers):
            stats = run_daily_pipeline(cfg, {}, tmp_path, dry_run=True)

        # Pipeline should complete cleanly
        assert stats["status"] == "success"
