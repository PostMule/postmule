"""
OCR pipeline — extracts text from PDF files.

Strategy:
  1. pdfplumber — fast, lossless text extraction from PDFs with a text layer.
  2. pytesseract — image-based OCR fallback for scanned (image-only) PDFs.

Returns the extracted text string. Empty string means no text could be extracted.
"""

from __future__ import annotations

import io
import logging
import tempfile
from pathlib import Path

log = logging.getLogger("postmule.ocr")

# Minimum characters from pdfplumber before we consider it "has text"
_MIN_TEXT_LENGTH = 50


def extract_text(
    pdf_path: Path,
    tesseract_dpi: int = 300,
    tesseract_lang: str = "eng",
) -> str:
    """
    Extract text from a PDF, trying pdfplumber first then pytesseract.

    Args:
        pdf_path:       Path to the PDF file.
        tesseract_dpi:  DPI for image rendering before OCR (higher = better quality).
        tesseract_lang: Tesseract language code.

    Returns:
        Extracted text string. May be empty if extraction fails completely.
    """
    if not pdf_path.exists():
        log.error(f"PDF not found: {pdf_path}")
        return ""

    # --- Try pdfplumber first ---
    text = _extract_with_pdfplumber(pdf_path)
    if len(text.strip()) >= _MIN_TEXT_LENGTH:
        log.debug(f"pdfplumber extracted {len(text)} chars from {pdf_path.name}")
        return text

    log.debug(
        f"pdfplumber got only {len(text.strip())} chars from {pdf_path.name} "
        f"(threshold={_MIN_TEXT_LENGTH}) — trying tesseract"
    )

    # --- Fallback: pytesseract ---
    text = _extract_with_tesseract(pdf_path, tesseract_dpi, tesseract_lang)
    if text:
        log.debug(f"tesseract extracted {len(text)} chars from {pdf_path.name}")
    else:
        log.warning(
            f"OCR failed for {pdf_path.name} — no text extracted by either method.\n"
            "The PDF may be blank, corrupted, or contain only images with no text.\n"
            "It will be filed as NeedsReview."
        )
    return text


def _extract_with_pdfplumber(pdf_path: Path) -> str:
    try:
        import pdfplumber  # type: ignore[import]
    except ImportError:
        log.warning("pdfplumber not installed — skipping text-layer extraction")
        return ""

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            pages = []
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                pages.append(page_text)
            return "\n\n".join(pages)
    except Exception as exc:
        log.debug(f"pdfplumber error on {pdf_path.name}: {exc}")
        return ""


def _extract_with_tesseract(pdf_path: Path, dpi: int, lang: str) -> str:
    try:
        import pytesseract  # type: ignore[import]
        from pdf2image import convert_from_path  # type: ignore[import]
    except ImportError:
        log.warning(
            "pytesseract or pdf2image not installed — cannot perform image OCR.\n"
            "Install with: pip install pytesseract pdf2image\n"
            "Also install Tesseract OCR from https://github.com/UB-Mannheim/tesseract/wiki"
        )
        return ""

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            images = convert_from_path(str(pdf_path), dpi=dpi, output_folder=tmpdir)
            pages = []
            for img in images:
                page_text = pytesseract.image_to_string(img, lang=lang)
                pages.append(page_text)
            return "\n\n".join(pages)
    except Exception as exc:
        log.debug(f"tesseract error on {pdf_path.name}: {exc}")
        return ""
