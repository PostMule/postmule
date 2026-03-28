"""
Generic IMAP email provider — connects to any standard IMAP server.

Supports Yahoo Mail, Fastmail, self-hosted (Dovecot/Postfix), and any
other IMAP-capable mail server.

Config example:
    email:
      providers:
        - service: imap
          enabled: true
          role: mailbox_notifications
          address: you@yourdomain.com
          host: imap.yourdomain.com
          port: 993
          use_ssl: true
"""

from __future__ import annotations

import email as email_lib
import imaplib
import logging
from email.header import decode_header

from postmule.providers.email.base import EmailMessage

log = logging.getLogger("postmule.email.imap")

SERVICE_KEY = "imap"
DISPLAY_NAME = "Generic IMAP"

_DEFAULT_PROCESSED_FOLDER = "PostMule"


class ImapProvider:
    """
    Generic IMAP provider for any standard IMAP mail server.

    Args:
        host:              IMAP server hostname (e.g., imap.yourdomain.com).
        port:              IMAP port (default: 993 for SSL, 143 for plain/STARTTLS).
        username:          Login username (usually email address).
        password:          Login password or app password.
        use_ssl:           Use IMAP4_SSL (default: True).
        processed_folder:  Folder to move processed emails into (default: PostMule).
        inbox_folder:      Folder to search for incoming mail (default: INBOX).
    """

    def __init__(
        self,
        host: str,
        port: int = 993,
        username: str = "",
        password: str = "",
        use_ssl: bool = True,
        processed_folder: str = _DEFAULT_PROCESSED_FOLDER,
        inbox_folder: str = "INBOX",
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self.processed_folder = processed_folder
        self.inbox_folder = inbox_folder

    def _connect(self) -> imaplib.IMAP4:
        """Open an authenticated IMAP connection."""
        try:
            if self.use_ssl:
                conn = imaplib.IMAP4_SSL(self.host, self.port)
            else:
                conn = imaplib.IMAP4(self.host, self.port)
            conn.login(self.username, self.password)
            return conn
        except imaplib.IMAP4.error as exc:
            raise RuntimeError(f"IMAP login failed for {self.username}@{self.host}: {exc}") from exc

    def _ensure_folder_exists(self, conn: imaplib.IMAP4, folder: str) -> None:
        """Create the folder if it doesn't already exist."""
        status, _ = conn.select(f'"{folder}"')
        if status != "OK":
            conn.create(f'"{folder}"')

    def health_check(self):
        """Return a HealthResult indicating whether the IMAP server is reachable."""
        from postmule.providers import HealthResult
        try:
            conn = self._connect()
            conn.select(self.inbox_folder)
            conn.logout()
            return HealthResult(
                ok=True,
                status="ok",
                message=f"IMAP connected to {self.host} as {self.username}",
            )
        except Exception as exc:
            return HealthResult(ok=False, status="error", message=str(exc))

    def list_unprocessed_emails(
        self,
        sender_filter: str = "",
        subject_filter: str = "",
    ) -> list[EmailMessage]:
        """Return unprocessed (UNSEEN) emails matching optional sender/subject filters."""
        criteria = _build_search_criteria(sender_filter, subject_filter)
        return self._fetch_emails(criteria)

    def list_emails_with_pdf_attachments(self) -> list[EmailMessage]:
        """Return all unprocessed emails that contain at least one PDF attachment."""
        all_emails = self._fetch_emails(b"UNSEEN")
        return [e for e in all_emails if e.attachments]

    def mark_as_processed(self, message_id: str) -> None:
        """Move the message (UID) to the processed folder and delete from inbox."""
        conn = self._connect()
        try:
            conn.select(self.inbox_folder)
            self._ensure_folder_exists(conn, self.processed_folder)
            result, _ = conn.uid("COPY", message_id.encode(), f'"{self.processed_folder}"')
            if result != "OK":
                log.warning(f"IMAP COPY failed for UID {message_id}")
                return
            conn.uid("STORE", message_id.encode(), "+FLAGS", "\\Deleted")
            conn.expunge()
            log.debug(f"Marked UID {message_id} as processed → {self.processed_folder}")
        except Exception as exc:
            log.error(f"mark_as_processed failed for UID {message_id}: {exc}")
            raise
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def _fetch_emails(self, criteria: bytes) -> list[EmailMessage]:
        conn = self._connect()
        results: list[EmailMessage] = []
        try:
            conn.select(self.inbox_folder, readonly=True)
            status, data = conn.uid("SEARCH", None, criteria)
            if status != "OK" or not data[0]:
                return []

            uids = data[0].split()
            log.info(f"IMAP SEARCH returned {len(uids)} messages")

            for uid in uids:
                try:
                    msg = _fetch_single(conn, uid)
                    if msg:
                        results.append(msg)
                except Exception as exc:
                    log.warning(f"Failed to fetch IMAP message UID {uid}: {exc}")
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        return results


# ------------------------------------------------------------------
# Module-level helpers (shared with ProtonMailProvider)
# ------------------------------------------------------------------

def _build_search_criteria(sender_filter: str, subject_filter: str) -> bytes:
    parts = ["UNSEEN"]
    if sender_filter:
        parts.append(f'FROM "{sender_filter}"')
    if subject_filter:
        parts.append(f'SUBJECT "{subject_filter}"')
    return " ".join(parts).encode()


def _fetch_single(conn: imaplib.IMAP4, uid: bytes) -> EmailMessage | None:
    status, data = conn.uid("FETCH", uid, "(RFC822)")
    if status != "OK" or not data or not data[0]:
        return None

    raw = data[0][1] if isinstance(data[0], tuple) else data[0]
    msg = email_lib.message_from_bytes(raw)

    subject = _decode_header_value(msg.get("Subject", ""))
    sender = _decode_header_value(msg.get("From", ""))
    date_str = _parse_date(msg.get("Date", ""))

    attachments = []
    for part in msg.walk():
        if part.get_content_disposition() == "attachment":
            filename = part.get_filename() or ""
            if filename.lower().endswith(".pdf"):
                payload = part.get_payload(decode=True)
                if payload:
                    attachments.append({"name": filename, "data": payload})

    return EmailMessage(
        message_id=uid.decode(),
        subject=subject,
        received_date=date_str,
        sender=sender,
        attachments=attachments,
    )


def _decode_header_value(value: str) -> str:
    if not value:
        return ""
    parts = []
    for fragment, charset in decode_header(value):
        if isinstance(fragment, bytes):
            parts.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(fragment)
    return "".join(parts)


def _parse_date(date_str: str) -> str:
    if not date_str:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str).strftime("%Y-%m-%d")
    except Exception:
        return ""
