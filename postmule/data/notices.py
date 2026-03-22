"""
Notices JSON data layer — reads/writes notices_YYYY.json.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import date
from pathlib import Path
from typing import Any

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
    _atomic_write(path, json.dumps(notices, indent=2, ensure_ascii=False))


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def add_notice(data_dir: Path, notice: dict[str, Any]) -> dict[str, Any]:
    year = _year_from(notice.get("date_received", ""))
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


def _year_from(date_str: str) -> int:
    try:
        return int(date_str[:4])
    except (ValueError, TypeError):
        return date.today().year
