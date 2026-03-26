"""
Outlook 365 email provider — stub (not yet implemented).

Covers Microsoft 365 / work accounts (outlook.office365.com).
Implementation will use the Microsoft Graph API with OAuth2.

Config example:
    email:
      providers:
        - service: outlook_365
          enabled: true
          role: mailbox_notifications
          address: you@yourcompany.com
"""

from __future__ import annotations

SERVICE_KEY = "outlook_365"
DISPLAY_NAME = "Outlook / Microsoft 365"


class Outlook365Provider:
    """
    Outlook 365 (Microsoft 365 / work accounts) email provider.

    Not yet implemented. Configure service: outlook_365 in config.yaml
    once this provider is available.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "Outlook 365 provider is not yet implemented. "
            "Use service: gmail or service: imap in config.yaml for now."
        )

    def list_unprocessed_emails(self, sender_filter: str, subject_filter: str) -> list:
        raise NotImplementedError("Outlook 365 provider is not yet implemented.")

    def list_emails_with_pdf_attachments(self) -> list:
        raise NotImplementedError("Outlook 365 provider is not yet implemented.")

    def mark_as_processed(self, message_id: str) -> None:
        raise NotImplementedError("Outlook 365 provider is not yet implemented.")
