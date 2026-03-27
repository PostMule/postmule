"""
Generic IMAP email provider — stub (not yet implemented).

Allows connecting to any IMAP-capable mail server by supplying
host, port, username, and password directly.

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

SERVICE_KEY = "imap"
DISPLAY_NAME = "Generic IMAP"


class ImapProvider:
    """
    Generic IMAP provider for any standard IMAP mail server.

    Not yet implemented. Configure service: imap in config.yaml
    once this provider is available.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "Generic IMAP provider is not yet implemented. "
            "Use service: gmail in config.yaml for now."
        )

    def list_unprocessed_emails(self, sender_filter: str, subject_filter: str) -> list:
        raise NotImplementedError("Generic IMAP provider is not yet implemented.")

    def list_emails_with_pdf_attachments(self) -> list:
        raise NotImplementedError("Generic IMAP provider is not yet implemented.")

    def mark_as_processed(self, message_id: str) -> None:
        raise NotImplementedError("Generic IMAP provider is not yet implemented.")

    def health_check(self):
        raise NotImplementedError("Generic IMAP provider is not yet implemented.")
