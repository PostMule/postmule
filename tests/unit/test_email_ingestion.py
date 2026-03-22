"""Unit tests for postmule.agents.email_ingestion."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from postmule.agents.email_ingestion import (
    IngestionResult,
    IngestedPDF,
    _sanitize_filename,
    run_ingestion,
)


def _make_email(message_id="msg1", received_date="2025-03-01", attachments=None):
    email = MagicMock()
    email.message_id = message_id
    email.received_date = received_date
    email.attachments = attachments or [{"name": "scan.pdf", "data": b"%PDF fake"}]
    return email


def _make_gmail(emails=None):
    gmail = MagicMock()
    gmail.list_unprocessed_emails.return_value = emails if emails is not None else []
    return gmail


def _make_drive(upload_id="drive-id-1"):
    drive = MagicMock()
    drive.upload_pdf.return_value = upload_id
    return drive


class TestRunIngestionNoEmails:
    def test_returns_zero_counts_when_no_emails(self, tmp_path):
        result = run_ingestion(
            gmail=_make_gmail([]),
            drive=_make_drive(),
            inbox_folder_id="folder-1",
            download_dir=tmp_path,
        )
        assert result.emails_found == 0
        assert result.pdfs_saved == 0
        assert result.pdfs_uploaded == 0

    def test_does_not_call_drive_when_no_emails(self, tmp_path):
        drive = _make_drive()
        run_ingestion(
            gmail=_make_gmail([]),
            drive=drive,
            inbox_folder_id="folder-1",
            download_dir=tmp_path,
        )
        drive.upload_pdf.assert_not_called()


class TestRunIngestionWithEmails:
    def test_saves_and_uploads_pdf(self, tmp_path):
        email = _make_email()
        result = run_ingestion(
            gmail=_make_gmail([email]),
            drive=_make_drive(),
            inbox_folder_id="folder-1",
            download_dir=tmp_path,
        )
        assert result.emails_found == 1
        assert result.pdfs_saved == 1
        assert result.pdfs_uploaded == 1
        assert len(result.ingested) == 1

    def test_ingested_item_has_drive_id(self, tmp_path):
        email = _make_email()
        result = run_ingestion(
            gmail=_make_gmail([email]),
            drive=_make_drive("my-drive-id"),
            inbox_folder_id="folder-1",
            download_dir=tmp_path,
        )
        assert result.ingested[0].drive_file_id == "my-drive-id"

    def test_marks_email_as_processed(self, tmp_path):
        email = _make_email(message_id="msg-abc")
        gmail = _make_gmail([email])
        run_ingestion(
            gmail=gmail,
            drive=_make_drive(),
            inbox_folder_id="folder-1",
            download_dir=tmp_path,
        )
        gmail.mark_as_processed.assert_called_once_with("msg-abc")

    def test_multiple_attachments(self, tmp_path):
        email = _make_email(attachments=[
            {"name": "scan1.pdf", "data": b"%PDF 1"},
            {"name": "scan2.pdf", "data": b"%PDF 2"},
        ])
        result = run_ingestion(
            gmail=_make_gmail([email]),
            drive=_make_drive(),
            inbox_folder_id="folder-1",
            download_dir=tmp_path,
        )
        assert result.pdfs_saved == 2
        assert result.pdfs_uploaded == 2


class TestRunIngestionDryRun:
    def test_dry_run_does_not_upload(self, tmp_path):
        email = _make_email()
        drive = _make_drive()
        result = run_ingestion(
            gmail=_make_gmail([email]),
            drive=drive,
            inbox_folder_id="folder-1",
            download_dir=tmp_path,
            dry_run=True,
        )
        drive.upload_pdf.assert_not_called()
        assert result.pdfs_uploaded == 1  # counted but not actually uploaded

    def test_dry_run_does_not_mark_processed(self, tmp_path):
        email = _make_email()
        gmail = _make_gmail([email])
        run_ingestion(
            gmail=gmail,
            drive=_make_drive(),
            inbox_folder_id="folder-1",
            download_dir=tmp_path,
            dry_run=True,
        )
        gmail.mark_as_processed.assert_not_called()


class TestRunIngestionErrors:
    def test_drive_error_recorded_not_raised(self, tmp_path):
        email = _make_email()
        drive = _make_drive()
        drive.upload_pdf.side_effect = RuntimeError("Drive offline")
        result = run_ingestion(
            gmail=_make_gmail([email]),
            drive=drive,
            inbox_folder_id="folder-1",
            download_dir=tmp_path,
        )
        assert len(result.errors) == 1
        assert "Drive offline" in result.errors[0]

    def test_mark_as_processed_failure_does_not_crash(self, tmp_path):
        email = _make_email()
        gmail = _make_gmail([email])
        gmail.mark_as_processed.side_effect = Exception("Label error")
        result = run_ingestion(
            gmail=gmail,
            drive=_make_drive(),
            inbox_folder_id="folder-1",
            download_dir=tmp_path,
        )
        # Should complete without raising
        assert result.emails_found == 1

    def test_creates_download_dir_if_missing(self, tmp_path):
        new_dir = tmp_path / "new" / "subdir"
        run_ingestion(
            gmail=_make_gmail([]),
            drive=_make_drive(),
            inbox_folder_id="folder-1",
            download_dir=new_dir,
        )
        assert new_dir.exists()


class TestSanitizeFilename:
    def test_adds_pdf_extension(self):
        result = _sanitize_filename("scan_001", "2025-03-01")
        assert result.endswith(".pdf")

    def test_preserves_existing_pdf_extension(self):
        result = _sanitize_filename("scan_001.pdf", "2025-03-01")
        assert result.endswith(".pdf")
        assert result.count(".pdf") == 1

    def test_prepends_date(self):
        result = _sanitize_filename("scan.pdf", "2025-03-01")
        assert result.startswith("2025-03-01_")

    def test_does_not_double_prefix(self):
        result = _sanitize_filename("2025-03-01_scan.pdf", "2025-03-01")
        assert result.count("2025-03-01") == 1

    def test_removes_special_chars(self):
        result = _sanitize_filename("scan (copy).pdf", "2025-03-01")
        assert "(" not in result
        assert " " not in result
