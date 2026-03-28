"""
Shared Microsoft Graph API email logic for Outlook 365 and Outlook.com providers.

Both providers use identical Graph API calls — the only difference is the OAuth
authority used to obtain the access token (handled outside this module).
"""

from __future__ import annotations

import logging

from postmule.providers.email.base import EmailMessage

log = logging.getLogger("postmule.email.graph")

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_PAGE_SIZE = 50


class GraphEmailProvider:
    """
    Shared implementation for Outlook 365 and Outlook.com providers.

    Uses the Microsoft Graph API with a bearer access token.
    Token refresh / OAuth dance is handled by the caller (connections setup page).
    """

    def __init__(
        self,
        access_token: str,
        processed_category: str = "PostMule",
        default_sender_filter: str = "",
        default_subject_filter: str = "",
    ) -> None:
        self.access_token = access_token
        self.processed_category = processed_category
        self.default_sender_filter = default_sender_filter
        self.default_subject_filter = default_subject_filter

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, **params) -> dict:
        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError("requests is not installed. Run: pip install requests")
        resp = requests.get(f"{_GRAPH_BASE}{path}", headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, body: dict) -> None:
        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError("requests is not installed. Run: pip install requests")
        resp = requests.patch(f"{_GRAPH_BASE}{path}", headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()

    def health_check(self):
        """Return a HealthResult by calling /me on the Graph API."""
        from postmule.providers import HealthResult
        try:
            data = self._get("/me", select="displayName,mail")
            name = data.get("displayName") or data.get("mail", "unknown")
            return HealthResult(ok=True, status="ok", message=f"Microsoft Graph connected ({name})")
        except Exception as exc:
            return HealthResult(ok=False, status="error", message=str(exc))

    def list_unprocessed_emails(
        self,
        sender_filter: str = "",
        subject_filter: str = "",
    ) -> list[EmailMessage]:
        """Return unread emails NOT already categorised as PostMule."""
        sender = sender_filter or self.default_sender_filter
        subject = subject_filter or self.default_subject_filter
        filter_expr = _build_graph_filter(sender, subject, self.processed_category)
        return self._fetch_messages(filter_expr)

    def list_emails_with_pdf_attachments(self) -> list[EmailMessage]:
        """Return unprocessed emails that have at least one PDF attachment."""
        filter_expr = _build_graph_filter("", "", self.processed_category)
        all_emails = self._fetch_messages(filter_expr)
        # hasAttachments=true filter from Graph — but we verify PDF specifically
        return [e for e in all_emails if e.attachments]

    def mark_as_processed(self, message_id: str) -> None:
        """Apply the PostMule category to the message, marking it as processed."""
        try:
            self._patch(
                f"/me/messages/{message_id}",
                {"categories": [self.processed_category]},
            )
            log.debug(f"Marked message {message_id[:16]}... as processed")
        except Exception as exc:
            log.error(f"mark_as_processed failed for {message_id[:16]}...: {exc}")
            raise

    def _fetch_messages(self, filter_expr: str) -> list[EmailMessage]:
        results: list[EmailMessage] = []
        path = "/me/messages"
        params = {
            "$filter": filter_expr,
            "$select": "id,subject,receivedDateTime,from,hasAttachments",
            "$top": _PAGE_SIZE,
        }

        while True:
            try:
                data = self._get(path, **params)
            except Exception as exc:
                log.error(f"Graph API message fetch failed: {exc}")
                break

            for raw in data.get("value", []):
                msg = _parse_message(raw)
                if msg.attachments is not None and raw.get("hasAttachments"):
                    # Load attachment data
                    try:
                        msg = self._load_attachments(msg)
                    except Exception as exc:
                        log.warning(f"Failed to load attachments for {msg.message_id[:16]}...: {exc}")
                results.append(msg)

            next_link = data.get("@odata.nextLink")
            if not next_link:
                break
            # nextLink is a full URL — extract relative path + params
            path = next_link.replace(_GRAPH_BASE, "")
            params = {}

        log.info(f"Graph API returned {len(results)} messages")
        return results

    def _load_attachments(self, msg: EmailMessage) -> EmailMessage:
        """Replace the attachments list with actual data for PDF attachments."""
        attachments = []
        data = self._get(f"/me/messages/{msg.message_id}/attachments")
        for att in data.get("value", []):
            name = att.get("name", "")
            if name.lower().endswith(".pdf"):
                import base64
                content = att.get("contentBytes", "")
                payload = base64.b64decode(content) if content else b""
                attachments.append({"name": name, "data": payload})
        return EmailMessage(
            message_id=msg.message_id,
            subject=msg.subject,
            received_date=msg.received_date,
            sender=msg.sender,
            attachments=attachments,
        )


def _build_graph_filter(sender: str, subject: str, processed_category: str) -> str:
    """Build an OData filter for the Graph messages endpoint."""
    parts = [
        "isRead eq false",
        f"not categories/any(c:c eq '{processed_category}')",
    ]
    if sender:
        parts.append(f"from/emailAddress/address eq '{sender}'")
    if subject:
        parts.append(f"contains(subject, '{subject}')")
    return " and ".join(parts)


def _parse_message(raw: dict) -> EmailMessage:
    msg_id = raw.get("id", "")
    subject = raw.get("subject", "")
    from_obj = raw.get("from", {}) or {}
    addr_obj = from_obj.get("emailAddress", {}) or {}
    sender = addr_obj.get("address", addr_obj.get("name", ""))
    received = raw.get("receivedDateTime", "")[:10]  # YYYY-MM-DD
    return EmailMessage(
        message_id=msg_id,
        subject=subject,
        received_date=received,
        sender=sender,
        attachments=[],
    )
