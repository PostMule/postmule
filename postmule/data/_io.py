"""
Shared I/O utilities for the data layer.

Imported by bills, notices, forward_to_me, entities, and run_log — do not
add anything domain-specific here.
"""

from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path


def atomic_write(path: Path, text: str) -> None:
    """Write *text* to *path* atomically via a sibling temp file + os.replace()."""
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


def year_from(date_str: str) -> int:
    """Extract the year from a YYYY-MM-DD string, defaulting to today's year."""
    try:
        if not date_str or len(date_str) < 4:
            return date.today().year
        return int(date_str[:4])
    except (ValueError, TypeError):
        return date.today().year


def recent_years(n: int = 3) -> list[int]:
    """Return the last *n* calendar years, most recent first."""
    current = date.today().year
    return list(range(current, current - n, -1))
