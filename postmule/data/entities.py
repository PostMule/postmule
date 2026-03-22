"""
Entity data layer — reads/writes entities.json and pending/entity_matches.json.

Entity record schema (version-locked — field additions require an app update + migration):
{
  "id": "uuid",
  "canonical_name": "AT&T",
  "aliases": ["AT T", "ATT"],
  "denied_aliases": [],
  "category": "biller",          # biller | sender | vendor | government | personal
  "address": {                   # all sub-fields nullable
    "street": null,
    "city": null,
    "state": null,
    "zip": null,
    "country": null
  },
  "account_numbers": [],         # list of known account number strings
  "phone": null,
  "website": null,
  "email": null,
  "notes": null,                 # free-text, human-editable
  "auto_populated_at": null,     # ISO datetime of last LLM enrichment
  "last_seen_in_mail_id": null,  # provenance: last mail that referenced this entity
  "user_verified_fields": [],    # field names that have been manually verified
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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from postmule.data._io import atomic_write

# Schema version — bump when fields are added so migrate_entity() can be extended
SCHEMA_VERSION = 2

# Valid categories
CATEGORIES = ("biller", "sender", "vendor", "government", "personal")

_EMPTY_ADDRESS: dict[str, str | None] = {
    "street": None, "city": None, "state": None, "zip": None, "country": None,
}


def _entities_file(data_dir: Path) -> Path:
    return data_dir / "entities.json"


def _pending_file(data_dir: Path) -> Path:
    pending_dir = data_dir / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    return pending_dir / "entity_matches.json"


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


def migrate_entity(entity: dict[str, Any]) -> dict[str, Any]:
    """Upgrade an old-schema entity record to the current schema in place. Returns the entity."""
    # v1 → v2: replace 'type' with 'category', add structured fields
    if "type" in entity and "category" not in entity:
        old_type = entity.pop("type", "")
        # Map old Person/Corporation/etc types to new categories
        _type_map = {
            "person": "personal",
            "llc": "vendor",
            "trust": "personal",
            "corporation": "biller",
            "partnership": "vendor",
        }
        entity["category"] = _type_map.get(old_type.lower(), "biller")

    entity.setdefault("aliases", [entity["canonical_name"]])
    entity.setdefault("denied_aliases", [])
    entity.setdefault("category", "biller")
    entity.setdefault("address", dict(_EMPTY_ADDRESS))
    entity.setdefault("account_numbers", [])
    entity.setdefault("phone", None)
    entity.setdefault("website", None)
    entity.setdefault("email", None)
    entity.setdefault("notes", None)
    entity.setdefault("auto_populated_at", None)
    entity.setdefault("last_seen_in_mail_id", None)
    entity.setdefault("user_verified_fields", [])
    return entity


def load_entities(data_dir: Path) -> list[dict[str, Any]]:
    path = _entities_file(data_dir)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    needs_migration = any("type" in e or "category" not in e for e in raw)
    entities = [migrate_entity(e) for e in raw]
    if needs_migration:
        save_entities(data_dir, entities)
    return entities


def add_entity(data_dir: Path, name: str, category: str = "biller") -> dict[str, Any]:
    entities = load_entities(data_dir)
    entity: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "canonical_name": name,
        "aliases": [name],
        "denied_aliases": [],
        "category": category if category in CATEGORIES else "biller",
        "address": dict(_EMPTY_ADDRESS),
        "account_numbers": [],
        "phone": None,
        "website": None,
        "email": None,
        "notes": None,
        "auto_populated_at": None,
        "last_seen_in_mail_id": None,
        "user_verified_fields": [],
        "created_date": date.today().isoformat(),
    }
    entities.append(entity)
    save_entities(data_dir, entities)
    return entity


def enrich_entity(
    data_dir: Path,
    entity_id: str,
    fields: dict[str, Any],
    source_mail_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Fill null fields on an entity with LLM-extracted data.
    Fields in entity['user_verified_fields'] are never overwritten.
    Returns the updated entity or None if not found.
    """
    entities = load_entities(data_dir)
    for entity in entities:
        if entity["id"] != entity_id:
            continue
        verified = set(entity.get("user_verified_fields", []))
        for key, value in fields.items():
            if key in ("id", "canonical_name", "aliases", "denied_aliases",
                       "user_verified_fields", "created_date"):
                continue
            if key in verified:
                continue
            if key == "address" and isinstance(value, dict):
                addr = entity.setdefault("address", dict(_EMPTY_ADDRESS))
                for sub, sub_val in value.items():
                    if sub not in verified and sub_val is not None:
                        addr[sub] = sub_val
            elif value is not None:
                entity[key] = value
        entity["auto_populated_at"] = datetime.now(timezone.utc).isoformat()
        if source_mail_id:
            entity["last_seen_in_mail_id"] = source_mail_id
        save_entities(data_dir, entities)
        return entity
    return None


def update_entity_field(
    data_dir: Path,
    entity_id: str,
    field: str,
    value: Any,
    mark_verified: bool = True,
) -> dict[str, Any] | None:
    """
    Update a single field on an entity (user edit).
    By default marks the field as user_verified to protect it from LLM overwrites.
    Returns the updated entity or None if not found.
    """
    entities = load_entities(data_dir)
    for entity in entities:
        if entity["id"] != entity_id:
            continue
        if field == "address" and isinstance(value, dict):
            addr = entity.setdefault("address", dict(_EMPTY_ADDRESS))
            addr.update(value)
        elif field == "account_numbers" and isinstance(value, list):
            entity["account_numbers"] = value
        else:
            entity[field] = value
        if mark_verified and field not in ("id", "created_date"):
            verified = entity.setdefault("user_verified_fields", [])
            if field not in verified:
                verified.append(field)
        save_entities(data_dir, entities)
        return entity
    return None


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
    headers = [
        "ID", "Canonical Name", "Category", "Aliases",
        "Phone", "Website", "Email", "Account Numbers",
        "Address", "Last Seen Mail ID", "Created Date",
    ]
    rows = [headers]
    for e in entities:
        addr = e.get("address") or {}
        addr_str = ", ".join(
            v for v in [
                addr.get("street"), addr.get("city"), addr.get("state"),
                addr.get("zip"), addr.get("country"),
            ] if v
        )
        rows.append([
            e.get("id", ""),
            e.get("canonical_name", ""),
            e.get("category", ""),
            ", ".join(e.get("aliases", [])),
            e.get("phone", "") or "",
            e.get("website", "") or "",
            e.get("email", "") or "",
            ", ".join(e.get("account_numbers", [])),
            addr_str,
            e.get("last_seen_in_mail_id", "") or "",
            e.get("created_date", ""),
        ])
    return rows
