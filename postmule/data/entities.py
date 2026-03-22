"""
Entity data layer — reads/writes entities.json and pending/entity_matches.json.

Entity record schema:
{
  "id": "uuid",
  "canonical_name": "Alice Smith",
  "type": "Person",          # Person | LLC | Trust | Corporation | Partnership | Other
  "aliases": ["Alice", "A. Smith"],
  "denied_aliases": ["Al"],
  "created_date": "YYYY-MM-DD"
}

Pending match schema:
{
  "id": "uuid",
  "proposed_name": "A. Smith",
  "match_entity_id": "uuid",
  "similarity": 0.92,
  "proposed_date": "YYYY-MM-DD",
  "auto_approve_after": "YYYY-MM-DD",
  "status": "pending" | "approved" | "denied",
  "source_mail_id": "uuid",    # ID of the mail item that triggered this match (optional)
  "source_mail_type": "Bill"   # "Bill" | "Notice" | "ForwardToMe" (optional)
}
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from postmule.data._io import atomic_write


def _entities_file(data_dir: Path) -> Path:
    return data_dir / "entities.json"


def _pending_file(data_dir: Path) -> Path:
    pending_dir = data_dir / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    return pending_dir / "entity_matches.json"


def load_entities(data_dir: Path) -> list[dict[str, Any]]:
    path = _entities_file(data_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_entities(data_dir: Path, entities: list[dict[str, Any]]) -> None:
    path = _entities_file(data_dir)
    atomic_write(path, json.dumps(entities, indent=2, ensure_ascii=False))


def load_pending_matches(data_dir: Path) -> list[dict[str, Any]]:
    path = _pending_file(data_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_pending_matches(data_dir: Path, matches: list[dict[str, Any]]) -> None:
    path = _pending_file(data_dir)
    atomic_write(path, json.dumps(matches, indent=2, ensure_ascii=False))


def add_entity(data_dir: Path, name: str, entity_type: str = "Person") -> dict[str, Any]:
    entities = load_entities(data_dir)
    entity = {
        "id": str(uuid.uuid4()),
        "canonical_name": name,
        "type": entity_type,
        "aliases": [name],
        "denied_aliases": [],
        "created_date": date.today().isoformat(),
    }
    entities.append(entity)
    save_entities(data_dir, entities)
    return entity


def get_all_known_names(data_dir: Path) -> list[str]:
    """Return all canonical names and aliases for LLM context."""
    entities = load_entities(data_dir)
    names = []
    for e in entities:
        names.append(e["canonical_name"])
        names.extend(e.get("aliases", []))
    return sorted(set(names))


def propose_alias_match(
    data_dir: Path,
    proposed_name: str,
    entity_id: str,
    similarity: float,
    auto_approve_days: int = 7,
    source_mail_id: str | None = None,
    source_mail_type: str | None = None,
) -> dict[str, Any]:
    """Add a pending alias match for human review."""
    pending = load_pending_matches(data_dir)

    # Don't re-propose if already pending or decided
    for m in pending:
        if m["proposed_name"] == proposed_name and m["match_entity_id"] == entity_id:
            return m

    auto_approve_after = (date.today() + timedelta(days=auto_approve_days)).isoformat()
    match = {
        "id": str(uuid.uuid4()),
        "proposed_name": proposed_name,
        "match_entity_id": entity_id,
        "similarity": round(similarity, 4),
        "proposed_date": date.today().isoformat(),
        "auto_approve_after": auto_approve_after,
        "status": "pending",
        "source_mail_id": source_mail_id,
        "source_mail_type": source_mail_type,
    }
    pending.append(match)
    save_pending_matches(data_dir, pending)
    return match


def process_auto_approvals(data_dir: Path) -> list[dict[str, Any]]:
    """
    Auto-approve any pending matches whose auto_approve_after date has passed.
    Returns list of newly approved matches.
    """
    pending = load_pending_matches(data_dir)
    entities = load_entities(data_dir)
    today = date.today().isoformat()
    approved = []

    for match in pending:
        if match["status"] != "pending":
            continue
        if match["auto_approve_after"] <= today:
            match["status"] = "approved"
            # Add alias to entity
            for entity in entities:
                if entity["id"] == match["match_entity_id"]:
                    if match["proposed_name"] not in entity["aliases"]:
                        entity["aliases"].append(match["proposed_name"])
                    break
            approved.append(match)

    if approved:
        save_pending_matches(data_dir, pending)
        save_entities(data_dir, entities)

    return approved


def is_denied(data_dir: Path, proposed_name: str, entity_id: str) -> bool:
    """Check if a proposed alias was previously denied by the user."""
    for match in load_pending_matches(data_dir):
        if (match["proposed_name"] == proposed_name
                and match["match_entity_id"] == entity_id
                and match["status"] == "denied"):
            return True
    # Also check entity's denied_aliases list
    for entity in load_entities(data_dir):
        if entity["id"] == entity_id:
            return proposed_name in entity.get("denied_aliases", [])
    return False


def to_sheet_rows(entities: list[dict[str, Any]]) -> list[list[Any]]:
    headers = ["ID", "Canonical Name", "Type", "Aliases", "Created Date"]
    rows = [headers]
    for e in entities:
        rows.append([
            e.get("id", ""),
            e.get("canonical_name", ""),
            e.get("type", ""),
            ", ".join(e.get("aliases", [])),
            e.get("created_date", ""),
        ])
    return rows
