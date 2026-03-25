"""Unit tests for postmule.data.entities."""

import json

import pytest

from postmule.data.entities import (
    CATEGORIES,
    SCHEMA_VERSION,
    add_entity,
    enrich_entity,
    find_entity_by_account,
    get_all_known_names,
    is_denied,
    load_entities,
    mask_account_number,
    migrate_entity,
    process_auto_approvals,
    propose_alias_match,
    update_entity_field,
    validate_friendly_name_unique,
)


def test_add_and_load(tmp_path):
    entity = add_entity(tmp_path, "Alice Smith", "personal")
    assert entity["canonical_name"] == "Alice Smith"
    assert entity["category"] == "personal"
    assert "id" in entity
    assert "type" not in entity
    assert entity["address"] == {"street": None, "city": None, "state": None, "zip": None, "country": None}
    assert entity["account_number"] is None
    assert entity["user_verified_fields"] == []

    entities = load_entities(tmp_path)
    assert len(entities) == 1


def test_add_entity_invalid_category_defaults_to_biller(tmp_path):
    entity = add_entity(tmp_path, "Test", "unknown_type")
    assert entity["category"] == "biller"


def test_get_all_known_names(tmp_path):
    add_entity(tmp_path, "Alice Smith", "personal")
    names = get_all_known_names(tmp_path)
    assert "Alice Smith" in names


def test_propose_alias_match(tmp_path):
    entity = add_entity(tmp_path, "Alice Smith", "personal")
    match = propose_alias_match(tmp_path, "A. Smith", entity["id"], 0.92)
    assert match["proposed_name"] == "A. Smith"
    assert match["status"] == "pending"


def test_no_duplicate_proposals(tmp_path):
    entity = add_entity(tmp_path, "Alice Smith", "personal")
    m1 = propose_alias_match(tmp_path, "A. Smith", entity["id"], 0.92)
    m2 = propose_alias_match(tmp_path, "A. Smith", entity["id"], 0.92)
    assert m1["id"] == m2["id"]


def test_auto_approval(tmp_path):
    entity = add_entity(tmp_path, "Alice Smith", "personal")
    propose_alias_match(tmp_path, "A. Smith", entity["id"], 0.90, auto_approve_days=0)
    approved = process_auto_approvals(tmp_path)
    assert len(approved) == 1
    # Alias added to entity
    entities = load_entities(tmp_path)
    assert "A. Smith" in entities[0]["aliases"]


def test_is_denied(tmp_path):
    entity = add_entity(tmp_path, "Alice Smith", "personal")
    match = propose_alias_match(tmp_path, "Al", entity["id"], 0.60)
    # Manually deny
    from postmule.data.entities import load_pending_matches, save_pending_matches
    pending = load_pending_matches(tmp_path)
    for m in pending:
        if m["id"] == match["id"]:
            m["status"] = "denied"
    save_pending_matches(tmp_path, pending)
    assert is_denied(tmp_path, "Al", entity["id"])


def test_migrate_entity_from_v1(tmp_path):
    """Old records with 'type' are migrated to 'category' on load."""
    old_record = [{"id": "abc", "canonical_name": "AT&T", "type": "Corporation",
                   "aliases": ["AT&T"], "denied_aliases": [], "created_date": "2024-01-01"}]
    (tmp_path / "entities.json").write_text(json.dumps(old_record))
    entities = load_entities(tmp_path)
    assert entities[0]["category"] == "biller"
    assert "type" not in entities[0]
    assert entities[0]["phone"] is None
    assert entities[0]["address"] == {"street": None, "city": None, "state": None, "zip": None, "country": None}


def test_enrich_entity_fills_null_fields(tmp_path):
    entity = add_entity(tmp_path, "AT&T", "biller")
    result = enrich_entity(tmp_path, entity["id"], {"phone": "1-800-288-2020", "website": "https://att.com"})
    assert result is not None
    assert result["phone"] == "1-800-288-2020"
    assert result["website"] == "https://att.com"
    assert result["auto_populated_at"] is not None


def test_enrich_entity_does_not_overwrite_verified_fields(tmp_path):
    entity = add_entity(tmp_path, "AT&T", "biller")
    update_entity_field(tmp_path, entity["id"], "phone", "1-888-CORRECT", mark_verified=True)
    enrich_entity(tmp_path, entity["id"], {"phone": "1-800-WRONG"})
    entities = load_entities(tmp_path)
    assert entities[0]["phone"] == "1-888-CORRECT"


def test_update_entity_field_marks_verified(tmp_path):
    entity = add_entity(tmp_path, "Test Corp", "biller")
    updated = update_entity_field(tmp_path, entity["id"], "phone", "555-1234")
    assert updated is not None
    assert "phone" in updated["user_verified_fields"]


def test_update_entity_field_not_found(tmp_path):
    result = update_entity_field(tmp_path, "nonexistent-id", "phone", "555")
    assert result is None


