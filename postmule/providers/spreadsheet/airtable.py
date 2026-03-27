"""
Airtable spreadsheet provider — stub (not yet implemented).

Implementation will use the Airtable REST API with a Personal Access Token.

Config example:
    spreadsheet:
      providers:
        - service: airtable
          enabled: true
          workbook_name: PostMule
          base_id: appXXXXXXXXXXXXXX
"""

from __future__ import annotations

from typing import Any

SERVICE_KEY = "airtable"
DISPLAY_NAME = "Airtable"


class AirtableProvider:
    """
    Airtable spreadsheet provider.

    Not yet implemented. Configure service: airtable in config.yaml
    once this provider is available.
    """

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "Airtable provider is not yet implemented. "
            "Use service: google_sheets in config.yaml for now."
        )

    def get_or_create_workbook(self, drive_folder_id: str | None = None) -> str:
        raise NotImplementedError("Airtable provider is not yet implemented.")

    def write_sheet(self, sheet_name: str, rows: list[list[Any]]) -> None:
        raise NotImplementedError("Airtable provider is not yet implemented.")

    def health_check(self):
        raise NotImplementedError("Airtable provider is not yet implemented.")
