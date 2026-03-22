"""
Unit tests for postmule/agents/ocr.py

Covers: extract_text, _extract_with_pdfplumber, _extract_with_tesseract
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from postmule.agents.ocr import (
    _MIN_TEXT_LENGTH,
    _extract_with_pdfplumber,
    _extract_with_tesseract,
    extract_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pdf(tmp_path: Path, name: str = "test.pdf") -> Path:
    """Create a minimal valid-looking PDF file for path-exists checks."""
    p = tmp_path / name
    p.write_bytes(b"%PDF-1.4 fake content")
    return p


def _long_text(length: int = _MIN_TEXT_LENGTH + 1) -> str:
    return "A" * length


# ---------------------------------------------------------------------------
# extract_text — file not found
# ---------------------------------------------------------------------------

class TestExtractTextFileNotFound:
    def test_returns_empty_string_when_pdf_missing(self, tmp_path):
        missing = tmp_path / "nonexistent.pdf"
        result = extract_text(missing)
        assert result == ""

    def test_logs_error_when_pdf_missing(self, tmp_path, caplog):
        import logging
        missing = tmp_path / "ghost.pdf"
        with caplog.at_level(logging.ERROR, logger="postmule.ocr"):
            extract_text(missing)
        assert "ghost.pdf" in caplog.text


# ---------------------------------------------------------------------------
# extract_text — pdfplumber path
# ---------------------------------------------------------------------------

class TestExtractTextPdfplumberSufficient:
    def test_returns_pdfplumber_text_when_long_enough(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        long_text = _long_text()

        with patch("postmule.agents.ocr._extract_with_pdfplumber", return_value=long_text) as mock_plumb, \
             patch("postmule.agents.ocr._extract_with_tesseract") as mock_tess:
            result = extract_text(pdf)

        assert result == long_text
        mock_plumb.assert_called_once_with(pdf)
        mock_tess.assert_not_called()

    def test_pdfplumber_text_exactly_at_threshold_is_sufficient(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        threshold_text = "A" * _MIN_TEXT_LENGTH  # exactly equal

        with patch("postmule.agents.ocr._extract_with_pdfplumber", return_value=threshold_text), \
             patch("postmule.agents.ocr._extract_with_tesseract") as mock_tess:
            extract_text(pdf)

        mock_tess.assert_not_called()


class TestExtractTextFallsBackToTesseract:
    def test_uses_tesseract_when_pdfplumber_short(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        short_text = "short"
        tesseract_text = _long_text(100)

        with patch("postmule.agents.ocr._extract_with_pdfplumber", return_value=short_text), \
             patch("postmule.agents.ocr._extract_with_tesseract", return_value=tesseract_text) as mock_tess:
            result = extract_text(pdf)

        assert result == tesseract_text
        mock_tess.assert_called_once_with(pdf, 300, "eng")

    def test_uses_tesseract_when_pdfplumber_returns_empty(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        tesseract_text = _long_text()

        with patch("postmule.agents.ocr._extract_with_pdfplumber", return_value=""), \
             patch("postmule.agents.ocr._extract_with_tesseract", return_value=tesseract_text):
            result = extract_text(pdf)

        assert result == tesseract_text

    def test_passes_custom_dpi_and_lang_to_tesseract(self, tmp_path):
        pdf = _make_pdf(tmp_path)

        with patch("postmule.agents.ocr._extract_with_pdfplumber", return_value=""), \
             patch("postmule.agents.ocr._extract_with_tesseract", return_value="") as mock_tess:
            extract_text(pdf, tesseract_dpi=600, tesseract_lang="fra")

        mock_tess.assert_called_once_with(pdf, 600, "fra")

    def test_returns_empty_when_both_fail(self, tmp_path):
        pdf = _make_pdf(tmp_path)

        with patch("postmule.agents.ocr._extract_with_pdfplumber", return_value=""), \
             patch("postmule.agents.ocr._extract_with_tesseract", return_value=""):
            result = extract_text(pdf)

        assert result == ""

    def test_logs_warning_when_both_fail(self, tmp_path, caplog):
        import logging
        pdf = _make_pdf(tmp_path)

        with patch("postmule.agents.ocr._extract_with_pdfplumber", return_value=""), \
             patch("postmule.agents.ocr._extract_with_tesseract", return_value=""):
            with caplog.at_level(logging.WARNING, logger="postmule.ocr"):
                extract_text(pdf)

        assert "NeedsReview" in caplog.text or "no text extracted" in caplog.text.lower()


# ---------------------------------------------------------------------------
# _extract_with_pdfplumber
# ---------------------------------------------------------------------------

class TestExtractWithPdfplumber:
    def test_returns_empty_when_pdfplumber_not_installed(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        with patch.dict(sys.modules, {"pdfplumber": None}):
            result = _extract_with_pdfplumber(pdf)
        assert result == ""

    def test_returns_empty_on_pdfplumber_exception(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        mock_plumber = MagicMock()
        mock_plumber.open.side_effect = Exception("corrupt PDF")

        with patch.dict(sys.modules, {"pdfplumber": mock_plumber}):
            result = _extract_with_pdfplumber(pdf)

        assert result == ""

    def test_extracts_single_page_text(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Hello world"

        mock_pdf_obj = MagicMock()
        mock_pdf_obj.__enter__ = MagicMock(return_value=mock_pdf_obj)
        mock_pdf_obj.__exit__ = MagicMock(return_value=False)
        mock_pdf_obj.pages = [mock_page]

        mock_plumber = MagicMock()
        mock_plumber.open.return_value = mock_pdf_obj

        with patch.dict(sys.modules, {"pdfplumber": mock_plumber}):
            result = _extract_with_pdfplumber(pdf)

        assert result == "Hello world"

    def test_concatenates_multiple_pages_with_double_newline(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        page1 = MagicMock()
        page1.extract_text.return_value = "Page one"
        page2 = MagicMock()
        page2.extract_text.return_value = "Page two"

        mock_pdf_obj = MagicMock()
        mock_pdf_obj.__enter__ = MagicMock(return_value=mock_pdf_obj)
        mock_pdf_obj.__exit__ = MagicMock(return_value=False)
        mock_pdf_obj.pages = [page1, page2]

        mock_plumber = MagicMock()
        mock_plumber.open.return_value = mock_pdf_obj

        with patch.dict(sys.modules, {"pdfplumber": mock_plumber}):
            result = _extract_with_pdfplumber(pdf)

        assert result == "Page one\n\nPage two"

    def test_handles_none_page_text(self, tmp_path):
        """Pages that return None from extract_text should become empty string."""
        pdf = _make_pdf(tmp_path)
        page = MagicMock()
        page.extract_text.return_value = None

        mock_pdf_obj = MagicMock()
        mock_pdf_obj.__enter__ = MagicMock(return_value=mock_pdf_obj)
        mock_pdf_obj.__exit__ = MagicMock(return_value=False)
        mock_pdf_obj.pages = [page]

        mock_plumber = MagicMock()
        mock_plumber.open.return_value = mock_pdf_obj

        with patch.dict(sys.modules, {"pdfplumber": mock_plumber}):
            result = _extract_with_pdfplumber(pdf)

        assert result == ""


# ---------------------------------------------------------------------------
# _extract_with_tesseract
# ---------------------------------------------------------------------------

class TestExtractWithTesseract:
    def test_returns_empty_when_pytesseract_not_installed(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        with patch.dict(sys.modules, {"pytesseract": None, "pdf2image": None}):
            result = _extract_with_tesseract(pdf, 300, "eng")
        assert result == ""

    def test_returns_empty_when_pdf2image_not_installed(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        mock_pytesseract = MagicMock()
        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "pdf2image": None}):
            result = _extract_with_tesseract(pdf, 300, "eng")
        assert result == ""

    def test_returns_empty_on_tesseract_exception(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        mock_pytesseract = MagicMock()
        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.side_effect = Exception("tesseract error")

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "pdf2image": mock_pdf2image}):
            result = _extract_with_tesseract(pdf, 300, "eng")

        assert result == ""

    def test_extracts_single_image_page(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        mock_img = MagicMock()

        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_string.return_value = "OCR text here"

        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.return_value = [mock_img]

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "pdf2image": mock_pdf2image}):
            with patch("tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fake")
                mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
                result = _extract_with_tesseract(pdf, 300, "eng")

        assert result == "OCR text here"

    def test_concatenates_multiple_image_pages(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        mock_img1 = MagicMock()
        mock_img2 = MagicMock()

        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_string.side_effect = ["First page OCR", "Second page OCR"]

        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.return_value = [mock_img1, mock_img2]

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "pdf2image": mock_pdf2image}):
            with patch("tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fake")
                mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
                result = _extract_with_tesseract(pdf, 300, "eng")

        assert result == "First page OCR\n\nSecond page OCR"

    def test_passes_dpi_and_lang_correctly(self, tmp_path):
        pdf = _make_pdf(tmp_path)
        mock_img = MagicMock()

        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_string.return_value = "text"

        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.return_value = [mock_img]

        with patch.dict(sys.modules, {"pytesseract": mock_pytesseract, "pdf2image": mock_pdf2image}):
            with patch("tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__ = MagicMock(return_value="/tmp/fake")
                mock_tmpdir.return_value.__exit__ = MagicMock(return_value=False)
                _extract_with_tesseract(pdf, 600, "fra")

        call_kwargs = mock_pdf2image.convert_from_path.call_args
        assert call_kwargs.kwargs.get("dpi") == 600 or 600 in call_kwargs.args
        mock_pytesseract.image_to_string.assert_called_once_with(mock_img, lang="fra")