def test_categories_constant():
    assert "biller" in CATEGORIES
    assert "personal" in CATEGORIES


# ---------------------------------------------------------------------------
# Schema v3 — friendly_name
# ---------------------------------------------------------------------------

def test_schema_version_is_3():
    assert SCHEMA_VERSION == 3


def test_add_entity_friendly_name_defaults_to_canonical_name(tmp_path):
    entity = add_entity(tmp_path, "AT&T Mobility LLC", "biller")
    assert entity["friendly_name"] == "AT&T Mobility LLC"


def test_add_entity_explicit_friendly_name(tmp_path):
    entity = add_entity(tmp_path, "AT&T Mobility LLC", "biller", friendly_name="AT&T Mobile")
    assert entity["friendly_name"] == "AT&T Mobile"
    assert entity["canonical_name"] == "AT&T Mobility LLC"


def test_friendly_name_in_known_names(tmp_path):
    add_entity(tmp_path, "AT&T Mobility LLC", "biller", friendly_name="AT&T Mobile")
    names = get_all_known_names(tmp_path)
    assert "AT&T Mobile" in names
    assert "AT&T Mobility LLC" in names


def test_validate_friendly_name_unique_passes_for_new(tmp_path):
    add_entity(tmp_path, "AT&T", "biller", friendly_name="AT&T Mobile")
    entities = load_entities(tmp_path)
    assert validate_friendly_name_unique(entities, "Verizon") is True


def test_validate_friendly_name_unique_rejects_duplicate(tmp_path):
    e = add_entity(tmp_path, "AT&T", "biller", friendly_name="AT&T Mobile")
    entities = load_entities(tmp_path)
    assert validate_friendly_name_unique(entities, "AT&T Mobile") is False


def test_validate_friendly_name_unique_exclude_self(tmp_path):
    e = add_entity(tmp_path, "AT&T", "biller", friendly_name="AT&T Mobile")
    entities = load_entities(tmp_path)
    # Same name is ok when exclude_id is the entity's own id
    assert validate_friendly_name_unique(entities, "AT&T Mobile", exclude_id=e["id"]) is True


def test_validate_friendly_name_case_insensitive(tmp_path):
    add_entity(tmp_path, "AT&T", "biller", friendly_name="AT&T Mobile")
    entities = load_entities(tmp_path)
    assert validate_friendly_name_unique(entities, "at&t mobile") is False


# ---------------------------------------------------------------------------
# Schema v3 — account_number scalar
# ---------------------------------------------------------------------------

def test_add_entity_with_account_number(tmp_path):
    entity = add_entity(tmp_path, "Verizon", "biller", account_number="123456789")
    assert entity["account_number"] == "123456789"


def test_update_entity_field_account_number(tmp_path):
    entity = add_entity(tmp_path, "Verizon", "biller")
    updated = update_entity_field(tmp_path, entity["id"], "account_number", "98765432")
    assert updated is not None
    assert updated["account_number"] == "98765432"


def test_enrich_entity_does_not_overwrite_account_number(tmp_path):
    """account_number, friendly_name, canonical_name are protected from LLM writes."""
    entity = add_entity(tmp_path, "Verizon", "biller", account_number="REAL1234")
    enrich_entity(tmp_path, entity["id"], {"account_number": "FAKE9999", "friendly_name": "Hacked"})
    entities = load_entities(tmp_path)
    assert entities[0]["account_number"] == "REAL1234"
    assert entities[0]["friendly_name"] == "Verizon"


# ---------------------------------------------------------------------------
# mask_account_number
# ---------------------------------------------------------------------------

def test_mask_account_number_standard():
    assert mask_account_number("12345678") == "****5678"


def test_mask_account_number_with_dashes():
    assert mask_account_number("1234-5678-9012") == "****9012"


def test_mask_account_number_short():
    assert mask_account_number("123") == "****123"


def test_mask_account_number_empty():
    assert mask_account_number("") == ""


def test_mask_account_number_only_special_chars():
    assert mask_account_number("---") == ""


# ---------------------------------------------------------------------------
# find_entity_by_account
# ---------------------------------------------------------------------------

def test_find_entity_by_account_matches_last4(tmp_path):
    e = add_entity(tmp_path, "AT&T", "biller", account_number="12345678")
    entities = load_entities(tmp_path)
    found = find_entity_by_account(entities, "99995678")
    assert found is not None
    assert found["id"] == e["id"]


def test_find_entity_by_account_no_match(tmp_path):
    add_entity(tmp_path, "AT&T", "biller", account_number="12345678")
    entities = load_entities(tmp_path)
    assert find_entity_by_account(entities, "99999999") is None


def test_find_entity_by_account_ignores_dashes(tmp_path):
    e = add_entity(tmp_path, "AT&T", "biller", account_number="1234-5678")
    entities = load_entities(tmp_path)
    found = find_entity_by_account(entities, "56 78")
    assert found is not None
    assert found["id"] == e["id"]


