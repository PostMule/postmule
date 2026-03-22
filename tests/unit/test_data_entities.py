"""Unit tests for postmule.data.entities."""

import json

import pytest

from postmule.data.entities import (
    CATEGORIES,
    add_entity,
    enrich_entity,
    get_all_known_names,
    is_denied,
    load_entities,
    migrate_entity,
    process_auto_approvals,
    propose_alias_match,
    update_entity_field,
)


def test_add_and_load(tmp_path):
    entity = add_entity(tmp_path, "Alice Smith", "personal")
    assert entity["canonical_name"] == "Alice Smith"
    assert entity["category"] == "personal"
    assert "id" in entity
    assert "type" not in entity
    assert entity["address"] == {"street": None, "city": None, "state": None, "zip": None, "country": None}
    assert entity["account_numbers"] == []
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
