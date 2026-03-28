"""Unit tests for postmule.data.owners."""

import json

import pytest

from postmule.data.owners import (
    OWNER_TYPES,
    add_owner,
    deactivate_owner,
    get_owner,
    load_owners,
    resolve_owner_ids,
    save_owners,
    update_owner,
)


class TestLoadOwners:
    def test_empty_when_no_file(self, tmp_path):
        assert load_owners(tmp_path) == []

    def test_returns_active_owners_by_default(self, tmp_path):
        data = [
            {"id": "a1", "name": "Alice", "active": True},
            {"id": "b1", "name": "Bob", "active": False},
        ]
        (tmp_path / "owners.json").write_text(json.dumps(data), encoding="utf-8")
        result = load_owners(tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    def test_include_inactive_returns_all(self, tmp_path):
        data = [
            {"id": "a1", "name": "Alice", "active": True},
            {"id": "b1", "name": "Bob", "active": False},
        ]
        (tmp_path / "owners.json").write_text(json.dumps(data), encoding="utf-8")
        result = load_owners(tmp_path, include_inactive=True)
        assert len(result) == 2

    def test_missing_active_field_treated_as_active(self, tmp_path):
        data = [{"id": "a1", "name": "Alice"}]
        (tmp_path / "owners.json").write_text(json.dumps(data), encoding="utf-8")
        result = load_owners(tmp_path)
        assert len(result) == 1


class TestSaveOwners:
    def test_round_trip(self, tmp_path):
        owners = [{"id": "x1", "name": "Alice", "active": True}]
        save_owners(tmp_path, owners)
        assert load_owners(tmp_path) == owners

    def test_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "sub" / "data"
        save_owners(nested, [])
        assert (nested / "owners.json").exists()


class TestAddOwner:
    def test_assigns_uuid(self, tmp_path):
        owner = add_owner(tmp_path, "Alice")
        assert len(owner["id"]) > 8

    def test_defaults_to_person_type(self, tmp_path):
        owner = add_owner(tmp_path, "Alice")
        assert owner["type"] == "person"

    def test_company_type(self, tmp_path):
        owner = add_owner(tmp_path, "Example LLC", "company")
        assert owner["type"] == "company"

    def test_invalid_type_defaults_to_person(self, tmp_path):
        owner = add_owner(tmp_path, "X", "robot")
        assert owner["type"] == "person"

    def test_short_name_and_color(self, tmp_path):
        owner = add_owner(tmp_path, "Alice Smith", short_name="Alice", color="#7C3AED")
        assert owner["short_name"] == "Alice"
        assert owner["color"] == "#7C3AED"

    def test_active_by_default(self, tmp_path):
        owner = add_owner(tmp_path, "Alice")
        assert owner["active"] is True

    def test_persists(self, tmp_path):
        add_owner(tmp_path, "Alice")
        assert len(load_owners(tmp_path)) == 1

    def test_appends(self, tmp_path):
        add_owner(tmp_path, "Alice")
        add_owner(tmp_path, "Bob")
        assert len(load_owners(tmp_path)) == 2


class TestGetOwner:
    def test_returns_owner_by_id(self, tmp_path):
        owner = add_owner(tmp_path, "Alice")
        result = get_owner(tmp_path, owner["id"])
        assert result is not None
        assert result["name"] == "Alice"

    def test_returns_inactive_owner(self, tmp_path):
        owner = add_owner(tmp_path, "Alice")
        deactivate_owner(tmp_path, owner["id"])
        result = get_owner(tmp_path, owner["id"])
        assert result is not None

    def test_returns_none_when_not_found(self, tmp_path):
        assert get_owner(tmp_path, "ghost-id") is None


class TestUpdateOwner:
    def test_updates_name(self, tmp_path):
        owner = add_owner(tmp_path, "Alice")
        updated = update_owner(tmp_path, owner["id"], {"name": "Alice Smith"})
        assert updated["name"] == "Alice Smith"

    def test_persists_update(self, tmp_path):
        owner = add_owner(tmp_path, "Alice")
        update_owner(tmp_path, owner["id"], {"color": "#FF0000"})
        reloaded = get_owner(tmp_path, owner["id"])
        assert reloaded["color"] == "#FF0000"

    def test_ignores_id_and_created_date(self, tmp_path):
        owner = add_owner(tmp_path, "Alice")
        original_id = owner["id"]
        update_owner(tmp_path, owner["id"], {"id": "hacked", "created_date": "1900-01-01"})
        reloaded = get_owner(tmp_path, original_id)
        assert reloaded["id"] == original_id

    def test_ignores_invalid_type(self, tmp_path):
        owner = add_owner(tmp_path, "Alice")
        update_owner(tmp_path, owner["id"], {"type": "robot"})
        reloaded = get_owner(tmp_path, owner["id"])
        assert reloaded["type"] == "person"

    def test_returns_none_when_not_found(self, tmp_path):
        assert update_owner(tmp_path, "ghost-id", {"name": "X"}) is None


class TestDeactivateOwner:
    def test_sets_active_false(self, tmp_path):
        owner = add_owner(tmp_path, "Alice")
        result = deactivate_owner(tmp_path, owner["id"])
        assert result is True
        reloaded = get_owner(tmp_path, owner["id"])
        assert reloaded["active"] is False

    def test_hides_from_default_load(self, tmp_path):
        owner = add_owner(tmp_path, "Alice")
        deactivate_owner(tmp_path, owner["id"])
        assert load_owners(tmp_path) == []

    def test_returns_false_when_not_found(self, tmp_path):
        assert deactivate_owner(tmp_path, "ghost-id") is False


class TestResolveOwnerIds:
    def _owners(self):
        return [
            {"id": "uuid-alice", "name": "Alice", "short_name": None, "active": True},
            {"id": "uuid-bob", "name": "Bob", "short_name": "Bobby", "active": True},
            {"id": "uuid-llc", "name": "Example LLC", "short_name": "LLC1", "active": True},
            {"id": "uuid-inactive", "name": "Carol", "short_name": None, "active": False},
        ]

    def test_exact_match(self):
        owners = self._owners()
        result = resolve_owner_ids(["Alice"], owners)
        assert result == ["uuid-alice"]

    def test_case_insensitive_match(self):
        owners = self._owners()
        result = resolve_owner_ids(["alice"], owners)
        assert result == ["uuid-alice"]

    def test_short_name_match(self):
        owners = self._owners()
        result = resolve_owner_ids(["Bobby"], owners)
        assert result == ["uuid-bob"]

    def test_multiple_recipients(self):
        owners = self._owners()
        result = resolve_owner_ids(["Alice", "Bob"], owners)
        assert result == ["uuid-alice", "uuid-bob"]

    def test_unmatched_is_dropped(self):
        owners = self._owners()
        result = resolve_owner_ids(["Unknown Person"], owners)
        assert result == []

    def test_mixed_matched_and_unmatched(self):
        owners = self._owners()
        result = resolve_owner_ids(["Alice", "Nobody"], owners)
        assert result == ["uuid-alice"]

    def test_inactive_owner_not_matched(self):
        owners = self._owners()
        result = resolve_owner_ids(["Carol"], owners)
        assert result == []

    def test_deduplicates(self):
        owners = self._owners()
        result = resolve_owner_ids(["Alice", "Alice"], owners)
        assert result == ["uuid-alice"]

    def test_empty_recipients(self):
        owners = self._owners()
        assert resolve_owner_ids([], owners) == []

    def test_empty_owners(self):
        assert resolve_owner_ids(["Alice"], []) == []
