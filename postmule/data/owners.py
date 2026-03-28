"""
Owner registry — reads/writes owners.json.

Owner record schema:
{
  "id": "uuid",
  "name": "Alice",
  "type": "person",       # "person" | "company"
  "short_name": null,     # optional display override for badges/filenames
  "color": "#7C3AED",     # hex color for dashboard badge (optional)
  "active": true,
  "created_date": "YYYY-MM-DD"
}
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from postmule.data._io import atomic_write

OWNER_TYPES = ("person", "company")


def _owners_file(data_dir: Path) -> Path:
    return data_dir / "owners.json"


def load_owners(data_dir: Path, *, include_inactive: bool = False) -> list[dict[str, Any]]:
    """Load owners. Active only by default; pass include_inactive=True for all records."""
    path = _owners_file(data_dir)
    if not path.exists():
        return []
    owners: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    if not include_inactive:
        owners = [o for o in owners if o.get("active", True)]
    return owners


def save_owners(data_dir: Path, owners: list[dict[str, Any]]) -> None:
    atomic_write(_owners_file(data_dir), json.dumps(owners, indent=2, ensure_ascii=False))


def add_owner(
    data_dir: Path,
    name: str,
    owner_type: str = "person",
    *,
    short_name: str | None = None,
    color: str | None = None,
) -> dict[str, Any]:
    owners = load_owners(data_dir, include_inactive=True)
    owner: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "name": name,
        "type": owner_type if owner_type in OWNER_TYPES else "person",
        "short_name": short_name,
        "color": color,
        "active": True,
        "created_date": date.today().isoformat(),
    }
    owners.append(owner)
    save_owners(data_dir, owners)
    return owner


def get_owner(data_dir: Path, owner_id: str) -> dict[str, Any] | None:
    """Return a single owner by ID (searches active and inactive). None if not found."""
    for owner in load_owners(data_dir, include_inactive=True):
        if owner["id"] == owner_id:
            return owner
    return None


def update_owner(data_dir: Path, owner_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    """Update writable fields on an owner record. Returns updated owner or None if not found."""
    owners = load_owners(data_dir, include_inactive=True)
    for owner in owners:
        if owner["id"] != owner_id:
            continue
        for key, value in fields.items():
            if key in ("id", "created_date"):
                continue
            if key == "type" and value not in OWNER_TYPES:
                continue
            owner[key] = value
        save_owners(data_dir, owners)
        return owner
    return None


def deactivate_owner(data_dir: Path, owner_id: str) -> bool:
    """Soft-delete: set active=False. Returns True if found."""
    owners = load_owners(data_dir, include_inactive=True)
    for owner in owners:
        if owner["id"] == owner_id:
            owner["active"] = False
            save_owners(data_dir, owners)
            return True
    return False


def resolve_owner_ids(recipients: list[str], owners: list[dict[str, Any]]) -> list[str]:
    """
    Map LLM-extracted recipient strings to owner IDs via exact, case-insensitive
    name or short_name match. Only active owners are considered.
    Unmatched strings are silently dropped. Returns deduplicated list of owner IDs.
    """
    matched: list[str] = []
    active = [o for o in owners if o.get("active", True)]
    for recipient in recipients:
        r_lower = recipient.strip().lower()
        for owner in active:
            if owner.get("name", "").lower() == r_lower:
                if owner["id"] not in matched:
                    matched.append(owner["id"])
                break
            sn = owner.get("short_name") or ""
            if sn and sn.lower() == r_lower:
                if owner["id"] not in matched:
                    matched.append(owner["id"])
                break
    return matched
