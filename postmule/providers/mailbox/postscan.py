"""
PostScan Mail mailbox provider.

No public API is available. This provider reads scan notification emails via
IMAP and downloads PDFs by authenticating to the PostScan Mail web portal.

Integration path: email notification parsing.
  - PostScan Mail sends a notification email for each new mail piece.
  - This provider reads those emails via IMAP (UNSEEN search).
  - PDFs are downloaded by logging into the web portal with the user's credentials.
  - The IMAP email is marked SEEN after successful download to avoid re-processing.

NOTE: Web portal endpoints are inferred from the public-facing web UI and have
not been verified against a live account. Adjust _PDF_LINK_PATTERN,
_LOGIN_PATH, and _AUTH_PARAMS if the portal changes.

Config example:
    mailbox:
      providers:
        - service: postscan
          enabled: true
          username: user@example.com
          password: <from keyring>
          imap_host: imap.gmail.com
          imap_user: postmule-notifications@example.com
          imap_password: <from keyring>
"""

from __future__ import annotations

import email as _email
import imaplib
import logging
import re
from datetime import date

log = logging.getLogger("postmule.mailbox.postscan")

SERVICE_KEY = "postscan"
DISPLAY_NAME = "PostScan Mail"

# PostScan sends notifications from this address.
_NOTIFICATION_FROM = "noreply@postscanmail.com"
# Regex to find the PDF/view link in notification email HTML.
# NOTE: verify against a real PostScan notification email.
_PDF_LINK_PATTERN = re.compile(
    r'href=["\']([^"\']*postscanmail\.com[^"\']*(?:view|download|pdf|mail)[^"\']*)["\']',
    re.IGNORECASE,
)
# Web portal login
_PORTAL_BASE = "https://www.postscanmail.com"
_LOGIN_PATH = "/login"  # NOTE: verify
_IMAP_SEARCH = b'(UNSEEN FROM "noreply@postscanmail.com")'


