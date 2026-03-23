"""
VPM (Virtual Post Mail) direct API provider.

Uses VPM's JSON API at https://www.virtualpostmail.com/webtools/json
to fetch unprocessed mail items and download PDFs directly,
without requiring a Gmail intermediary.

API operations:
  doLogin              — Authenticate; returns session token
  listMail             — List mail items
  getMailItemImagePDF  — Download PDF for a mail item
  doMarkAsViewed       — Mark a mail item as viewed/processed
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

log = logging.getLogger("postmule.mailbox.vpm")

_VPM_API_URL = "https://www.virtualpostmail.com/webtools/json"
_REQUEST_TIMEOUT = 60  # seconds


@dataclass
class MailItem:
    mail_item_id: str
    received_date: str  # ISO YYYY-MM-DD
    sender: str
    scan_date: str      # ISO YYYY-MM-DD


class VpmProvider:
    """
    VPM direct REST API client.

    Args:
        username: VPM account username (email address).
        password: VPM account password.
    """

    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password
        self._token: str | None = None
        self._session = None

    def _get_session(self):
        if self._session is None:
            import requests  # type: ignore[import]
            self._session = requests.Session()
            self._session.headers.update({"User-Agent": "PostMule/0.1"})
        return self._session

    def _login(self) -> str:
        """Authenticate with VPM and return a session token."""
        session = self._get_session()
        resp = session.post(
            _VPM_API_URL,
            data={"action": "doLogin", "login": self.username, "password": self.password},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"VPM login failed: {data.get('error', 'unknown error')}")
        token = data.get("token", "")
        if not token:
            raise RuntimeError("VPM login succeeded but returned no token")
        log.debug("VPM login successful")
        return token

    def _get_token(self) -> str:
        """Return cached token, logging in if necessary."""
        if not self._token:
            self._token = self._login()
        return self._token

    def _api_call(self, action: str, **params) -> Any:
        """Make an authenticated VPM API call, re-authenticating once on token expiry."""
        token = self._get_token()
        session = self._get_session()
        payload = {"action": action, "token": token, **params}
        resp = session.post(_VPM_API_URL, data=payload, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        # If the server signals an auth error, re-login once and retry
        if not data.get("success") and "login" in str(data.get("error", "")).lower():
            log.debug("VPM token expired — re-authenticating")
            self._token = self._login()
            payload["token"] = self._token
            resp = session.post(_VPM_API_URL, data=payload, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

        return data

    def list_unprocessed_items(self) -> list[MailItem]:
        """
        Return all unviewed mail items from the VPM account.

        Returns:
            List of MailItem objects for items not yet marked as viewed.
        """
        data = self._api_call("listMail")
        if not data.get("success"):
            raise RuntimeError(f"VPM listMail failed: {data.get('error', 'unknown error')}")

        # VPM may return items under different keys depending on API version
        raw_items = data.get("items") or data.get("mailItems") or []
        items = []
        for raw in raw_items:
            # Skip already-viewed items
            if raw.get("viewed") or raw.get("status") == "viewed":
                continue

            mail_item_id = str(raw.get("mailItemID") or raw.get("id") or "")
            if not mail_item_id:
                log.debug(f"Skipping VPM item with no ID: {raw}")
                continue

            items.append(MailItem(
                mail_item_id=mail_item_id,
                received_date=_parse_vpm_date(
                    raw.get("receivedDate") or raw.get("dateReceived") or ""
                ),
                sender=raw.get("senderName") or raw.get("sender") or "",
                scan_date=_parse_vpm_date(
                    raw.get("scanDate") or raw.get("dateScan") or ""
                ),
            ))

        log.info(f"VPM: {len(items)} unprocessed mail item(s)")
        return items

    def download_pdf(self, mail_item_id: str) -> bytes:
        """
        Download the scanned PDF for a mail item.

        Args:
            mail_item_id: VPM mail item ID.

        Returns:
            PDF bytes.

        Raises:
            RuntimeError: If the download fails or content is not a PDF.
        """
        token = self._get_token()
        session = self._get_session()
        resp = session.post(
            _VPM_API_URL,
            data={"action": "getMailItemImagePDF", "token": token, "mailItemID": mail_item_id},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower() and "octet-stream" not in content_type.lower():
            # Try to decode as JSON error
            try:
                error_data = resp.json()
                raise RuntimeError(
                    f"VPM PDF download error for {mail_item_id}: "
                    f"{error_data.get('error', content_type)}"
                )
            except (ValueError, RuntimeError):
                raise RuntimeError(
                    f"VPM PDF download returned unexpected content type '{content_type}' "
                    f"for mail item {mail_item_id}"
                )

        if not resp.content:
            raise RuntimeError(f"VPM returned empty PDF for mail item {mail_item_id}")

        log.debug(f"Downloaded PDF for VPM mail item {mail_item_id}: {len(resp.content)} bytes")
        return resp.content

    def mark_as_processed(self, mail_item_id: str) -> None:
        """
        Mark a mail item as viewed/processed in VPM.

        Args:
            mail_item_id: VPM mail item ID.
        """
        data = self._api_call("doMarkAsViewed", mailItemID=mail_item_id)
        if not data.get("success"):
            raise RuntimeError(
                f"VPM doMarkAsViewed failed for {mail_item_id}: "
                f"{data.get('error', 'unknown error')}"
            )
        log.debug(f"Marked VPM mail item {mail_item_id} as viewed")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_vpm_date(date_str: str) -> str:
    """
    Parse a VPM date string to ISO YYYY-MM-DD.

    VPM may return dates in MM/DD/YYYY, YYYY-MM-DD, or datetime formats.
    Falls back to today if unparseable.
    """
    if not date_str:
        return date.today().isoformat()

    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%m/%d/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(date_str.strip(), fmt).date().isoformat()
        except ValueError:
            continue

    log.debug(f"Could not parse VPM date '{date_str}', using today")
    return date.today().isoformat()
