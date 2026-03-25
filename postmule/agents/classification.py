"""
Classification agent — orchestrates OCR + LLM classification for a single PDF.

This is the core per-document processing step.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from postmule.agents.ocr import extract_text
from postmule.providers.llm.base import ClassificationResult, LLMProvider

log = logging.getLogger("postmule.classification")


@dataclass
class ProcessedMail:
    """All extracted data for a single mail item, ready to be stored and filed."""
    # Original file
    original_path: Path
    # Classification
    category: str            # Bill | Notice | ForwardToMe | Personal | Junk | NeedsReview
    confidence: float
    # Extracted data
    sender: str | None
    recipients: list[str]
    amount_due: float | None
    due_date: str | None
    account_number: str | None
    summary: str
    # Processing metadata
    ocr_text: str
    ocr_method: str          # "pdfplumber" | "tesseract" | "none"
    processed_date: str      # YYYY-MM-DD
    tokens_used: int
    # Computed after classification
    suggested_filename: str = ""
    destination_folder: str = ""
    statement_date: str | None = None
    ach_descriptor: str | None = None


CATEGORY_FOLDERS = {
    "Bill": "Bills",
    "Notice": "Notices",
    "ForwardToMe": "ForwardToMe",
    "Personal": "Personal",
    "Junk": "Junk",
    "NeedsReview": "NeedsReview",
}


def classify_pdf(
    pdf_path: Path,
    llm: LLMProvider,
    known_names: list[str] | None = None,
    confidence_threshold: float = 0.80,
    dry_run: bool = False,
) -> ProcessedMail:
    """
    Run the full classify pipeline on a single PDF:
      1. OCR text extraction
      2. LLM classification
      3. Build ProcessedMail result

    Args:
        pdf_path:             Path to the PDF file.
        llm:                  Any LLMProvider implementation.
        known_names:          Known entity names for LLM context.
        confidence_threshold: Below this confidence, category becomes NeedsReview.
        dry_run:              Skip API calls; return placeholder result.

    Returns:
        ProcessedMail with all extracted data and suggested filename/folder.
    """
    log.info(f"Classifying: {pdf_path.name}")

    # Step 1: OCR
    ocr_text = extract_text(pdf_path) if not dry_run else "[dry-run]"
    ocr_method = _detect_ocr_method(pdf_path, ocr_text, dry_run)

    # Step 2: LLM classification
    result: ClassificationResult = llm.classify(
        ocr_text=ocr_text,
        known_names=known_names,
        dry_run=dry_run,
    )

    # Downgrade to NeedsReview if confidence is below threshold
    category = result.category
    if result.confidence < confidence_threshold and category != "NeedsReview":
        log.info(
            f"{pdf_path.name}: confidence {result.confidence:.2f} < threshold {confidence_threshold} "
            f"— changing {category} to NeedsReview"
        )
        category = "NeedsReview"

    processed = ProcessedMail(
        original_path=pdf_path,
        category=category,
        confidence=result.confidence,
        sender=result.sender,
        recipients=result.recipients,
        amount_due=result.amount_due,
        due_date=result.due_date,
        account_number=result.account_number,
        statement_date=result.statement_date,
        ach_descriptor=result.ach_descriptor,
        summary=result.summary,
        ocr_text=ocr_text,
        ocr_method=ocr_method,
        processed_date=date.today().isoformat(),
        tokens_used=result.tokens_used,
    )

    processed.suggested_filename = _build_filename(processed)
    processed.destination_folder = CATEGORY_FOLDERS.get(category, "NeedsReview")

    log.info(
        f"{pdf_path.name} -> {category} "
        f"(confidence={result.confidence:.2f}, sender={result.sender})"
    )
    return processed


def _detect_ocr_method(pdf_path: Path, text: str, dry_run: bool) -> str:
    if dry_run:
        return "none"
    if not text or len(text.strip()) < 50:
        return "none"
    # We can't easily tell after the fact which method succeeded,
    # so we re-check pdfplumber cheaply
    try:
        import pdfplumber  # type: ignore[import]
        with pdfplumber.open(str(pdf_path)) as pdf:
            sample = (pdf.pages[0].extract_text() or "") if pdf.pages else ""
        return "pdfplumber" if len(sample.strip()) >= 50 else "tesseract"
    except Exception:
        return "tesseract"


def _build_filename(mail: ProcessedMail) -> str:
    """
    Build the canonical filename for a mail item.
    Pattern: {date}_{recipients}_{sender}_{category}.pdf
    Example: 2025-11-15_Alice_ATT_Bill.pdf
    """
    parts = [mail.processed_date]

    recipients_str = _slugify(", ".join(mail.recipients)) if mail.recipients else "Unknown"
    parts.append(recipients_str[:30])

    sender_str = _slugify(mail.sender) if mail.sender else "Unknown"
    parts.append(sender_str[:30])

    parts.append(mail.category)

    return "_".join(parts) + ".pdf"


def _slugify(text: str) -> str:
    """Convert a string to a safe filename component."""
    import re
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text
