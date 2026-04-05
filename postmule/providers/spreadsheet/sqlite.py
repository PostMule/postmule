"""
SQLite spreadsheet provider — local view layer backed by a SQLite database.

Each PostMule sheet becomes a table in a single .db file.
Like all spreadsheet providers, this is a generated view — rebuilt from JSON
on each run. JSON files remain the source of truth.

Config example:
    spreadsheet:
      providers:
        - service: sqlite
          enabled: true
          db_name: "postmule.db"
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

log = logging.getLogger("postmule.spreadsheet.sqlite")

SERVICE_KEY = "sqlite"
DISPLAY_NAME = "SQLite (local)"


class SqliteSpreadsheetProvider:
    """
    SQLite-backed spreadsheet provider.

    Stores all PostMule view data in a single .db file on disk.
    The first row of each write_sheet call is treated as column headers.
    Each write_sheet call drops and recreates the table — rows are always
    rebuilt from the JSON source of truth.

    Args:
        db_path: Absolute path to the SQLite .db file.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_or_create_workbook(self, drive_folder_id: str | None = None) -> str:
        """
        Open (or create) the SQLite database file.

        The drive_folder_id parameter is ignored — SQLite uses a local path.

        Returns:
            Absolute path to the .db file as a string (used as workbook_id).
        """
        conn = sqlite3.connect(self.db_path)
        conn.close()
        log.debug(f"SQLite workbook ready: {self.db_path}")
        return str(self.db_path)

    def write_sheet(self, sheet_name: str, rows: list[list[Any]]) -> None:
        """
        Write rows to a SQLite table. First row = column headers.

        Drops and recreates the table on every write so the view always
        reflects the current state of the JSON source of truth.

        Empty rows list is a no-op.
        """
        if not rows:
            return

        table = _safe_identifier(sheet_name)
        headers = [_safe_identifier(str(h)) for h in rows[0]]
        data_rows = rows[1:]

        col_defs = ", ".join(f'"{h}" TEXT' for h in headers)
        placeholders = ", ".join("?" for _ in headers)

        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(f'DROP TABLE IF EXISTS "{table}"')
            cur.execute(f'CREATE TABLE "{table}" ({col_defs})')
            if data_rows:
                normalized = [_pad_row(row, len(headers)) for row in data_rows]
                cur.executemany(
                    f'INSERT INTO "{table}" VALUES ({placeholders})',
                    normalized,
                )
            conn.commit()
            log.debug(f"SQLite: wrote {len(data_rows)} rows to '{table}'")
        finally:
            conn.close()

    def health_check(self):
        from postmule.providers import HealthResult
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("SELECT 1")
            conn.close()
            return HealthResult(ok=True, status="ok", message=f"SQLite at {self.db_path}")
        except Exception as exc:
            return HealthResult(ok=False, status="error", message=str(exc))


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _safe_identifier(name: str) -> str:
    """Replace characters that are unsafe in SQL identifiers with underscores."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in name)


def _pad_row(row: list[Any], width: int) -> list[str]:
    """Trim or pad a row to exactly `width` columns, converting all values to str."""
    result = [str(v) if v is not None else "" for v in row]
    if len(result) < width:
        result += [""] * (width - len(result))
    return result[:width]
