"""Unit tests for postmule.agents.classification."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from postmule.agents.classification import (
    CATEGORY_FOLDERS,
    ProcessedMail,
    _build_filename,
    _slugify,
    classify_pdf,
)
from postmule.providers.llm.base import ClassificationResult


def _mock_llm(category="Bill", confidence=0.95, sender="ATT", recipients=None,
              amount_due=94.0, due_date="2025-04-05"):
    llm = MagicMock()
    llm.classify.return_value = ClassificationResult(
        category=category,
        confidence=confidence,
        sender=sender,
        recipients=recipients or ["Alice"],
        amount_due=amount_due,
        due_date=due_date,
        account_number="1234",
        summary="Monthly bill",
        tokens_used=500,
    )
    return llm


class TestClassifyPdf:
    def test_dry_run_skips_ocr(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 empty")
        llm = _mock_llm()
        with patch("postmule.agents.classification.extract_text") as mock_ocr:
            classify_pdf(pdf, llm, dry_run=True)
        mock_ocr.assert_not_called()

    def test_high_confidence_keeps_llm_category(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 empty")
        llm = _mock_llm(category="Notice", confidence=0.95)
        result = classify_pdf(pdf, llm, confidence_threshold=0.80, dry_run=True)
        assert result.category == "Notice"

    def test_low_confidence_becomes_needs_review(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 empty")
        llm = _mock_llm(category="Bill", confidence=0.50)
        result = classify_pdf(pdf, llm, confidence_threshold=0.80, dry_run=True)
        assert result.category == "NeedsReview"

    def test_destination_folder_maps_bill_to_bills(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 empty")
        llm = _mock_llm(category="Bill", confidence=0.95)
        result = classify_pdf(pdf, llm, confidence_threshold=0.80, dry_run=True)
        assert result.destination_folder == "Bills"

    def test_destination_folder_set_for_all_categories(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 empty")
        for category, folder in CATEGORY_FOLDERS.items():
            llm = _mock_llm(category=category, confidence=0.99)
            result = classify_pdf(pdf, llm, confidence_threshold=0.80, dry_run=True)
            assert result.destination_folder == folder

    def test_suggested_filename_has_pdf_extension(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 empty")
        llm = _mock_llm()
        result = classify_pdf(pdf, llm, dry_run=True)
        assert result.suggested_filename.endswith(".pdf")

    def test_tokens_used_passed_through(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 empty")
        llm = _mock_llm(confidence=0.95)
        llm.classify.return_value.tokens_used = 1234
        result = classify_pdf(pdf, llm, dry_run=True)
        assert result.tokens_used == 1234


def _make_mail(**kwargs) -> ProcessedMail:
    defaults = dict(
        original_path=Path("test.pdf"),
        category="Bill",
        confidence=0.95,
        sender="ATT",
        recipients=["Alice"],
        amount_due=94.0,
        due_date="2025-04-05",
        account_number=None,
        summary="",
        ocr_text="",
        ocr_method="pdfplumber",
        processed_date="2025-03-01",
        tokens_used=0,
    )
    defaults.update(kwargs)
    return ProcessedMail(**defaults)


class TestBuildFilename:
    def test_format(self):
        mail = _make_mail()
        filename = _build_filename(mail)
        assert filename.startswith("2025-03-01_")
        assert "ATT" in filename
        assert filename.endswith(".pdf")

    def test_multiple_recipients_joined(self):
        mail = _make_mail(recipients=["Alice", "Bob"])
        filename = _build_filename(mail)
        assert "Alice" in filename
        assert "Bob" in filename

    def test_none_sender_fallback(self):
        mail = _make_mail(sender=None)
        filename = _build_filename(mail)
        assert "Unknown" in filename

    def test_empty_recipients_fallback(self):
        mail = _make_mail(recipients=[])
        filename = _build_filename(mail)
        assert "Unknown" in filename

    def test_long_sender_truncated(self):
        mail = _make_mail(sender="A" * 50)
        filename = _build_filename(mail)
        parts = filename.replace(".pdf", "").split("_")
        sender_part = parts[2]
        assert len(sender_part) <= 30


class TestOwnerResolutionInClassify:
    def _owners(self):
        return [
            {"id": "uuid-alice", "name": "Alice", "short_name": None, "active": True},
            {"id": "uuid-bob", "name": "Bob", "short_name": None, "active": True},
        ]

    def test_owner_ids_empty_when_no_owners_passed(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 empty")
        llm = _mock_llm(recipients=["Alice"])
        result = classify_pdf(pdf, llm, dry_run=True)
        assert result.owner_ids == []

    def test_owner_ids_resolved_from_recipients(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 empty")
        llm = _mock_llm(recipients=["Alice"])
        result = classify_pdf(pdf, llm, dry_run=True, owners=self._owners())
        assert result.owner_ids == ["uuid-alice"]

    def test_multiple_recipients_resolved(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 empty")
        llm = _mock_llm(recipients=["Alice", "Bob"])
        result = classify_pdf(pdf, llm, dry_run=True, owners=self._owners())
        assert set(result.owner_ids) == {"uuid-alice", "uuid-bob"}

    def test_unmatched_recipient_gives_empty(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 empty")
        llm = _mock_llm(recipients=["Unknown Person"])
        result = classify_pdf(pdf, llm, dry_run=True, owners=self._owners())
        assert result.owner_ids == []

    def test_owner_ids_default_is_empty_list(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 empty")
        llm = _mock_llm()
        result = classify_pdf(pdf, llm, dry_run=True)
        assert isinstance(result.owner_ids, list)


class TestSlugify:
    def test_special_characters_stripped(self):
        result = _slugify("AT&T Mobility")
        assert "/" not in result
        assert "&" not in result

    def test_spaces_become_hyphens(self):
        assert _slugify("hello world") == "hello-world"

    def test_leading_trailing_whitespace_trimmed(self):
        assert _slugify("  trimmed  ") == "trimmed"
