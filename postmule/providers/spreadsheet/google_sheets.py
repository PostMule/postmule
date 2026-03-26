"""
Google Sheets provider — writes generated views from JSON data.

Sheets are NEVER the source of truth. They are rebuilt from JSON on demand.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("postmule.spreadsheet.sheets")

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsProvider:
    """
    Google Sheets API provider.

    Args:
        credentials:   google.oauth2.credentials.Credentials object (from build_google_credentials()).
        workbook_name: Name of the PostMule Sheets workbook.
    """

    def __init__(self, credentials: Any, workbook_name: str = "PostMule") -> None:
        self.credentials = credentials
        self.workbook_name = workbook_name
        self._service = None
        self._spreadsheet_id: str | None = None

    def _get_service(self):
        if self._service is None:
            from googleapiclient.discovery import build  # type: ignore[import]
            self._service = build("sheets", "v4", credentials=self.credentials)
        return self._service

    def health_check(self):
        """Return a HealthResult indicating whether Sheets credentials are valid."""
        from postmule.providers import HealthResult
        try:
            self._get_service()  # triggers OAuth; raises if creds invalid
            return HealthResult(ok=True, status="ok", message="Sheets connected")
        except Exception as exc:
            return HealthResult(ok=False, status="error", message=str(exc))

    def get_or_create_workbook(self, drive_folder_id: str | None = None) -> str:
        """
        Find or create the PostMule Google Sheets workbook.

        Returns:
            Spreadsheet ID.
        """
        if self._spreadsheet_id:
            return self._spreadsheet_id

        # Try to find existing workbook via Drive search
        try:
            from googleapiclient.discovery import build  # type: ignore[import]
            drive_svc = build("drive", "v3", credentials=self.credentials)
            query = (
                f"name='{self.workbook_name}' "
                f"and mimeType='application/vnd.google-apps.spreadsheet' "
                f"and trashed=false"
            )
            results = drive_svc.files().list(q=query, fields="files(id)").execute()
            files = results.get("files", [])
            if files:
                self._spreadsheet_id = files[0]["id"]
                log.debug(f"Found existing Sheets workbook: {self._spreadsheet_id}")
                return self._spreadsheet_id
        except Exception as exc:
            log.debug(f"Drive search for workbook failed: {exc}")

        # Create new workbook
        svc = self._get_service()
        sheet_names = [
            "Bills", "Notices", "ForwardToMe", "Entities", "SenderDirectory",
            "BankTransactions", "PendingEntityMatches", "PendingBillMatches",
            "RunLog", "APIUsage",
        ]
        body = {
            "properties": {"title": self.workbook_name},
            "sheets": [{"properties": {"title": name}} for name in sheet_names],
        }
        spreadsheet = svc.spreadsheets().create(body=body).execute()
        self._spreadsheet_id = spreadsheet["spreadsheetId"]
        log.info(f"Created Sheets workbook: {self.workbook_name} ({self._spreadsheet_id})")
        return self._spreadsheet_id

    def write_sheet(self, sheet_name: str, rows: list[list[Any]]) -> None:
        """
        Overwrite a sheet with new data (header row + data rows).

        Args:
            sheet_name: Name of the sheet tab.
            rows:       List of rows, each row is a list of cell values.
                        First row should be headers.
        """
        svc = self._get_service()
        spreadsheet_id = self._spreadsheet_id
        if not spreadsheet_id:
            raise RuntimeError("Call get_or_create_workbook() before writing sheets.")

        # Clear existing content
        svc.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1:ZZ",
        ).execute()

        if not rows:
            return

        svc.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()
        log.debug(f"Updated sheet '{sheet_name}': {len(rows)-1} data rows")

    def append_row(self, sheet_name: str, row: list[Any]) -> None:
        """Append a single row to a sheet."""
        svc = self._get_service()
        svc.spreadsheets().values().append(
            spreadsheetId=self._spreadsheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
