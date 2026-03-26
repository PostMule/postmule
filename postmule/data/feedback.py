"""Local feedback log — stores user feedback to data/feedback.json."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from postmule.data._io import atomic_write


_FEEDBACK_FILE = "feedback.json"


def append_feedback(data_dir: str | Path, entry: dict) -> dict:
    """Append one feedback entry to feedback.json and return it with an assigned id.

    The entry dict should contain: type, title, description, steps, page, version.
    An id and timestamp are added automatically.
    """
    path = Path(data_dir) / _FEEDBACK_FILE

    if path.exists():
        with open(path, encoding="utf-8") as fh:
            records: list[dict] = json.load(fh)
    else:
        records = []

    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **{k: v for k, v in entry.items() if v is not None},
    }
    records.append(entry)
    atomic_write(path, json.dumps(records, indent=2, ensure_ascii=False))
    return entry


def list_feedback(data_dir: str | Path) -> list[dict]:
    """Return all feedback entries, newest first."""
    path = Path(data_dir) / _FEEDBACK_FILE
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        records: list[dict] = json.load(fh)
    return list(reversed(records))
