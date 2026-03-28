"""
Airtable spreadsheet provider.

Uses the Airtable REST API v0 with a Personal Access Token (PAT).

Config example:
    spreadsheet:
      providers:
        - service: airtable
          enabled: true
          base_id: appXXXXXXXXXXXXXX
          workbook_name: PostMule
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("postmule.spreadsheet.airtable")

SERVICE_KEY = "airtable"
DISPLAY_NAME = "Airtable"

_API_BASE = "https://api.airtable.com/v0"
_META_BASE = "https://api.airtable.com/v0/meta"
_BATCH_SIZE = 10  # Airtable max records per request


class AirtableProvider:
    """
    Airtable spreadsheet provider via the Airtable REST API v0.

    Args:
        access_token: Airtable Personal Access Token (PAT).
        base_id:      Airtable base ID (e.g. 'appXXXXXXXXXXXXXX').
        workbook_name: Display name — unused in API calls, kept for config consistency.
    """

    def __init__(
        self,
        access_token: str,
        base_id: str,
        workbook_name: str = "PostMule",
    ) -> None:
        self.access_token = access_token
        self.base_id = base_id
        self.workbook_name = workbook_name

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _get(self, url: str, **params) -> dict:
        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError("requests is not installed. Run: pip install requests")
        resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, url: str, body: dict) -> dict:
        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError("requests is not installed. Run: pip install requests")
        resp = requests.post(url, headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, url: str, params: dict | None = None) -> dict:
        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError("requests is not installed. Run: pip install requests")
        resp = requests.delete(url, headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def health_check(self):
        """Return a HealthResult by calling the Airtable whoami endpoint."""
        from postmule.providers import HealthResult
        try:
            data = self._get(f"{_META_BASE}/whoami")
            user_id = data.get("id", "unknown")
            return HealthResult(
                ok=True,
                status="ok",
                message=f"Airtable connected (user: {user_id})",
            )
        except Exception as exc:
            return HealthResult(ok=False, status="error", message=str(exc))

    def get_or_create_workbook(self, drive_folder_id: str | None = None) -> str:
        """
        Verify the configured Airtable base is accessible; return its base ID.

        Airtable bases must be created manually via the UI — this method confirms
        the base exists and returns the base_id as the workbook identifier.
        """
        self._get(f"{_META_BASE}/bases/{self.base_id}/tables")
        log.debug(f"Airtable base verified: {self.base_id}")
        return self.base_id

    def write_sheet(self, sheet_name: str, rows: list[list[Any]]) -> None:
        """
        Write rows to an Airtable table, replacing all existing records.

        The table is created if it does not exist. rows[0] is used as field names.
        Existing records are deleted before new ones are created.

        Args:
            sheet_name: Airtable table name.
            rows:       List of rows; rows[0] is headers, rows[1:] are data.
        """
        if not rows:
            return

        headers = [str(h) for h in rows[0]]
        data_rows = rows[1:]

        table_id = self._get_or_create_table(sheet_name, headers)
        self._delete_all_records(table_id)

        if data_rows:
            self._create_records(table_id, headers, data_rows)

        log.debug(f"Airtable table '{sheet_name}': wrote {len(data_rows)} records")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_table(self, name: str, fields: list[str]) -> str:
        """Return table ID for the named table, creating it with text fields if needed."""
        data = self._get(f"{_META_BASE}/bases/{self.base_id}/tables")
        for table in data.get("tables", []):
            if table.get("name") == name:
                return table["id"]

        body = {
            "name": name,
            "fields": [{"name": f, "type": "singleLineText"} for f in fields],
        }
        result = self._post(f"{_META_BASE}/bases/{self.base_id}/tables", body)
        log.info(f"Created Airtable table: {name}")
        return result["id"]

    def _delete_all_records(self, table_id: str) -> None:
        """Delete all records from a table in batches of 10."""
        while True:
            data = self._get(
                f"{_API_BASE}/{self.base_id}/{table_id}",
                **{"fields[]": [], "maxRecords": 100},
            )
            records = data.get("records", [])
            if not records:
                break
            for i in range(0, len(records), _BATCH_SIZE):
                batch_ids = [r["id"] for r in records[i:i + _BATCH_SIZE]]
                self._delete(
                    f"{_API_BASE}/{self.base_id}/{table_id}",
                    params={"records[]": batch_ids},
                )

    def _create_records(self, table_id: str, headers: list[str], data_rows: list[list[Any]]) -> None:
        """Batch-create records from data rows (10 per request)."""
        for i in range(0, len(data_rows), _BATCH_SIZE):
            batch = data_rows[i:i + _BATCH_SIZE]
            records = [
                {
                    "fields": {
                        headers[j]: str(cell) if cell is not None else ""
                        for j, cell in enumerate(row)
                        if j < len(headers)
                    }
                }
                for row in batch
            ]
            self._post(f"{_API_BASE}/{self.base_id}/{table_id}", {"records": records})
