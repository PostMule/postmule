"""
No-op spreadsheet provider — disables the spreadsheet view entirely.

Use this when you don't want PostMule to maintain a spreadsheet view.
JSON files remain the source of truth regardless.

Config example:
    spreadsheet:
      providers:
        - service: none
          enabled: true
"""

from __future__ import annotations

from typing import Any

SERVICE_KEY = "none"
DISPLAY_NAME = "None (disabled)"


class NoneSpreadsheetProvider:
    """
    No-op spreadsheet provider. All operations are silently skipped.

    Use service: none when you do not want a spreadsheet view.
    """

    def __init__(self, *args, **kwargs) -> None:
        pass

    def get_or_create_workbook(self, drive_folder_id: str | None = None) -> str:
        return ""

    def write_sheet(self, sheet_name: str, rows: list[list[Any]]) -> None:
        pass

    def health_check(self):
        from postmule.providers import HealthResult
        return HealthResult(ok=True, status="ok", message="Spreadsheet view disabled")
