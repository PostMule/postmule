"""
Run log data layer — records the result of every PostMule run.

Schema per entry:
{
  "run_id": "uuid",
  "start_time": "YYYY-MM-DDTHH:MM:SS",
  "end_time": "YYYY-MM-DDTHH:MM:SS",
  "status": "success" | "partial" | "failed",
  "emails_found": 5,
  "pdfs_processed": 5,
  "bills": 2,
  "notices": 1,
  "forward_to_me": 0,
  "junk": 1,
  "needs_review": 1,
  "errors": [],
  "api_usage": {}
}
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


def _run_log_file(data_dir: Path) -> Path:
    return data_dir / "run_log.json"


def load_run_log(data_dir: Path) -> list[dict[str, Any]]:
    path = _run_log_file(data_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def append_run(data_dir: Path, entry: dict[str, Any]) -> None:
    log = load_run_log(data_dir)
    if "run_id" not in entry:
        entry["run_id"] = str(uuid.uuid4())
    log.append(entry)
    # Keep last 365 entries
    if len(log) > 365:
        log = log[-365:]
    path = _run_log_file(data_dir)
    _atomic_write(path, json.dumps(log, indent=2, ensure_ascii=False))


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


def get_last_run(data_dir: Path) -> dict[str, Any] | None:
    log = load_run_log(data_dir)
    return log[-1] if log else None


def to_sheet_rows(run_log: list[dict[str, Any]]) -> list[list[Any]]:
    headers = [
        "Run ID", "Start Time", "End Time", "Status",
        "Emails Found", "PDFs Processed", "Bills", "Notices",
        "ForwardToMe", "Junk", "NeedsReview", "Errors",
    ]
    rows = [headers]
    for r in reversed(run_log):  # most recent first
        rows.append([
            r.get("run_id", ""),
            r.get("start_time", ""),
            r.get("end_time", ""),
            r.get("status", ""),
            r.get("emails_found", 0),
            r.get("pdfs_processed", 0),
            r.get("bills", 0),
            r.get("notices", 0),
            r.get("forward_to_me", 0),
            r.get("junk", 0),
            r.get("needs_review", 0),
            "; ".join(r.get("errors", [])),
        ])
    return rows
