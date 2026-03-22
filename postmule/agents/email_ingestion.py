"""
Email ingestion agent — fetches new VPM emails, saves PDFs locally, uploads to Drive Inbox.

This is the first step of the daily pipeline.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("postmule.agents.email_ingestion")


@dataclass
class IngestedPDF:
    filename: str
    local_path: Path
    source_email_id: str
    received_date: str
    drive_file_id: str = ""


@dataclass
class IngestionResult:
    emails_found: int = 0
    pdfs_saved: int = 0
    pdfs_uploaded: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    ingested: list[IngestedPDF] = field(default_factory=list)


def run_ingestion(
    gmail,           # GmailProvider
    drive,           # DriveProvider
    inbox_folder_id: str,
    download_dir: Path,
    sender_filter: str = "noreply@virtualpostmail.com",
    subject_filter: str = "[Scan Request]",
    dry_run: bool = False,
) -> IngestionResult:
    """
    Fetch unprocessed VPM emails, save PDFs to local dir, upload to Drive Inbox.

    Args:
        gmail:           Configured GmailProvider.
        drive:           Configured DriveProvider.
        inbox_folder_id: Drive folder ID for /Inbox.
        download_dir:    Local directory to temporarily save PDFs.
        sender_filter:   VPM sender email address.
        subject_filter:  VPM subject prefix.
        dry_run:         If True, fetch and log but don't upload or label.

    Returns:
        IngestionResult summary.
    """
    result = IngestionResult()
    download_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"Fetching emails from {sender_filter}...")
    emails = gmail.list_unprocessed_emails(sender_filter, subject_filter)
    result.emails_found = len(emails)

    if not emails:
        log.info("No new VPM emails found.")
        return result

    log.info(f"Found {len(emails)} new emails.")

    for email in emails:
        upload_failed = False
        for attachment in email.attachments:
            filename = _sanitize_filename(attachment["name"], email.received_date)
            local_path = download_dir / filename

            # Save PDF locally
            try:
                local_path.write_bytes(attachment["data"])
                result.pdfs_saved += 1
                log.debug(f"Saved: {filename}")
            except Exception as exc:
                msg = f"Failed to save {filename}: {exc}"
                log.error(msg)
                result.errors.append(msg)
                upload_failed = True
                continue

            if dry_run:
                log.info(f"[DRY RUN] Would upload: {filename}")
                result.pdfs_uploaded += 1
                result.ingested.append(IngestedPDF(
                    filename=filename,
                    local_path=local_path,
                    source_email_id=email.message_id,
                    received_date=email.received_date,
                ))
                continue

            # Upload to Drive Inbox
            try:
                drive_id = drive.upload_pdf(local_path, filename, inbox_folder_id, verify=True)
                result.pdfs_uploaded += 1
                result.ingested.append(IngestedPDF(
                    filename=filename,
                    local_path=local_path,
                    source_email_id=email.message_id,
                    received_date=email.received_date,
                    drive_file_id=drive_id,
                ))
                log.info(f"Uploaded to Drive Inbox: {filename}")
            except Exception as exc:
                msg = f"Failed to upload {filename} to Drive: {exc}"
                log.error(msg)
                result.errors.append(msg)
                upload_failed = True

        # Only mark as processed when every attachment uploaded successfully.
        # If any upload failed, leave the email unprocessed so it retries tomorrow.
        if not dry_run and not upload_failed:
            try:
                gmail.mark_as_processed(email.message_id)
            except Exception as exc:
                log.warning(f"Failed to mark email {email.message_id[:12]}... as processed: {exc}")
        elif upload_failed:
            log.warning(
                f"Email {email.message_id[:12]}... NOT marked processed due to upload failure(s) — will retry tomorrow."
            )

    log.info(
        f"Ingestion complete: {result.emails_found} emails, "
        f"{result.pdfs_uploaded} PDFs uploaded, "
        f"{len(result.errors)} errors"
    )
    return result


def _sanitize_filename(name: str, date_prefix: str) -> str:
    """Ensure filename starts with date and is safe."""
    import re
    safe = re.sub(r"[^\w\-.]", "_", name)
    if not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    # Prefix with date if not already dated
    if not safe.startswith(date_prefix):
        safe = f"{date_prefix}_{safe}"
    return safe
