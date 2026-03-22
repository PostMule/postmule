"""Unit tests for postmule.agents.retroactive."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from postmule.agents.retroactive import run_retroactive, _store_record
from postmule.agents.classification import ProcessedMail
from postmule.providers.llm.gemini import ClassificationResult


def _make_pdf(tmp_path, name="scan.pdf"):
    p = tmp_path / name
    p.write_bytes(b"%PDF-1.4 test")
    return p


def _make_llm(category="Bill", confidence=0.95):
    llm = MagicMock()
    llm.classify.return_value = ClassificationResult(
        category=category,
        confidence=confidence,
        sender="ATT",
        recipients=["Alice"],
        amount_due=94.0,
        due_date="2025-04-05",
        account_number="1234",
        summary="Monthly bill",
        tokens_used=200,
    )
    return llm


def _make_drive():
    drive = MagicMock()
    drive.upload_pdf.return_value = "drive-id-1"
    return drive


class TestRunRetroactiveDryRun:
    def test_dry_run_does_not_upload(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        drive = _make_drive()
        result = run_retroactive(
            pdf_paths=[pdf],
            llm=_make_llm(),
            drive=drive,
            folder_ids={"bills": "bills-folder", "needs_review": "review-folder"},
            data_dir=tmp_path,
            rate_limit_seconds=0.0,
            dry_run=True,
        )
        drive.upload_pdf.assert_not_called()
        assert result["processed"] == 1

    def test_dry_run_returns_correct_counts(self, tmp_path):
        pdfs = [_make_pdf(tmp_path, f"scan_{i}.pdf") for i in range(3)]
        result = run_retroactive(
            pdf_paths=pdfs,
            llm=_make_llm(category="Bill"),
            drive=_make_drive(),
            folder_ids={"bills": "bills-folder", "needs_review": "review-folder"},
            data_dir=tmp_path,
            rate_limit_seconds=0.0,
            dry_run=True,
        )
        assert result["processed"] == 3


class TestRunRetroactiveMaxFiles:
    def test_respects_max_files_cap(self, tmp_path):
        pdfs = [_make_pdf(tmp_path, f"scan_{i}.pdf") for i in range(5)]
        result = run_retroactive(
            pdf_paths=pdfs,
            llm=_make_llm(),
            drive=_make_drive(),
            folder_ids={"bills": "b", "needs_review": "r"},
            data_dir=tmp_path,
            rate_limit_seconds=0.0,
            max_files=3,
            dry_run=True,
        )
        assert result["processed"] == 3


class TestRunRetroactiveErrors:
    def test_classification_error_recorded_not_raised(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        llm = MagicMock()
        llm.classify.side_effect = RuntimeError("LLM error")
        result = run_retroactive(
            pdf_paths=[pdf],
            llm=llm,
            drive=_make_drive(),
            folder_ids={"bills": "b", "needs_review": "r"},
            data_dir=tmp_path,
            rate_limit_seconds=0.0,
            dry_run=True,
        )
        assert result["processed"] == 0
        assert len(result["errors"]) == 1
        assert "LLM error" in result["errors"][0]


class TestRunRetroactiveCategories:
    def test_counts_categories(self, tmp_path):
        pdfs = [
            _make_pdf(tmp_path, "scan_0.pdf"),
            _make_pdf(tmp_path, "scan_1.pdf"),
        ]
        llm = MagicMock()
        # First returns Bill, second returns Notice
        llm.classify.side_effect = [
            ClassificationResult("Bill", 0.95, "ATT", ["Alice"], 94.0, "2025-04-05", None, "bill", 100),
            ClassificationResult("Notice", 0.92, "IRS", ["Alice"], None, None, None, "notice", 100),
        ]
        result = run_retroactive(
            pdf_paths=pdfs,
            llm=llm,
            drive=_make_drive(),
            folder_ids={"bills": "b", "notices": "n", "needs_review": "r"},
            data_dir=tmp_path,
            rate_limit_seconds=0.0,
            dry_run=True,
        )
        assert result["counts"]["Bill"] == 1
        assert result["counts"]["Notice"] == 1


class TestStoreRecord:
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
        _store_record(tmp_path, result, "drive-id-1")
        from postmule.data.bills import load_bills
        bills = load_bills(tmp_path, year=2025)
        assert len(bills) == 1
        assert bills[0]["sender"] == "ATT"

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
        _store_record(tmp_path, result, "drive-id-2")
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
        _store_record(tmp_path, result, "drive-id-3")
        from postmule.data.forward_to_me import load_forward_to_me
        items = load_forward_to_me(tmp_path)
        assert len(items) == 1
