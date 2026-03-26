"""
Outlook.com email provider — stub (not yet implemented).

Covers personal Microsoft accounts (@outlook.com, @hotmail.com, @live.com).
Implementation will use the Microsoft Graph API with OAuth2.

Config example:
    email:
      providers:
        - service: outlook_com
          enabled: true
          role: mailbox_notifications
          address: you@outlook.com
"""

from __future__ import annotations

SERVICE_KEY = "outlook_com"
DISPLAY_NAME = "outlook.com / Hotmail / Live"


class OutlookComProvider:
    """
    Outlook.com (personal Microsoft accounts) email provider.

    Not yet implemented. Configure service: outlook_com in config.yaml
    once this provider is available.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "Outlook.com provider is not yet implemented. "
            "Use service: gmail or service: imap in config.yaml for now."
        )

    def list_unprocessed_emails(self, sender_filter: str, subject_filter: str) -> list:
        raise NotImplementedError("Outlook.com provider is not yet implemented.")

    def list_emails_with_pdf_attachments(self) -> list:
        raise NotImplementedError("Outlook.com provider is not yet implemented.")

    def mark_as_processed(self, message_id: str) -> None:
        raise NotImplementedError("Outlook.com provider is not yet implemented.")
