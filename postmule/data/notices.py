"""
Notices JSON data layer — reads/writes notices_YYYY.json.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from postmule.data._io import atomic_write, year_from

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


