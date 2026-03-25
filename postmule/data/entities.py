"""
Entity data layer — reads/writes entities.json and pending/entity_matches.json.

Entity record schema (v3 — field additions require an app update + migration):
{
  "id": "uuid",
  "friendly_name": "AT&T Mobile",       # user-editable, unique, primary display label
  "canonical_name": "AT&T Mobility LLC", # LLM/OCR extracted, secondary muted display
  "aliases": ["AT T", "ATT"],
  "denied_aliases": [],
  "category": "biller",          # biller | sender | vendor | government | personal
  "account_number": "12345678",  # stored in full; displayed as ****1234; one per entity
  "address": {                   # all sub-fields nullable
    "street": null,
    "city": null,
    "state": null,
    "zip": null,
    "country": null
  },
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

import copy
import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from postmule.data._io import atomic_write

# Schema version — bump when fields are added so migrate_entity() can be extended
SCHEMA_VERSION = 3

# Valid categories
CATEGORIES = ("biller", "sender", "vendor", "government", "personal")

_EMPTY_ADDRESS: dict[str, str | None] = {
    "street": None, "city": None, "state": None, "zip": None, "country": None,
}


def mask_account_number(account: str) -> str:
    """Strip non-alphanumeric chars from account, return last 4 as ****XXXX.

    Empty or whitespace-only input returns empty string.
    Inputs shorter than 4 alnum chars return ****<full stripped value>.
    """
    if not account:
        return ""
    stripped = re.sub(r"[^a-zA-Z0-9]", "", account)
    if not stripped:
        return ""
    last4 = stripped[-4:]
    return f"****{last4}"


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
    """Upgrade an old-schema entity record to the current schema in place. Returns the entity.

    Note: multi-account entity splitting (account_numbers list → per-account records)
    is handled by load_entities() after individual migration, not here.
    """
    # v1 → v2: replace 'type' with 'category', add structured fields
    if "type" in entity and "category" not in entity:
        old_type = entity.pop("type", "")
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
    entity.setdefault("phone", None)
    entity.setdefault("website", None)
    entity.setdefault("email", None)
    entity.setdefault("notes", None)
    entity.setdefault("auto_populated_at", None)
    entity.setdefault("last_seen_in_mail_id", None)
    entity.setdefault("user_verified_fields", [])

    # v2 → v3: add friendly_name; account_numbers list → account_number scalar
    # The account_numbers key is left in place here so load_entities() can detect
    # multi-account records and split them into separate entities.
    entity.setdefault("friendly_name", entity.get("canonical_name", ""))
    if "account_numbers" in entity and "account_number" not in entity:
        acct_list = entity["account_numbers"]
        entity["account_number"] = acct_list[0] if acct_list else None
        # leave account_numbers for load_entities() split logic
    entity.setdefault("account_number", None)

    return entity


def _split_multi_account_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    After per-entity migration, split any entity that still holds a legacy
    account_numbers list with 2+ entries into separate entity records.
    Called once during load_entities() migration.
    """
    result: list[dict[str, Any]] = []
    for entity in entities:
        extra_accounts = entity.pop("account_numbers", [])
        result.append(entity)
        # extra_accounts[0] was already promoted to account_number by migrate_entity()
        for acct in extra_accounts[1:]:
            new_entity = copy.deepcopy(entity)
            new_entity["id"] = str(uuid.uuid4())
            new_entity["account_number"] = acct
            masked = mask_account_number(acct)
            base_name = entity["friendly_name"]
            new_entity["friendly_name"] = f"{base_name} {masked}" if masked else base_name
            result.append(new_entity)
    return result


def load_entities(data_dir: Path) -> list[dict[str, Any]]:
    path = _entities_file(data_dir)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    needs_migration = any(
        "type" in e
        or "category" not in e
        or "account_numbers" in e
        or "friendly_name" not in e
        for e in raw
    )
    entities = [migrate_entity(e) for e in raw]

    # v2 → v3 split: handle multi-account entities; clean up legacy key
    if any("account_numbers" in e for e in entities):
        entities = _split_multi_account_entities(entities)
    else:
        for e in entities:
            e.pop("account_numbers", None)

    if needs_migration:
        save_entities(data_dir, entities)
    return entities


def add_entity(
    data_dir: Path,
    name: str,
    category: str = "biller",
    *,
    friendly_name: str | None = None,
    account_number: str | None = None,
) -> dict[str, Any]:
    entities = load_entities(data_dir)
    entity: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "friendly_name": friendly_name if friendly_name is not None else name,
        "canonical_name": name,
        "aliases": [name],
        "denied_aliases": [],
        "category": category if category in CATEGORIES else "biller",
        "account_number": account_number,
        "address": dict(_EMPTY_ADDRESS),
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


def validate_friendly_name_unique(
    entities: list[dict[str, Any]],
    friendly_name: str,
    exclude_id: str | None = None,
) -> bool:
    """Return True if friendly_name is not already used by another entity."""
    fn_lower = friendly_name.strip().lower()
    for e in entities:
        if exclude_id and e["id"] == exclude_id:
            continue
        if e.get("friendly_name", "").strip().lower() == fn_lower:
            return False
    return True


def find_entity_by_account(
    entities: list[dict[str, Any]],
    account_number: str,
) -> dict[str, Any] | None:
    """
    Find an entity whose stored account_number shares the same last-4 alphanumeric
    characters as the given account_number.  Returns the first match or None.
    """
    if not account_number:
        return None
    stripped = re.sub(r"[^a-zA-Z0-9]", "", account_number)
    if not stripped:
        return None
    input_last4 = stripped[-4:]
    for entity in entities:
        stored = entity.get("account_number") or ""
        if not stored:
            continue
        stored_stripped = re.sub(r"[^a-zA-Z0-9]", "", stored)
        if not stored_stripped:
            continue
        stored_last4 = stored_stripped[-4:]
        if stored_last4 == input_last4:
            return entity
    return None


def enrich_entity(
    data_dir: Path,
    entity_id: str,
    fields: dict[str, Any],
    source_mail_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Fill null fields on an entity with LLM-extracted data.
    Fields in entity['user_verified_fields'] are never overwritten.
    friendly_name and canonical_name are always protected from LLM writes.
    Returns the updated entity or None if not found.
    """
    entities = load_entities(data_dir)
    for entity in entities:
        if entity["id"] != entity_id:
            continue
        verified = set(entity.get("user_verified_fields", []))
        for key, value in fields.items():
            if key in ("id", "friendly_name", "canonical_name", "aliases", "denied_aliases",
                       "account_number", "user_verified_fields", "created_date"):
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
    """Return all friendly names, canonical names, and aliases for LLM context."""
    entities = load_entities(data_dir)
    names = []
    for e in entities:
        if e.get("friendly_name"):
            names.append(e["friendly_name"])
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
        "ID", "Friendly Name", "Canonical Name", "Category", "Aliases",
        "Phone", "Website", "Email", "Account Number",
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
        acct = e.get("account_number") or ""
        rows.append([
            e.get("id", ""),
            e.get("friendly_name", ""),
            e.get("canonical_name", ""),
            e.get("category", ""),
            ", ".join(e.get("aliases", [])),
            e.get("phone", "") or "",
            e.get("website", "") or "",
            e.get("email", "") or "",
            mask_account_number(acct) if acct else "",
            addr_str,
            e.get("last_seen_in_mail_id", "") or "",
            e.get("created_date", ""),
        ])
    return rows
