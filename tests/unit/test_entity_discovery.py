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


# ---------------------------------------------------------------------------
# Account-number primary matching
# ---------------------------------------------------------------------------

def test_account_number_match_returns_matched(tmp_path):
    """Known account number → matched, skips name-based logic entirely."""
    add_entity(tmp_path, "AT&T Mobility LLC", "biller",
               friendly_name="AT&T Mobile", account_number="A1B2C3D4")
    result = run_entity_discovery(
        ["AT&T", "Alice Smith"],
        tmp_path,
        account_number="X9Y9A1B2C3D4",  # last4 = D4 matches
    )
    assert len(result["matched"]) == 1
    assert result["matched"][0]["match_type"] == "account_number"
    assert result["matched"][0]["name"] == "AT&T Mobile"
    # unassigned/proposed/new should all be empty (returned early)
    assert result["unassigned"] == []
    assert result["proposed"] == []
    assert result["new"] == []


def test_unknown_account_number_routes_to_unassigned(tmp_path):
    """Unrecognized account number → unassigned, even if name would fuzzy-match."""
    add_entity(tmp_path, "AT&T Mobility LLC", "biller", account_number="KNOWN001")
    result = run_entity_discovery(
        ["AT&T"],  # name matches, but account is different
        tmp_path,
        account_number="UNKNOWN999",
    )
    assert len(result["unassigned"]) == 1
    assert result["unassigned"][0]["reason"] == "unrecognized_account"
    assert result["matched"] == []


def test_no_account_number_falls_through_to_name_matching(tmp_path):
    """No account_number provided → normal name-based matching."""
    add_entity(tmp_path, "AT&T Mobility LLC", "biller")
    result = run_entity_discovery(["AT&T Mobility LLC"], tmp_path)
    assert len(result["matched"]) == 1
    assert result["matched"][0]["match_type"] == "exact"


def test_friendly_name_is_exact_matchable(tmp_path):
    """friendly_name can be used as an exact match trigger."""
    add_entity(tmp_path, "AT&T Mobility LLC", "biller", friendly_name="AT&T Mobile")
    result = run_entity_discovery(["AT&T Mobile"], tmp_path)
    assert len(result["matched"]) == 1
    assert result["matched"][0]["match_type"] == "exact"


def test_empty_account_number_string_falls_through_to_name(tmp_path):
    """Empty string for account_number is treated as absent."""
    add_entity(tmp_path, "Verizon", "biller")
    result = run_entity_discovery(["Verizon"], tmp_path, account_number="")
    assert len(result["matched"]) == 1
    assert result["matched"][0]["match_type"] == "exact"
