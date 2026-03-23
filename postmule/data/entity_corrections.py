"""
Entity correction log — records when a user manually overrides an entity
association on a mail item.

Schema for each correction record:
{
  "id": "uuid",
  "mail_id": "uuid",
  "mail_type": "Bill" | "Notice" | "ForwardToMe",
  "original_sender": "ATTT",
  "corrected_entity_id": "uuid",
  "corrected_entity_name": "AT&T",
  "added_alias": true,
  "correction_date": "YYYY-MM-DD"
}

The log is append-only. Developer reviews it periodically to:
- Identify missing aliases (same original_sender → same entity repeatedly)
- Spot logic issues (same original_sender → different entities across corrections)
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from postmule.data._io import atomic_write


def _corrections_file(data_dir: Path) -> Path:
    return data_dir / "entity_corrections.json"


def load_corrections(data_dir: Path) -> list[dict[str, Any]]:
    path = _corrections_file(data_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def log_correction(
    data_dir: Path,
    mail_id: str,
    mail_type: str,
    original_sender: str,
    corrected_entity_id: str,
    corrected_entity_name: str,
    added_alias: bool = False,
) -> dict[str, Any]:
    """Append a correction record. Returns the new record."""
    corrections = load_corrections(data_dir)
    record: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "mail_id": mail_id,
        "mail_type": mail_type,
        "original_sender": original_sender,
        "corrected_entity_id": corrected_entity_id,
        "corrected_entity_name": corrected_entity_name,
        "added_alias": added_alias,
        "correction_date": date.today().isoformat(),
    }
    corrections.append(record)
    atomic_write(_corrections_file(data_dir), json.dumps(corrections, indent=2, ensure_ascii=False))
    return record


def correction_summary(data_dir: Path) -> list[dict[str, Any]]:
    """
    Return corrections grouped by original_sender, sorted by frequency descending.
    Each entry: {"original_sender", "count", "entity_names": [list of distinct targets]}
    """
    corrections = load_corrections(data_dir)
    groups: dict[str, dict[str, Any]] = {}
    for c in corrections:
        sender = c.get("original_sender", "")
        if sender not in groups:
            groups[sender] = {"original_sender": sender, "count": 0, "entity_names": []}
        groups[sender]["count"] += 1
        name = c.get("corrected_entity_name", "")
        if name and name not in groups[sender]["entity_names"]:
            groups[sender]["entity_names"].append(name)
    return sorted(groups.values(), key=lambda g: g["count"], reverse=True)
