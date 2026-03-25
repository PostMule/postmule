"""
Proton Mail email provider — stub (not yet implemented).

Uses Proton Bridge (localhost IMAP proxy) so no cloud credentials are needed.
PostMule pre-fills Proton Bridge defaults: host=127.0.0.1, port=1143.

Config example:
    email:
      providers:
        - service: proton
          enabled: true
          role: mailbox_notifications
          address: you@proton.me
          # bridge_host and bridge_port default to 127.0.0.1 / 1143
"""

from __future__ import annotations

SERVICE_KEY = "proton"
DISPLAY_NAME = "Proton Mail"

# Proton Bridge IMAP defaults — pre-filled when service: proton is selected
BRIDGE_DEFAULT_HOST = "127.0.0.1"
BRIDGE_DEFAULT_PORT = 1143


class ProtonMailProvider:
    """
    Proton Mail provider via Proton Bridge (local IMAP proxy).

    Not yet implemented. Configure service: proton in config.yaml
    once this provider is available. Requires Proton Bridge to be running locally.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "Proton Mail provider is not yet implemented. "
            "Use service: gmail or service: imap in config.yaml for now. "
            "When implemented, requires Proton Bridge running at "
            f"{BRIDGE_DEFAULT_HOST}:{BRIDGE_DEFAULT_PORT}."
        )

    def list_unprocessed_emails(self, sender_filter: str, subject_filter: str) -> list:
        raise NotImplementedError("Proton Mail provider is not yet implemented.")

    def list_emails_with_pdf_attachments(self) -> list:
        raise NotImplementedError("Proton Mail provider is not yet implemented.")

    def mark_as_processed(self, message_id: str) -> None:
        raise NotImplementedError("Proton Mail provider is not yet implemented.")
