"""
Email notification provider — thin wrapper used by the summary agent.

This wraps the SMTP send logic so it can be swapped with other
notification providers (Pushover, Slack, etc.) in the future.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("postmule.notifications.email")


class EmailNotifier:
    """
    Send notifications via SMTP email.

    smtp_config keys:
      host, port, username, password, from_address
    """

    def __init__(self, smtp_config: dict[str, Any], from_address: str = "") -> None:
        self.smtp_config = smtp_config
        self.smtp_config.setdefault("from_address", from_address)

    def send(self, to: str, subject: str, html: str) -> None:
        from postmule.agents.summary import _send_email
        _send_email(self.smtp_config, to, subject, html)
        log.info(f"Sent email to {to}: {subject}")
