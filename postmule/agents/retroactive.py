"""
Retroactive processing — runs all existing PDFs through the classification pipeline.

Used to:
  1. Process the 130 CONFLICT folder PDFs from before PostMule existed.
  2. Reprocess previously-sorted PDFs to populate the JSON/Sheets database.
  3. Fill in gaps found by the Gap Detector.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from postmule.agents.classification import classify_pdf, CATEGORY_FOLDERS
from postmule.data import bills as bills_data
from postmule.data import notices as notices_data
from postmule.data import forward_to_me as ftm_data

log = logging.getLogger("postmule.agents.retroactive")

# Rate limit: Gemini free tier is 15 req/min (conservative: 1 call per 5s)
_RATE_LIMIT_SECONDS = 5.0


def run_retroactive(
    pdf_paths: list[Path],
    llm,                    # GeminiProvider
    drive,                  # DriveProvider
    folder_ids: dict[str, str],
    data_dir: Path,
    known_names: list[str] | None = None,
    confidence_threshold: float = 0.80,
    rate_limit_seconds: float = _RATE_LIMIT_SECONDS,
    max_files: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Process a list of PDF paths through the full classification pipeline.

    Args:
        pdf_paths:            List of local PDF paths to process.
        llm:                  Configured GeminiProvider.
        drive:                Configured DriveProvider.
        folder_ids:           Dict of Drive folder IDs.
        data_dir:             Path to JSON data directory.
        known_names:          Known entity names for LLM context.
        confidence_threshold: Below this, file goes to NeedsReview.
        rate_limit_seconds:   Pause between LLM calls.
        max_files:            Stop after this many files (safety cap).
        dry_run:              Classify but don't upload or write JSON.

    Returns:
        Summary dict with counts per category.
    """
    total = len(pdf_paths)
    if max_files:
        pdf_paths = pdf_paths[:max_files]
        if len(pdf_paths) < total:
            log.info(f"Capped at {max_files} files (from {total} total)")

    log.info(f"Retroactive processing: {len(pdf_paths)} PDFs")

    counts: dict[str, int] = {k: 0 for k in CATEGORY_FOLDERS}
    errors: list[str] = []
    processed = 0

    for i, pdf_path in enumerate(pdf_paths, 1):
        log.info(f"[{i}/{len(pdf_paths)}] {pdf_path.name}")

        # Use parent folder name as classification hint
        folder_hint = pdf_path.parent.name

        try:
            result = classify_pdf(
                pdf_path=pdf_path,
                llm=llm,
                known_names=known_names,
                confidence_threshold=confidence_threshold,
                dry_run=dry_run,
            )
        except Exception as exc:
            msg = f"Classification failed for {pdf_path.name}: {exc}"
            log.error(msg)
            errors.append(msg)
            continue

        counts[result.category] = counts.get(result.category, 0) + 1
        processed += 1

        if not dry_run:
            # Upload to Drive
            dest_folder_key = result.destination_folder.lower().replace("tome", "_to_me")
            dest_folder_id = folder_ids.get(
                result.destination_folder.lower(),
                folder_ids.get("needs_review", ""),
            )

            if dest_folder_id:
                try:
                    drive_id = drive.upload_pdf(
                        pdf_path,
                        result.suggested_filename,
                        dest_folder_id,
                        verify=True,
                    )
                    _store_record(data_dir, result, drive_id)
                except Exception as exc:
                    msg = f"Upload failed for {pdf_path.name}: {exc}"
                    log.error(msg)
                    errors.append(msg)

        # Rate limit between LLM calls
        if i < len(pdf_paths):
            time.sleep(rate_limit_seconds)

    log.info(
        f"Retroactive complete: {processed}/{len(pdf_paths)} processed, "
        f"{len(errors)} errors. Counts: {counts}"
    )

    return {
        "processed": processed,
        "errors": errors,
        "counts": counts,
    }


def _store_record(data_dir: Path, result, drive_id: str) -> None:
    base = {
        "date_received": result.processed_date,
        "date_processed": result.processed_date,
        "sender": result.sender,
        "recipients": result.recipients,
        "summary": result.summary,
        "drive_file_id": drive_id,
        "filename": result.suggested_filename,
    }

    if result.category == "Bill":
        bills_data.add_bill(data_dir, {
            **base,
            "amount_due": result.amount_due,
            "due_date": result.due_date,
            "account_number": result.account_number,
            "status": "pending",
        })
    elif result.category == "Notice":
        notices_data.add_notice(data_dir, base)
    elif result.category == "ForwardToMe":
        ftm_data.add_item(data_dir, {**base, "forwarding_status": "pending"})
