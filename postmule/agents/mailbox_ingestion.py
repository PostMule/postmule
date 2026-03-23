"""
VPM mailbox ingestion agent — fetches mail items via VPM direct API,
saves PDFs locally, and uploads to Drive Inbox.

Used as the ingestion path when VPM credentials are configured.
The pipeline falls back to Gmail-based email_ingestion when they are not.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from postmule.agents.email_ingestion import IngestedPDF, IngestionResult

log = logging.getLogger("postmule.agents.mailbox_ingestion")


def run_vpm_ingestion(
    vpm,
    drive,
    inbox_folder_id: str,
    download_dir: Path,
    dry_run: bool = False,
) -> IngestionResult:
    """
    Fetch unprocessed VPM mail items, save PDFs locally, upload to Drive Inbox.

    Args:
        vpm:             Configured VpmProvider instance.
        drive:           Configured DriveProvider instance.
        inbox_folder_id: Drive folder ID for /Inbox.
        download_dir:    Local directory to temporarily save PDFs.
        dry_run:         If True, fetch and log but don't upload or mark processed.

    Returns:
        IngestionResult (same shape as email_ingestion.run_ingestion).
    """
    result = IngestionResult()
    download_dir.mkdir(parents=True, exist_ok=True)

    log.info("Fetching unprocessed items from VPM API...")
    try:
        items = vpm.list_unprocessed_items()
    except Exception as exc:
        msg = f"VPM list_unprocessed_items failed: {exc}"
        log.error(msg)
        result.errors.append(msg)
        return result

    result.emails_found = len(items)

    if not items:
        log.info("No new VPM mail items found.")
        return result

    log.info(f"Found {len(items)} unprocessed VPM mail item(s).")

    for item in items:
        filename = _build_filename(item.mail_item_id, item.received_date)
        local_path = download_dir / filename

        # Download PDF from VPM
        try:
            pdf_bytes = vpm.download_pdf(item.mail_item_id)
            local_path.write_bytes(pdf_bytes)
            result.pdfs_saved += 1
            log.debug(f"Saved: {filename}")
        except Exception as exc:
            msg = f"Failed to download PDF for VPM item {item.mail_item_id}: {exc}"
            log.error(msg)
            result.errors.append(msg)
            continue

        if dry_run:
            log.info(f"[DRY RUN] Would upload: {filename}")
            result.pdfs_uploaded += 1
            result.ingested.append(IngestedPDF(
                filename=filename,
                local_path=local_path,
                source_email_id=item.mail_item_id,
                received_date=item.received_date,
            ))
            continue

        # Upload to Drive Inbox
        try:
            drive_id = drive.upload_pdf(local_path, filename, inbox_folder_id, verify=True)
            result.pdfs_uploaded += 1
            result.ingested.append(IngestedPDF(
                filename=filename,
                local_path=local_path,
                source_email_id=item.mail_item_id,
                received_date=item.received_date,
                drive_file_id=drive_id,
            ))
            log.info(f"Uploaded to Drive Inbox: {filename}")
        except Exception as exc:
            msg = f"Failed to upload {filename} to Drive: {exc}"
            log.error(msg)
            result.errors.append(msg)
            continue

        # Mark as processed only after a successful upload
        try:
            vpm.mark_as_processed(item.mail_item_id)
        except Exception as exc:
            log.warning(
                f"Failed to mark VPM item {item.mail_item_id} as processed: {exc} "
                f"— item will be re-downloaded on next run"
            )

    log.info(
        f"VPM ingestion complete: {result.emails_found} items, "
        f"{result.pdfs_uploaded} PDFs uploaded, "
        f"{len(result.errors)} errors"
    )
    return result


def _build_filename(mail_item_id: str, received_date: str) -> str:
    """Build a safe PDF filename from VPM mail item ID and received date."""
    safe_id = re.sub(r"[^\w\-]", "_", str(mail_item_id))
    return f"{received_date}_vpm_{safe_id}.pdf"
