"""
Traveling Mailbox mailbox provider — stub (not yet implemented).

Implementation will use the Traveling Mailbox API or email notification
parsing to detect and download scanned PDFs.

Config example:
    mailbox:
      providers:
        - service: traveling_mailbox
          enabled: true
"""

from __future__ import annotations

SERVICE_KEY = "traveling_mailbox"
DISPLAY_NAME = "Traveling Mailbox"


class TravelingMailboxProvider:
    """
    Traveling Mailbox physical mailbox provider.

    Not yet implemented. Configure service: traveling_mailbox in config.yaml
    once this provider is available.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "Traveling Mailbox provider is not yet implemented. "
            "Use service: vpm in config.yaml for now."
        )

    def list_unprocessed_items(self) -> list:
        raise NotImplementedError("Traveling Mailbox provider is not yet implemented.")

    def download_pdf(self, mail_item_id: str) -> bytes:
        raise NotImplementedError("Traveling Mailbox provider is not yet implemented.")

    def mark_as_processed(self, mail_item_id: str) -> None:
        raise NotImplementedError("Traveling Mailbox provider is not yet implemented.")
