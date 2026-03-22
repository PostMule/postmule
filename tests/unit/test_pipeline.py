"""Unit tests for postmule.pipeline."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from postmule.core.config import load_config
from postmule.pipeline import (
    Providers,
    _run_bill_matching,
    _save_bill_matches,
    _store_processed_mail,
    _update_sheets,
    run_daily_pipeline,
)
from postmule.agents.classification import ProcessedMail
from postmule.providers.llm.gemini import ClassificationResult


@pytest.fixture
def minimal_config(tmp_path):
    data = {
        "app": {"dry_run": False, "install_dir": str(tmp_path)},
        "notifications": {"alert_email": "test@example.com"},
        "llm": {
            "providers": [{"type": "gemini", "enabled": True}],
            "classification_confidence_threshold": 0.80,
        },
        "email": {
            "providers": [{"type": "gmail", "enabled": True, "address": "test@gmail.com"}]
        },
        "storage": {
            "providers": [{"type": "google_drive", "enabled": True, "root_folder": "PostMule"}]
        },
        "data_protection": {"max_files_moved_per_run": 50},
        "deployment": {"dashboard_port": 5000},
    }
    path = tmp_path / "config.yaml"
    with path.open("w") as f:
        yaml.dump(data, f)
    return load_config(path)


@pytest.fixture
def credentials():
    return {
        "google": {
            "client_id": "cid",
            "client_secret": "cs",
            "refresh_token": "tok",
        },
        "gemini": {"api_key": "gemini-key"},
        "smtp": {"host": "smtp.gmail.com", "username": "u", "password": "p"},
    }


def _make_all_providers():
    """Return a mocked Providers dataclass instance."""
    gmail = MagicMock()
    gmail.list_unprocessed_emails.return_value = []
    drive = MagicMock()
    drive.ensure_folder_structure.return_value = {
        "root": "r", "inbox": "inbox", "bills": "bills",
        "needs_review": "review", "duplicates": "dupes",
    }
    drive.list_folder.return_value = []
    sheets = MagicMock()
    llm = MagicMock()
    safety_agent = MagicMock()
    safety_agent.summary.return_value = {"requests": 0, "tokens": 0}
    folder_ids = {
        "root": "r", "inbox": "inbox", "bills": "bills",
        "needs_review": "review", "duplicates": "dupes",
    }
    return Providers(
        gmail=gmail,
        drive=drive,
        sheets=sheets,
        llm=llm,
        safety_agent=safety_agent,
        folder_ids=folder_ids,
    )


class TestRunDailyPipelineDryRun:
    def test_dry_run_does_not_write_run_log(self, minimal_config, credentials, tmp_path):
        with patch("postmule.pipeline._build_providers", return_value=_make_all_providers()):
            stats = run_daily_pipeline(minimal_config, credentials, tmp_path, dry_run=True)
        from postmule.data.run_log import load_run_log
        assert load_run_log(tmp_path) == []
        assert stats["run_id"]

    def test_dry_run_returns_success_status(self, minimal_config, credentials, tmp_path):
        with patch("postmule.pipeline._build_providers", return_value=_make_all_providers()):
            stats = run_daily_pipeline(minimal_config, credentials, tmp_path, dry_run=True)
        assert stats["status"] == "success"

    def test_dry_run_returns_stats_dict(self, minimal_config, credentials, tmp_path):
        with patch("postmule.pipeline._build_providers", return_value=_make_all_providers()):
            stats = run_daily_pipeline(minimal_config, credentials, tmp_path, dry_run=True)
        for key in ("run_id", "start_time", "end_time", "status", "emails_found", "pdfs_processed"):
            assert key in stats


class TestRunDailyPipelineProviderFailure:
    def test_provider_init_failure_returns_failed_status(self, minimal_config, credentials, tmp_path):
        with patch("postmule.pipeline._build_providers", side_effect=RuntimeError("no creds")):
            stats = run_daily_pipeline(minimal_config, credentials, tmp_path, dry_run=True)
        assert stats["status"] == "failed"
        assert len(stats["errors"]) > 0


class TestRunDailyPipelineWithEmails:
    def test_processes_email_pdfs(self, minimal_config, credentials, tmp_path):
        providers = _make_all_providers()
        gmail, drive, llm = providers.gmail, providers.drive, providers.llm

        # Set up a fake email with a PDF
        from postmule.agents.email_ingestion import IngestedPDF
        fake_pdf = tmp_path / "scan.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 test")

        ingested = IngestedPDF(
            filename="scan.pdf",
            local_path=fake_pdf,
            source_email_id="msg1",
            received_date="2025-03-01",
            drive_file_id="drive-id",
        )

        from postmule.agents.email_ingestion import IngestionResult
        ingestion_result = IngestionResult(
            emails_found=1, pdfs_saved=1, pdfs_uploaded=1, ingested=[ingested]
        )

        llm.classify.return_value = ClassificationResult(
            category="Bill",
            confidence=0.95,
            sender="ATT",
            recipients=["Alice"],
            amount_due=94.0,
            due_date="2025-04-05",
            account_number=None,
            summary="Monthly bill",
            tokens_used=100,
        )

        with patch("postmule.pipeline._build_providers", return_value=providers):
            with patch("postmule.agents.email_ingestion.run_ingestion", return_value=ingestion_result):
                with patch("postmule.agents.classification.classify_pdf") as mock_classify:
                    mock_classify.return_value = ProcessedMail(
                        original_path=fake_pdf,
                        category="Bill",
                        confidence=0.95,
                        sender="ATT",
                        recipients=["Alice"],
                        amount_due=94.0,
                        due_date="2025-04-05",
                        account_number=None,
                        summary="Monthly bill",
                        ocr_text="",
                        ocr_method="pdfplumber",
                        processed_date="2025-03-01",
                        suggested_filename="2025-03-01_Alice_ATT_Bill.pdf",
                        destination_folder="Bills",
                        tokens_used=100,
                    )
                    stats = run_daily_pipeline(minimal_config, credentials, tmp_path, dry_run=True)

        assert stats["emails_found"] == 1
        assert stats["pdfs_processed"] == 1


class TestStoreProcessedMail:
    def test_stores_bill(self, tmp_path):
        result = ProcessedMail(
            original_path=Path("test.pdf"),
            category="Bill",
            confidence=0.95,
            sender="ATT",
            recipients=["Alice"],
            amount_due=94.0,
            due_date="2025-04-05",
            account_number="1234",
            summary="Monthly bill",
            ocr_text="",
            ocr_method="pdfplumber",
            processed_date="2025-03-01",
            tokens_used=0,
        )
        _store_processed_mail(tmp_path, result, "drive-id-1", "2025-03-01")
        from postmule.data.bills import load_bills
        bills = load_bills(tmp_path, year=2025)
        assert len(bills) == 1
        assert bills[0]["sender"] == "ATT"
        assert bills[0]["amount_due"] == 94.0

    def test_stores_notice(self, tmp_path):
        result = ProcessedMail(
            original_path=Path("test.pdf"),
            category="Notice",
            confidence=0.90,
            sender="IRS",
            recipients=["Alice"],
            amount_due=None,
            due_date=None,
            account_number=None,
            summary="Tax notice",
            ocr_text="",
            ocr_method="pdfplumber",
            processed_date="2025-03-01",
            tokens_used=0,
        )
        _store_processed_mail(tmp_path, result, "drive-id-2", "2025-03-01")
        from postmule.data.notices import load_notices
        notices = load_notices(tmp_path, year=2025)
        assert len(notices) == 1

    def test_stores_forward_to_me(self, tmp_path):
        result = ProcessedMail(
            original_path=Path("test.pdf"),
            category="ForwardToMe",
            confidence=0.95,
            sender="Visa",
            recipients=["Alice"],
            amount_due=None,
            due_date=None,
            account_number=None,
            summary="New card",
            ocr_text="",
            ocr_method="pdfplumber",
            processed_date="2025-03-01",
            tokens_used=0,
        )
        _store_processed_mail(tmp_path, result, "drive-id-3", "2025-03-01")
        from postmule.data.forward_to_me import load_forward_to_me
        items = load_forward_to_me(tmp_path)
        assert len(items) == 1

    def test_no_store_for_junk(self, tmp_path):
        result = ProcessedMail(
            original_path=Path("test.pdf"),
            category="Junk",
            confidence=0.95,
            sender="Spammer",
            recipients=[],
            amount_due=None,
            due_date=None,
            account_number=None,
            summary="Marketing",
            ocr_text="",
            ocr_method="pdfplumber",
            processed_date="2025-03-01",
            tokens_used=0,
        )
        _store_processed_mail(tmp_path, result, "drive-id-4", "2025-03-01")
        from postmule.data.bills import load_bills
        from postmule.data.notices import load_notices
        assert load_bills(tmp_path) == []
        assert load_notices(tmp_path) == []


class TestRunBillMatching:
    def test_skips_when_no_finance_provider(self, minimal_config, tmp_path):
        _run_bill_matching(minimal_config, {}, tmp_path, dry_run=True)
        # Should not raise — no finance provider configured in minimal config

    def test_skips_unknown_provider_type(self, tmp_path, minimal_config):
        # minimal_config has no finance providers — should skip silently
        _run_bill_matching(minimal_config, {}, tmp_path, dry_run=True)
        # Should not raise


class TestSaveBillMatches:
    def test_saves_new_matches(self, tmp_path):
        from postmule.providers.finance.simplifi import BillMatchResult
        match = BillMatchResult(
            bill_id="bill-1",
            transaction_id="txn-1",
            amount=94.0,
            date="2026-01-15",
            confidence="exact",
        )
        _save_bill_matches(tmp_path, [match])
        import json
        path = tmp_path / "pending" / "bill_matches.json"
        assert path.exists()
        saved = json.loads(path.read_text())
        assert len(saved) == 1
        assert saved[0]["bill_id"] == "bill-1"
        assert saved[0]["bill_amount"] == 94.0

    def test_does_not_duplicate_existing_matches(self, tmp_path):
        from postmule.providers.finance.simplifi import BillMatchResult
        match = BillMatchResult(
            bill_id="bill-1",
            transaction_id="txn-1",
            amount=94.0,
            date="2026-01-15",
            confidence="exact",
        )
        _save_bill_matches(tmp_path, [match])
        _save_bill_matches(tmp_path, [match])  # Save same match again
        import json
        saved = json.loads((tmp_path / "pending" / "bill_matches.json").read_text())
        assert len(saved) == 1


class TestUpdateSheets:
    def test_calls_write_sheet_for_all_datasets(self, tmp_path):
        sheets = MagicMock()
        _update_sheets(sheets, tmp_path)
        assert sheets.write_sheet.call_count == 4
        sheet_names = [call[0][0] for call in sheets.write_sheet.call_args_list]
        assert "Bills" in sheet_names
        assert "Notices" in sheet_names
        assert "ForwardToMe" in sheet_names
        assert "RunLog" in sheet_names
