"""
Excel Online spreadsheet provider.

Uses Microsoft 365 Excel Online via the Microsoft Graph API.
Shares OAuth2 infrastructure with the Outlook and OneDrive providers.

Config example:
    spreadsheet:
      providers:
        - service: excel_online
          enabled: true
          workbook_name: PostMule.xlsx
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("postmule.spreadsheet.excel_online")

SERVICE_KEY = "excel_online"
DISPLAY_NAME = "Excel Online"

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_DEFAULT_SHEETS = [
    "Bills", "Notices", "ForwardToMe", "Entities", "SenderDirectory",
    "BankTransactions", "PendingEntityMatches", "PendingBillMatches",
    "RunLog", "APIUsage",
]


class ExcelOnlineProvider:
    """
    Excel Online (Microsoft 365) spreadsheet provider via the Graph API.

    Args:
        access_token:  OAuth2 bearer token (shared with Outlook/OneDrive providers).
        workbook_name: Name of the Excel file in OneDrive (default: 'PostMule.xlsx').
        folder_id:     OneDrive folder item ID. If None, the workbook is placed at root.
    """

    def __init__(
        self,
        access_token: str,
        workbook_name: str = "PostMule.xlsx",
        folder_id: str | None = None,
    ) -> None:
        self.access_token = access_token
        self.workbook_name = workbook_name
        self.folder_id = folder_id
        self._item_id: str | None = None

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, **params) -> dict:
        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError("requests is not installed. Run: pip install requests")
        resp = requests.get(f"{_GRAPH_BASE}{path}", headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError("requests is not installed. Run: pip install requests")
        resp = requests.post(f"{_GRAPH_BASE}{path}", headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _patch(self, path: str, body: dict) -> dict:
        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError("requests is not installed. Run: pip install requests")
        resp = requests.patch(f"{_GRAPH_BASE}{path}", headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _put_bytes(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> dict:
        try:
            import requests  # type: ignore[import]
        except ImportError:
            raise RuntimeError("requests is not installed. Run: pip install requests")
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": content_type,
        }
        resp = requests.put(f"{_GRAPH_BASE}{path}", headers=headers, data=data, timeout=120)
        resp.raise_for_status()
        return resp.json()

    def health_check(self):
        """Return a HealthResult by calling /me/drive on the Graph API."""
        from postmule.providers import HealthResult
        try:
            data = self._get("/me/drive")
            quota = data.get("quota", {})
            used_gb = round(quota.get("used", 0) / 1e9, 2)
            return HealthResult(
                ok=True,
                status="ok",
                message=f"Excel Online connected ({used_gb} GB OneDrive used)",
            )
        except Exception as exc:
            return HealthResult(ok=False, status="error", message=str(exc))

    def get_or_create_workbook(self, drive_folder_id: str | None = None) -> str:
        """
        Find or create the PostMule Excel workbook in OneDrive.

        Searches OneDrive for the workbook by name. If not found, uploads a
        blank xlsx file generated with openpyxl.

        Returns:
            OneDrive item ID of the workbook file.
        """
        if self._item_id:
            return self._item_id

        folder = drive_folder_id or self.folder_id
        search_path = (
            f"/me/drive/items/{folder}/children" if folder else "/me/drive/root/children"
        )

        try:
            data = self._get(search_path, **{"$filter": f"name eq '{self.workbook_name}'"})
            for item in data.get("value", []):
                if item.get("name") == self.workbook_name and "file" in item:
                    self._item_id = item["id"]
                    log.debug(f"Found Excel workbook: {self.workbook_name} ({self._item_id})")
                    return self._item_id
        except Exception:
            pass

        # Create new workbook
        xlsx_bytes = _blank_xlsx(_DEFAULT_SHEETS)
        upload_path = (
            f"/me/drive/items/{folder}:/{self.workbook_name}:/content"
            if folder
            else f"/me/drive/root:/{self.workbook_name}:/content"
        )
        result = self._put_bytes(
            upload_path,
            xlsx_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self._item_id = result["id"]
        log.info(f"Created Excel workbook: {self.workbook_name} ({self._item_id})")
        return self._item_id

    def write_sheet(self, sheet_name: str, rows: list[list[Any]]) -> None:
        """
        Overwrite a worksheet with new data.

        Args:
            sheet_name: Name of the worksheet tab.
            rows:       List of rows; rows[0] is headers, rows[1:] are data.
        """
        item_id = self._item_id
        if not item_id:
            raise RuntimeError("Call get_or_create_workbook() before writing sheets.")

        self._get_or_create_worksheet(item_id, sheet_name)

        # Clear used range (ignore errors if sheet is empty)
        try:
            self._post(
                f"/me/drive/items/{item_id}/workbook/worksheets/{sheet_name}/usedRange/clear",
                {"applyTo": "Contents"},
            )
        except Exception:
            pass

        if not rows:
            return

        n_rows = len(rows)
        n_cols = max(len(r) for r in rows)
        end_col = _col_letter(n_cols)
        address = f"A1:{end_col}{n_rows}"
        padded = [list(row) + [""] * (n_cols - len(row)) for row in rows]

        self._patch(
            f"/me/drive/items/{item_id}/workbook/worksheets/{sheet_name}/range(address='{address}')",
            {"values": [[str(cell) if cell is not None else "" for cell in row] for row in padded]},
        )
        log.debug(f"Excel sheet '{sheet_name}': wrote {n_rows - 1} data rows")

    def _get_or_create_worksheet(self, item_id: str, name: str) -> None:
        """Create a worksheet if it does not already exist."""
        try:
            data = self._get(f"/me/drive/items/{item_id}/workbook/worksheets")
            for sheet in data.get("value", []):
                if sheet.get("name") == name:
                    return
        except Exception:
            pass

        try:
            self._post(
                f"/me/drive/items/{item_id}/workbook/worksheets",
                {"name": name},
            )
            log.info(f"Created Excel worksheet: {name}")
        except Exception as exc:
            log.warning(f"Could not create worksheet '{name}': {exc}")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _blank_xlsx(sheet_names: list[str]) -> bytes:
    """Generate a minimal blank xlsx workbook with the given sheet names."""
    try:
        import openpyxl  # type: ignore[import]
    except ImportError:
        raise RuntimeError("openpyxl is not installed. Run: pip install openpyxl")
    import io
    wb = openpyxl.Workbook()
    wb.active.title = sheet_names[0]
    for name in sheet_names[1:]:
        wb.create_sheet(title=name)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _col_letter(n: int) -> str:
    """Convert 1-based column number to Excel column letter (1→A, 27→AA, ...)."""
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result
