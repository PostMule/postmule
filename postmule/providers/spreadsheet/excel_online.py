"""
Excel Online spreadsheet provider — stub (not yet implemented).

Covers Microsoft 365 Excel Online via the Microsoft Graph API.

Config example:
    spreadsheet:
      providers:
        - service: excel_online
          enabled: true
          workbook_name: PostMule
"""

from __future__ import annotations

from typing import Any

SERVICE_KEY = "excel_online"
DISPLAY_NAME = "Excel Online"


class ExcelOnlineProvider:
    """
    Excel Online (Microsoft 365) spreadsheet provider.

    Not yet implemented. Configure service: excel_online in config.yaml
    once this provider is available.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "Excel Online provider is not yet implemented. "
            "Use service: google_sheets in config.yaml for now."
        )

    def get_or_create_workbook(self, drive_folder_id: str | None = None) -> str:
        raise NotImplementedError("Excel Online provider is not yet implemented.")

    def write_sheet(self, sheet_name: str, rows: list[list[Any]]) -> None:
        raise NotImplementedError("Excel Online provider is not yet implemented.")