def test_find_entity_by_account_empty_returns_none(tmp_path):
    add_entity(tmp_path, "AT&T", "biller", account_number="12345678")
    entities = load_entities(tmp_path)
    assert find_entity_by_account(entities, "") is None


# ---------------------------------------------------------------------------
# Migration v2 → v3
# ---------------------------------------------------------------------------

def test_migrate_v2_single_account_number(tmp_path):
    """account_numbers: ['abc'] → account_number: 'abc', no split."""
    old = [{
        "id": "aaa", "canonical_name": "Verizon",
        "aliases": ["Verizon"], "denied_aliases": [], "category": "biller",
        "account_numbers": ["A1B2C3D4"],
        "address": {"street": None, "city": None, "state": None, "zip": None, "country": None},
        "phone": None, "website": None, "email": None, "notes": None,
        "auto_populated_at": None, "last_seen_in_mail_id": None,
        "user_verified_fields": [], "created_date": "2025-01-01",
    }]
    (tmp_path / "entities.json").write_text(json.dumps(old))
    entities = load_entities(tmp_path)
    assert len(entities) == 1
    assert entities[0]["account_number"] == "A1B2C3D4"
    assert "account_numbers" not in entities[0]
    assert entities[0]["friendly_name"] == "Verizon"


def test_migrate_v2_empty_account_numbers(tmp_path):
    old = [{
        "id": "bbb", "canonical_name": "AT&T",
        "aliases": ["AT&T"], "denied_aliases": [], "category": "biller",
        "account_numbers": [],
        "address": {"street": None, "city": None, "state": None, "zip": None, "country": None},
        "phone": None, "website": None, "email": None, "notes": None,
        "auto_populated_at": None, "last_seen_in_mail_id": None,
        "user_verified_fields": [], "created_date": "2025-01-01",
    }]
    (tmp_path / "entities.json").write_text(json.dumps(old))
    entities = load_entities(tmp_path)
    assert len(entities) == 1
    assert entities[0]["account_number"] is None


def test_migrate_v2_multi_account_splits_into_separate_entities(tmp_path):
    """account_numbers with 3 entries → 3 separate entity records."""
    old = [{
        "id": "ccc", "canonical_name": "AT&T",
        "aliases": ["AT&T"], "denied_aliases": [], "category": "biller",
        "account_numbers": ["AAA00001", "BBB00002", "CCC00003"],
        "address": {"street": None, "city": None, "state": None, "zip": None, "country": None},
        "phone": None, "website": None, "email": None, "notes": None,
        "auto_populated_at": None, "last_seen_in_mail_id": None,
        "user_verified_fields": [], "created_date": "2025-01-01",
    }]
    (tmp_path / "entities.json").write_text(json.dumps(old))
    entities = load_entities(tmp_path)
    assert len(entities) == 3
    account_numbers = {e["account_number"] for e in entities}
    assert "AAA00001" in account_numbers
    assert "BBB00002" in account_numbers
    assert "CCC00003" in account_numbers
    # All three should have unique IDs
    ids = {e["id"] for e in entities}
    assert len(ids) == 3


def test_migrate_v2_multi_account_friendly_names_include_mask(tmp_path):
    """Split entities get masked account number appended to friendly_name (except first)."""
    old = [{
        "id": "ddd", "canonical_name": "AT&T",
        "aliases": ["AT&T"], "denied_aliases": [], "category": "biller",
        "account_numbers": ["AAA00001", "BBB00002"],
        "address": {"street": None, "city": None, "state": None, "zip": None, "country": None},
        "phone": None, "website": None, "email": None, "notes": None,
        "auto_populated_at": None, "last_seen_in_mail_id": None,
        "user_verified_fields": [], "created_date": "2025-01-01",
    }]
    (tmp_path / "entities.json").write_text(json.dumps(old))
    entities = load_entities(tmp_path)
    friendly_names = {e["friendly_name"] for e in entities}
    # First entity keeps "AT&T"; second gets "AT&T ****0002"
    assert "AT&T" in friendly_names
    assert "AT&T ****0002" in friendly_names


def test_migrate_v2_migration_is_persisted(tmp_path):
    """After migration, reloading should return the same split result without re-splitting."""
    old = [{
        "id": "eee", "canonical_name": "Comcast",
        "aliases": ["Comcast"], "denied_aliases": [], "category": "biller",
        "account_numbers": ["X1234567", "Y9876543"],
        "address": {"street": None, "city": None, "state": None, "zip": None, "country": None},
        "phone": None, "website": None, "email": None, "notes": None,
        "auto_populated_at": None, "last_seen_in_mail_id": None,
        "user_verified_fields": [], "created_date": "2025-01-01",
    }]
    (tmp_path / "entities.json").write_text(json.dumps(old))
    first_load = load_entities(tmp_path)
    second_load = load_entities(tmp_path)
    assert len(first_load) == 2
    assert len(second_load) == 2
