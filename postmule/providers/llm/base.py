"""
LLM provider base — shared types and Protocol for all LLM backends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from postmule.providers import HealthResult


@dataclass
class ClassificationResult:
    category: str
    confidence: float
    sender: str | None
    recipients: list[str]
    amount_due: float | None
    due_date: str | None
    account_number: str | None
    summary: str
    statement_date: str | None = None
    ach_descriptor: str | None = None
    tokens_used: int = 0
    raw_response: str = ""


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol that any PostMule LLM backend must satisfy."""

    def classify(
        self,
        ocr_text: str,
        known_names: list[str] | None = None,
        dry_run: bool = False,
    ) -> ClassificationResult:
        ...

    def health_check(self) -> HealthResult:
        ...
