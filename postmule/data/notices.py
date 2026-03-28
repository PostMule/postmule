"""
Notices JSON data layer — reads/writes notices_YYYY.json.

Schema for each notice record:
{
  "id": "uuid",
  "date_received": "YYYY-MM-DD",
  "date_processed": "YYYY-MM-DD",
  "sender": "IRS",
  "recipients": ["Alice"],
  "summary": "...",
  "drive_file_id": "...",
  "filename": "2025-01-15_Alice_IRS_Notice.pdf",
  "owner_ids": []          # resolved owner UUIDs (from owners.json); [] = unassigned
}
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from postmule.data._io import atomic_write, recent_years, year_from

_HEADERS = [
    "ID", "Date Received", "Date Processed", "Sender", "Recipients",
    "Summary", "Drive File ID", "Filename",
]


def _data_file(data_dir: Path, year: int | None = None) -> Path:
    y = year or date.today().year
    return data_dir / f"notices_{y}.json"


def load_notices(data_dir: Path, year: int | None = None) -> list[dict[str, Any]]:
    path = _data_file(data_dir, year)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_notices(data_dir: Path, notices: list[dict[str, Any]], year: int | None = None) -> None:
    path = _data_file(data_dir, year)
    atomic_write(path, json.dumps(notices, indent=2, ensure_ascii=False))


def add_notice(data_dir: Path, notice: dict[str, Any]) -> dict[str, Any]:
    year = year_from(notice.get("date_received", ""))
    notices = load_notices(data_dir, year)
    if "id" not in notice or not notice["id"]:
        notice["id"] = str(uuid.uuid4())
    notices.append(notice)
    save_notices(data_dir, notices, year)
    return notice


def find_notice(data_dir: Path, notice_id: str) -> dict[str, Any] | None:
    for year in recent_years():
        for notice in load_notices(data_dir, year):
            if notice.get("id") == notice_id:
                return notice
    return None


def set_entity_override(data_dir: Path, notice_id: str, entity_id: str) -> bool:
    """Set entity_override_id on a notice record. Returns True if found and updated."""
    for year in recent_years():
        notices = load_notices(data_dir, year)
        for notice in notices:
            if notice.get("id") == notice_id:
                notice["entity_override_id"] = entity_id
                save_notices(data_dir, notices, year)
                return True
    return False


def set_owner_ids(data_dir: Path, notice_id: str, owner_ids: list[str]) -> bool:
    """Set owner_ids on a notice record. Returns True if found."""
    for year in recent_years():
        notices = load_notices(data_dir, year)
        for notice in notices:
            if notice.get("id") == notice_id:
                notice["owner_ids"] = owner_ids
                save_notices(data_dir, notices, year)
                return True
    return False


def set_category_override(data_dir: Path, notice_id: str, category: str) -> bool:
    """Set category_override on a notice record. Returns True if found and updated."""
    for year in recent_years():
        notices = load_notices(data_dir, year)
        for notice in notices:
            if notice.get("id") == notice_id:
                notice["category_override"] = category
                save_notices(data_dir, notices, year)
                return True
    return False


def to_sheet_rows(notices: list[dict[str, Any]]) -> list[list[Any]]:
    rows = [_HEADERS]
    for n in notices:
        rows.append([
            n.get("id", ""),
            n.get("date_received", ""),
            n.get("date_processed", ""),
            n.get("sender", ""),
            ", ".join(n.get("recipients", [])),
            n.get("summary", ""),
            n.get("drive_file_id", ""),
            n.get("filename", ""),
        ])
    return rows


