"""
ForwardToMe data layer — reads/writes forward_to_me.json.
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
    "Summary", "Drive File ID", "Filename", "Forwarding Status",
]


def _data_file(data_dir: Path) -> Path:
    return data_dir / "forward_to_me.json"


def load_forward_to_me(data_dir: Path) -> list[dict[str, Any]]:
    path = _data_file(data_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_forward_to_me(data_dir: Path, items: list[dict[str, Any]]) -> None:
    path = _data_file(data_dir)
    _atomic_write(path, json.dumps(items, indent=2, ensure_ascii=False))


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


def add_item(data_dir: Path, item: dict[str, Any]) -> dict[str, Any]:
    items = load_forward_to_me(data_dir)
    if "id" not in item or not item["id"]:
        item["id"] = str(uuid.uuid4())
    if "forwarding_status" not in item:
        item["forwarding_status"] = "pending"
    items.append(item)
    save_forward_to_me(data_dir, items)
    return item


def get_pending_items(data_dir: Path) -> list[dict[str, Any]]:
    return [i for i in load_forward_to_me(data_dir) if i.get("forwarding_status") == "pending"]


def to_sheet_rows(items: list[dict[str, Any]]) -> list[list[Any]]:
    rows = [_HEADERS]
    for i in items:
        rows.append([
            i.get("id", ""),
            i.get("date_received", ""),
            i.get("date_processed", ""),
            i.get("sender", ""),
            ", ".join(i.get("recipients", [])),
            i.get("summary", ""),
            i.get("drive_file_id", ""),
            i.get("filename", ""),
            i.get("forwarding_status", "pending"),
        ])
    return rows
