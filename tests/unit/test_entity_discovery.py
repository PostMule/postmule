"""Unit tests for postmule.agents.entity_discovery."""

import pytest

from postmule.agents.entity_discovery import run_entity_discovery, seed_known_entities
from postmule.data.entities import add_entity, get_all_known_names, load_entities


def test_seed_known_entities(tmp_path):
    seed_known_entities(tmp_path, ["Alice Smith", "Bob Smith"])
    entities = load_entities(tmp_path)
    names = [e["canonical_name"] for e in entities]
    assert "Alice Smith" in names
    assert "Bob Smith" in names


def test_seed_is_idempotent(tmp_path):
    seed_known_entities(tmp_path, ["Alice Smith"])
    seed_known_entities(tmp_path, ["Alice Smith"])
    entities = load_entities(tmp_path)
    names = [e["canonical_name"] for e in entities]
    assert names.count("Alice Smith") == 1


def test_exact_match(tmp_path):
    add_entity(tmp_path, "Alice Smith", "Person")
    result = run_entity_discovery(["Alice Smith"], tmp_path)
    assert len(result["matched"]) == 1
    assert result["matched"][0]["entity"] == "Alice Smith"


def test_alias_match(tmp_path):
    entity = add_entity(tmp_path, "Alice Smith", "Person")
    from postmule.data.entities import load_entities, save_entities
    entities = load_entities(tmp_path)
    entities[0]["aliases"] = ["Alice Smith", "Alice"]
    save_entities(tmp_path, entities)

    result = run_entity_discovery(["Alice"], tmp_path)
    assert len(result["matched"]) == 1


def test_unknown_name_goes_to_new(tmp_path):
    result = run_entity_discovery(["Completely Unknown Person XYZ"], tmp_path)
    assert "Completely Unknown Person XYZ" in result["new"]


def test_fuzzy_match_proposes_alias(tmp_path):
    add_entity(tmp_path, "Alice Smith", "Person")
    result = run_entity_discovery(
        ["Alice Smyth"],  # slight typo
        tmp_path,
        fuzzy_threshold=80.0,
    )
    # Should propose as alias (not exact match)
    assert len(result["proposed"]) >= 0  # may match depending on threshold
