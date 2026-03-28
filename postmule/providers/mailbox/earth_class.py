"""
Earth Class Mail mailbox provider — discontinued.

Earth Class Mail was acquired by Anytime Mailbox in 2022 and shut down.
Existing Earth Class Mail customers were migrated to Anytime Mailbox.

This provider is a tombstone. It will never be implemented. If you previously
used Earth Class Mail, configure the anytime_mailbox provider instead.

See: https://www.earthclassmail.com (redirects to Anytime Mailbox)
"""

from __future__ import annotations

SERVICE_KEY = "earth_class"
DISPLAY_NAME = "Earth Class Mail (discontinued)"

_DISCONTINUED_MSG = (
    "Earth Class Mail was acquired by Anytime Mailbox in 2022 and is no longer "
    "operating. Configure service: anytime_mailbox in config.yaml instead."
)


class EarthClassMailProvider:
    """
    Earth Class Mail physical mailbox provider — discontinued.

    Earth Class Mail shut down in 2022 after being acquired by Anytime Mailbox.
    This class exists so that configs referencing 'earth_class' produce a clear
    error rather than a cryptic import failure.

    Use service: anytime_mailbox in config.yaml.
    """

    def __init__(self, *args, **kwargs) -> None:
        pass  # Allow instantiation so health_check() can report status

    def health_check(self):
        """Return a HealthResult indicating the service is discontinued."""
        from postmule.providers import HealthResult
        return HealthResult(
            ok=False,
            status="discontinued",
            message=_DISCONTINUED_MSG,
        )

    def list_unprocessed_items(self) -> list:
        raise RuntimeError(_DISCONTINUED_MSG)

    def download_pdf(self, mail_item_id: str) -> bytes:
        raise RuntimeError(_DISCONTINUED_MSG)

    def mark_as_processed(self, mail_item_id: str) -> None:
        raise RuntimeError(_DISCONTINUED_MSG)
