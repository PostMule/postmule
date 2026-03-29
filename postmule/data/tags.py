"""Tag registry — reads/writes tags.json (list of all ever-used tag names)."""

from __future__ import annotations

import json
from pathlib import Path

_FILE = "tags.json"


def load_tags(data_dir: Path) -> list[str]:
    """Return sorted list of all known tag names."""
    path = data_dir / _FILE
    if not path.exists():
        return []
    try:
        return sorted(set(json.loads(path.read_text("utf-8"))))
    except Exception:
        return []


def save_tags(data_dir: Path, tags: list[str]) -> None:
    (data_dir / _FILE).write_text(
        json.dumps(sorted(set(tags)), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def add_to_registry(data_dir: Path, tag: str) -> None:
    """Add a tag to the registry if not already present."""
    tag = tag.strip().lower()
    if not tag:
        return
    existing = load_tags(data_dir)
    if tag not in existing:
        save_tags(data_dir, existing + [tag])
