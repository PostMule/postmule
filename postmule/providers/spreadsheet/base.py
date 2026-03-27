"""
Spreadsheet provider base — Protocol for all spreadsheet backends.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from postmule.providers import HealthResult


@runtime_checkable
class SpreadsheetProvider(Protocol):
    """Protocol that any PostMule spreadsheet backend must satisfy."""

    def get_or_create_workbook(self, drive_folder_id: str | None = None) -> str:
        """Find or create the PostMule workbook; return its ID."""
        ...

    def write_sheet(self, sheet_name: str, rows: list[list[Any]]) -> None:
        """Write rows to a named sheet tab, creating it if needed."""
        ...

    def health_check(self) -> HealthResult:
        ...
