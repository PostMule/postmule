"""
Email provider base — shared types and Protocol for all email backends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from postmule.providers import HealthResult


@dataclass
class EmailMessage:
    message_id: str
    subject: str
    received_date: str   # ISO format YYYY-MM-DD
    sender: str
    attachments: list[dict] = field(default_factory=list)  # [{name, data: bytes}]


@runtime_checkable
class EmailProvider(Protocol):
    """Protocol that any PostMule email backend must satisfy."""

    def list_unprocessed_emails(
        self,
        sender_filter: str,
        subject_filter: str,
    ) -> list[EmailMessage]:
        ...

    def list_emails_with_pdf_attachments(self) -> list[EmailMessage]:
        """Return all unprocessed emails that contain at least one PDF attachment.

        Used for the bill_intake pipeline step (Phase 23).
        """
        ...

    def mark_as_processed(self, message_id: str) -> None:
        ...

    def health_check(self) -> HealthResult:
        ...
