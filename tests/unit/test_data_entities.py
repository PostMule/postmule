"""Unit tests for postmule.data.entities."""

import pytest

from postmule.data.entities import (
    add_entity,
    get_all_known_names,
    is_denied,
    load_entities,
    process_auto_approvals,
    propose_alias_match,
)


def test_add_and_load(tmp_path):
    entity = add_entity(tmp_path, "Alice Smith", "Person")
    assert entity["canonical_name"] == "Alice Smith"
    assert entity["type"] == "Person"
    assert "id" in entity

    entities = load_entities(tmp_path)
    assert len(entities) == 1


def test_get_all_known_names(tmp_path):
    add_entity(tmp_path, "Alice Smith", "Person")
    names = get_all_known_names(tmp_path)
    assert "Alice Smith" in names


def test_propose_alias_match(tmp_path):
    entity = add_entity(tmp_path, "Alice Smith", "Person")
    match = propose_alias_match(tmp_path, "A. Smith", entity["id"], 0.92)
    assert match["proposed_name"] == "A. Smith"
    assert match["status"] == "pending"


def test_no_duplicate_proposals(tmp_path):
    entity = add_entity(tmp_path, "Alice Smith", "Person")
    m1 = propose_alias_match(tmp_path, "A. Smith", entity["id"], 0.92)
    m2 = propose_alias_match(tmp_path, "A. Smith", entity["id"], 0.92)
    assert m1["id"] == m2["id"]


def test_auto_approval(tmp_path):
    entity = add_entity(tmp_path, "Alice Smith", "Person")
    match = propose_alias_match(tmp_path, "A. Smith", entity["id"], 0.90, auto_approve_days=0)
    approved = process_auto_approvals(tmp_path)
    assert len(approved) == 1
    # Alias added to entity
    entities = load_entities(tmp_path)
    assert "A. Smith" in entities[0]["aliases"]


def test_is_denied(tmp_path):
    entity = add_entity(tmp_path, "Alice Smith", "Person")
    match = propose_alias_match(tmp_path, "Al", entity["id"], 0.60)
    # Manually deny
    from postmule.data.entities import load_pending_matches, save_pending_matches
    pending = load_pending_matches(tmp_path)
    for m in pending:
        if m["id"] == match["id"]:
            m["status"] = "denied"
    save_pending_matches(tmp_path, pending)
    assert is_denied(tmp_path, "Al", entity["id"])
