"""
Earth Class Mail mailbox provider — stub (not yet implemented).

Implementation will use the Earth Class Mail API or email notification
parsing to detect and download scanned PDFs.

Config example:
    mailbox:
      providers:
        - service: earth_class
          enabled: true
"""

from __future__ import annotations

SERVICE_KEY = "earth_class"
DISPLAY_NAME = "Earth Class Mail"


class EarthClassMailProvider:
    """
    Earth Class Mail physical mailbox provider.

    Not yet implemented. Configure service: earth_class in config.yaml
    once this provider is available.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "Earth Class Mail provider is not yet implemented. "
            "Use service: vpm in config.yaml for now."
        )

    def list_unprocessed_items(self) -> list:
        raise NotImplementedError("Earth Class Mail provider is not yet implemented.")

    def download_pdf(self, mail_item_id: str) -> bytes:
        raise NotImplementedError("Earth Class Mail provider is not yet implemented.")

    def mark_as_processed(self, mail_item_id: str) -> None:
        raise NotImplementedError("Earth Class Mail provider is not yet implemented.")