class PostScanMailProvider:
    """
    PostScan Mail physical mailbox provider via email notification parsing.

    Args:
        username:      PostScan Mail account email address.
        password:      PostScan Mail account password.
        imap_host:     IMAP host for the inbox that receives notification emails.
        imap_user:     IMAP username (may differ from PostScan username).
        imap_password: IMAP password.
        imap_port:     IMAP SSL port (default 993).
    """

    def __init__(
        self,
        username: str,
        password: str,
        imap_host: str,
        imap_user: str,
        imap_password: str,
        imap_port: int = 993,
    ) -> None:
        self.username = username
        self.password = password
        self.imap_host = imap_host
        self.imap_user = imap_user
        self.imap_password = imap_password
        self.imap_port = imap_port
        self._session = None

    def health_check(self):
        """Return a HealthResult by testing the IMAP connection."""
        from postmule.providers import HealthResult
        try:
            conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            conn.login(self.imap_user, self.imap_password)
            conn.logout()
            return HealthResult(
                ok=True,
                status="ok",
                message=f"PostScan Mail: IMAP connected ({self.imap_host})",
            )
        except Exception as exc:
            return HealthResult(ok=False, status="error", message=str(exc))

    def list_unprocessed_items(self) -> list:
        """
        Return unread PostScan scan notification emails as MailItem objects.

        The IMAP email UID is used as mail_item_id.
        """
        from postmule.providers.mailbox.vpm import MailItem
        conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        conn.login(self.imap_user, self.imap_password)
        conn.select("INBOX")
        _, data = conn.search(None, _IMAP_SEARCH)
        uids = data[0].split() if data[0] else []
        items = []
        for uid in uids:
            try:
                _, msg_data = conn.fetch(uid, "(RFC822)")
                raw = msg_data[0][1]
                msg = _email.message_from_bytes(raw)
                received_date = _parse_email_date(msg.get("Date", ""))
                items.append(MailItem(
                    mail_item_id=uid.decode(),
                    received_date=received_date,
                    sender="PostScan Mail",
                    scan_date=received_date,
                ))
            except Exception as exc:
                log.warning(f"Could not parse PostScan notification {uid}: {exc}")
        conn.logout()
        log.info(f"PostScan Mail: {len(items)} unprocessed notification(s)")
        return items

    def download_pdf(self, mail_item_id: str) -> bytes:
        """
        Download the scanned PDF for a mail item.

        Fetches the notification email identified by mail_item_id (IMAP UID),
        extracts the PDF download URL, and downloads it using an authenticated
        session with PostScan Mail credentials.

        Args:
            mail_item_id: IMAP email UID (from list_unprocessed_items).
        """
        pdf_url = self._extract_pdf_url(mail_item_id)
        session = self._get_authenticated_session()
        resp = session.get(pdf_url, timeout=60)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower() and "octet-stream" not in content_type.lower():
            raise RuntimeError(
                f"PostScan Mail: unexpected content type '{content_type}' "
                f"for mail item {mail_item_id}"
            )
        if not resp.content:
            raise RuntimeError(f"PostScan Mail: empty PDF for mail item {mail_item_id}")
        log.debug(f"Downloaded PDF for PostScan item {mail_item_id}: {len(resp.content)} bytes")
        return resp.content

    def mark_as_processed(self, mail_item_id: str) -> None:
        """Mark the IMAP notification email as SEEN."""
        conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        conn.login(self.imap_user, self.imap_password)
        conn.select("INBOX")
        conn.store(mail_item_id.encode(), "+FLAGS", "\\Seen")
        conn.logout()
        log.debug(f"Marked PostScan notification {mail_item_id} as seen")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_pdf_url(self, mail_item_id: str) -> str:
        """Fetch the notification email and extract the PDF download URL."""
        conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
        conn.login(self.imap_user, self.imap_password)
        conn.select("INBOX")
        _, msg_data = conn.fetch(mail_item_id.encode(), "(RFC822)")
        conn.logout()

        raw = msg_data[0][1]
        msg = _email.message_from_bytes(raw)
        body = _get_html_body(msg)

        match = _PDF_LINK_PATTERN.search(body)
        if not match:
            raise RuntimeError(
                f"PostScan Mail: no PDF link found in notification email {mail_item_id}. "
                "The email format may have changed — update _PDF_LINK_PATTERN."
            )
        return match.group(1)

    def _get_authenticated_session(self):
        """Return a requests.Session authenticated with PostScan Mail credentials."""
        if self._session is not None:
            return self._session
        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError("requests is not installed. Run: pip install requests")

        session = requests.Session()
        session.headers.update({"User-Agent": "PostMule/0.1"})

        # NOTE: verify PostScan login form fields against real account
        login_url = f"{_PORTAL_BASE}{_LOGIN_PATH}"
        resp = session.get(login_url, timeout=30)
        resp.raise_for_status()

        csrf_token = _extract_csrf(resp.text)
        login_data = {
            "email": self.username,
            "password": self.password,
        }
        if csrf_token:
            login_data["_token"] = csrf_token

        resp2 = session.post(login_url, data=login_data, timeout=30, allow_redirects=True)
        resp2.raise_for_status()

        if "login" in resp2.url.lower():
            raise RuntimeError("PostScan Mail login failed — check credentials")

        self._session = session
        log.debug("PostScan Mail: authenticated session established")
        return session


def _parse_email_date(date_str: str) -> str:
    """Parse RFC 2822 email date to ISO YYYY-MM-DD; fall back to today."""
    if not date_str:
        return date.today().isoformat()
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str).date().isoformat()
    except Exception:
        return date.today().isoformat()


def _get_html_body(msg) -> str:
    """Extract the HTML (or plain text) body from an email.Message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                return part.get_payload(decode=True).decode(errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode(errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode(errors="replace") if payload else ""


def _extract_csrf(html: str) -> str:
    """Extract CSRF token from HTML (handles Laravel _token and Rails authenticity_token)."""
    for pattern in [
        r'<input[^>]+name=["\']_token["\'][^>]+value=["\']([^"\']+)["\']',
        r'<input[^>]+name=["\']authenticity_token["\'][^>]+value=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']',
    ]:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return ""
