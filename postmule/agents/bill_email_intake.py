"""
Bill email intake agent — fetches emails with PDF attachments from bill_intake providers,
saves PDFs locally, and uploads to Drive Inbox.

Step 1b of the daily pipeline. Runs after VPM/mailbox ingestion (step 1a) and feeds
the same OCR → classify → rename → move pipeline (step 2 onward).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from postmule.agents.email_ingestion import IngestedPDF, IngestionResult

log = logging.getLogger("postmule.agents.bill_email_intake")


def run_intake(
    email_provider,     # EmailProvider (role: bill_intake)
    drive,              # DriveProvider
    inbox_folder_id: str,
    download_dir: Path,
    dry_run: bool = False,
) -> IngestionResult:
    """
    Fetch unprocessed emails with PDF attachments, save locally, upload to Drive Inbox.

    Called once per configured bill_intake email provider. Results are merged into
    the main processed_pdfs list so classification (step 2) handles them identically
    to physical mail scans.

    Args:
        email_provider:  Configured provider with role bill_intake.
        drive:           Configured DriveProvider.
        inbox_folder_id: Drive folder ID for /Inbox.
        download_dir:    Local directory to temporarily save PDFs.
        dry_run:         If True, fetch and log but don't upload or mark processed.

    Returns:
        IngestionResult (same shape as email_ingestion.run_ingestion).
    """
    result = IngestionResult()
    download_dir.mkdir(parents=True, exist_ok=True)

    log.info("Fetching emails with PDF attachments from bill_intake provider...")
    try:
        emails = email_provider.list_emails_with_pdf_attachments()
    except Exception as exc:
        msg = f"list_emails_with_pdf_attachments failed: {exc}"
        log.error(msg)
        result.errors.append(msg)
        return result

    result.emails_found = len(emails)

    if not emails:
        log.info("No new bill emails found.")
        return result

    log.info(f"Found {len(emails)} email(s) with PDF attachments.")

    for email in emails:
        upload_failed = False

        for attachment in email.attachments:
            filename = _build_filename(attachment["name"], email.received_date)
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
        if not dry_run and not upload_failed:
            try:
                email_provider.mark_as_processed(email.message_id)
            except Exception as exc:
                log.warning(
                    f"Failed to mark email {email.message_id[:12]}... as processed: {exc}"
                )
        elif upload_failed:
            log.warning(
                f"Email {email.message_id[:12]}... NOT marked processed due to upload failure(s) "
                f"— will retry tomorrow."
            )

    log.info(
        f"Bill email intake complete: {result.emails_found} emails, "
        f"{result.pdfs_uploaded} PDFs uploaded, "
        f"{len(result.errors)} errors"
    )
    return result


def _build_filename(attachment_name: str, received_date: str) -> str:
    """Build a safe PDF filename, prefixed with the received date."""
    safe = re.sub(r"[^\w\-.]", "_", attachment_name)
    if not safe.lower().endswith(".pdf"):
        safe += ".pdf"
    if not safe.startswith(received_date):
        safe = f"{received_date}_bill_{safe}"
    return safe
