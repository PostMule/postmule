"""
Gmail provider — reads emails from a Gmail account using the Gmail API (OAuth2).

Responsibilities:
  - List unread emails matching VPM sender/subject filter
  - Download PDF attachments
  - Mark emails as processed (apply label)
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from postmule.providers.email.base import EmailMessage  # re-exported for callers

log = logging.getLogger("postmule.email.gmail")

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GmailProvider:
    """
    Gmail API provider using OAuth2 credentials.

    Args:
        credentials: google.oauth2.credentials.Credentials object (from build_google_credentials()).
        label_name:  Gmail label to apply to processed emails (default: "PostMule").
    """

    def __init__(self, credentials: Any, label_name: str = "PostMule") -> None:
        self.credentials = credentials
        self.label_name = label_name
        self._service = None
        self._label_id: str | None = None

    def _get_service(self):
        if self._service is None:
            from googleapiclient.discovery import build  # type: ignore[import]
            self._service = build("gmail", "v1", credentials=self.credentials)
        return self._service

    def health_check(self):
        """Return a HealthResult indicating whether Gmail credentials are valid."""
        from postmule.providers import HealthResult
        try:
            svc = self._get_service()
            svc.users().labels().list(userId="me").execute()
            return HealthResult(ok=True, status="ok", message="Gmail connected")
        except Exception as exc:
            return HealthResult(ok=False, status="error", message=str(exc))

    def list_unprocessed_emails(
        self,
        sender_filter: str = "noreply@virtualpostmail.com",
        subject_filter: str = "[Scan Request]",
    ) -> list[EmailMessage]:
        """
        Return all emails from sender_filter that have not yet been labelled.

        Args:
            sender_filter: From address to filter on.
            subject_filter: Subject substring to filter on.

        Returns:
            List of EmailMessage objects with attachment data loaded.
        """
        svc = self._get_service()
        label_id = self._get_or_create_label()

        # Search: from sender, NOT already labelled
        query = f"from:{sender_filter} subject:{subject_filter} -label:{self.label_name}"
        log.debug(f"Gmail query: {query}")

        messages = []
        page_token = None

        while True:
            kwargs: dict[str, Any] = {"userId": "me", "q": query, "maxResults": 100}
            if page_token:
                kwargs["pageToken"] = page_token

            result = svc.users().messages().list(**kwargs).execute()
            batch = result.get("messages", [])
            messages.extend(batch)
            log.debug(f"Retrieved {len(messages)} messages so far...")

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        log.info(f"Found {len(messages)} unprocessed VPM emails")

        emails = []
        for msg_ref in messages:
            email = self._load_email(svc, msg_ref["id"])
            if email:
                emails.append(email)

        return emails

    def list_emails_with_pdf_attachments(self) -> list[EmailMessage]:
        """Return all unprocessed emails that contain at least one PDF attachment.

        Used for the bill_intake pipeline step (Phase 23). Searches for any email
        with a PDF attachment that has not yet been labelled as processed.
        """
        svc = self._get_service()
        self._get_or_create_label()

        query = f"has:attachment filename:pdf -label:{self.label_name}"
        log.debug(f"Gmail bill-intake query: {query}")

        messages: list[dict] = []
        page_token = None

        while True:
            kwargs: dict[str, Any] = {"userId": "me", "q": query, "maxResults": 100}
            if page_token:
                kwargs["pageToken"] = page_token

            result = svc.users().messages().list(**kwargs).execute()
            messages.extend(result.get("messages", []))
            log.debug(f"Retrieved {len(messages)} bill-intake candidates so far...")

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        log.info(f"Found {len(messages)} unprocessed emails with PDF attachments")

        emails = []
        for msg_ref in messages:
            email = self._load_email(svc, msg_ref["id"])
            if email:
                emails.append(email)

        return emails

    def mark_as_processed(self, message_id: str) -> None:
        """Apply the configured label to an email to mark it as processed."""
        svc = self._get_service()
        label_id = self._get_or_create_label()
        svc.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": [label_id]},
        ).execute()
        log.debug(f"Marked message {message_id[:12]}... as processed")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_email(self, svc, message_id: str) -> EmailMessage | None:
        try:
            msg = svc.users().messages().get(
                userId="me", id=message_id, format="full"
            ).execute()
        except Exception as exc:
            log.warning(f"Failed to load message {message_id}: {exc}")
            return None

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "(no subject)")
        sender = headers.get("From", "")
        date_str = _parse_email_date(headers.get("Date", ""))

        attachments = self._extract_pdf_attachments(svc, message_id, msg)
        if not attachments:
            log.debug(f"No PDF attachments in message {message_id[:12]}...")
            return None

        return EmailMessage(
            message_id=message_id,
            subject=subject,
            received_date=date_str,
            sender=sender,
            attachments=attachments,
        )

    def _extract_pdf_attachments(
        self, svc, message_id: str, msg: dict
    ) -> list[dict]:
        """Extract all PDF attachments from a message."""
        pdfs = []
        parts = _flatten_parts(msg.get("payload", {}))

        for part in parts:
            filename = part.get("filename", "")
            mime = part.get("mimeType", "")
            if not (filename.lower().endswith(".pdf") or "pdf" in mime.lower()):
                continue

            body = part.get("body", {})
            attachment_id = body.get("attachmentId")

            if attachment_id:
                att = svc.users().messages().attachments().get(
                    userId="me", messageId=message_id, id=attachment_id
                ).execute()
                data = base64.urlsafe_b64decode(att["data"])
            elif "data" in body:
                data = base64.urlsafe_b64decode(body["data"])
            else:
                continue

            pdfs.append({"name": filename or "attachment.pdf", "data": data})

        return pdfs

    def _get_or_create_label(self) -> str:
        if self._label_id:
            return self._label_id

        svc = self._get_service()
        labels = svc.users().labels().list(userId="me").execute().get("labels", [])
        for label in labels:
            if label["name"].lower() == self.label_name.lower():
                self._label_id = label["id"]
                return self._label_id

        # Create label
        new_label = svc.users().labels().create(
            userId="me",
            body={"name": self.label_name, "labelListVisibility": "labelShow"},
        ).execute()
        self._label_id = new_label["id"]
        log.info(f"Created Gmail label: {self.label_name}")
        return self._label_id


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _flatten_parts(payload: dict) -> list[dict]:
    """Recursively flatten multipart email parts."""
    parts = []
    if payload.get("parts"):
        for part in payload["parts"]:
            parts.extend(_flatten_parts(part))
    else:
        parts.append(payload)
    return parts


def _parse_email_date(date_str: str) -> str:
    """Parse email Date header to YYYY-MM-DD, return today if unparseable."""
    from datetime import date
    from email.utils import parsedate_to_datetime

    try:
        dt = parsedate_to_datetime(date_str)
        return dt.date().isoformat()
    except Exception:
        return date.today().isoformat()
