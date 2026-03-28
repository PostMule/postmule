"""Unit tests for postmule.data.forward_to_me."""

import json

import pytest

from postmule.data.forward_to_me import (
    add_item,
    get_pending_items,
    load_forward_to_me,
    save_forward_to_me,
    to_sheet_rows,
)


class TestLoadForwardToMe:
    def test_empty_when_no_file(self, tmp_path):
        assert load_forward_to_me(tmp_path) == []

    def test_loads_existing_data(self, tmp_path):
        data = [{"id": "1", "forwarding_status": "pending"}]
        (tmp_path / "forward_to_me.json").write_text(json.dumps(data), encoding="utf-8")
        assert load_forward_to_me(tmp_path) == data


class TestSaveForwardToMe:
    def test_creates_file(self, tmp_path):
        save_forward_to_me(tmp_path, [{"id": "x"}])
        assert (tmp_path / "forward_to_me.json").exists()

    def test_round_trip(self, tmp_path):
        data = [{"id": "x", "sender": "Visa"}]
        save_forward_to_me(tmp_path, data)
        assert load_forward_to_me(tmp_path) == data

    def test_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "sub"
        save_forward_to_me(nested, [])
        assert (nested / "forward_to_me.json").exists()


class TestAddItem:
    def test_assigns_id_when_missing(self, tmp_path):
        item = add_item(tmp_path, {"sender": "Visa"})
        assert "id" in item
        assert len(item["id"]) > 8

    def test_preserves_existing_id(self, tmp_path):
        item = add_item(tmp_path, {"id": "existing-id", "sender": "Visa"})
        assert item["id"] == "existing-id"

    def test_sets_default_forwarding_status(self, tmp_path):
        item = add_item(tmp_path, {"sender": "Visa"})
        assert item["forwarding_status"] == "pending"

    def test_preserves_existing_forwarding_status(self, tmp_path):
        item = add_item(tmp_path, {"sender": "Visa", "forwarding_status": "shipped"})
        assert item["forwarding_status"] == "shipped"

    def test_appends_multiple_items(self, tmp_path):
        add_item(tmp_path, {"sender": "A"})
        add_item(tmp_path, {"sender": "B"})
        assert len(load_forward_to_me(tmp_path)) == 2


class TestGetPendingItems:
    def test_returns_only_pending(self, tmp_path):
        add_item(tmp_path, {"sender": "A", "forwarding_status": "pending"})
        add_item(tmp_path, {"sender": "B", "forwarding_status": "shipped"})
        pending = get_pending_items(tmp_path)
        assert len(pending) == 1
        assert pending[0]["sender"] == "A"

    def test_empty_when_none_pending(self, tmp_path):
        add_item(tmp_path, {"sender": "A", "forwarding_status": "shipped"})
        assert get_pending_items(tmp_path) == []


class TestToSheetRows:
    def test_has_headers(self):
        rows = to_sheet_rows([])
        assert rows[0][0] == "ID"

    def test_maps_forwarding_status(self):
        item = {
            "id": "x",
            "date_received": "2025-01-01",
            "date_processed": "2025-01-02",
            "sender": "Visa",
            "recipients": ["Alice"],
            "summary": "New credit card",
            "drive_file_id": "abc",
            "filename": "file.pdf",
            "forwarding_status": "pending",
        }
        rows = to_sheet_rows([item])
        row = rows[1]
        assert row[8] == "pending"
        assert row[3] == "Visa"
        assert row[4] == "Alice"


class TestSetEntityOverride:
    def test_sets_override_and_returns_true(self, tmp_path):
        from postmule.data.forward_to_me import set_entity_override
        add_item(tmp_path, {"id": "ftm1", "sender": "Visa"})
        result = set_entity_override(tmp_path, "ftm1", "entity-uuid")
        assert result is True
        saved = load_forward_to_me(tmp_path)
        assert saved[0]["entity_override_id"] == "entity-uuid"

    def test_returns_false_when_not_found(self, tmp_path):
        from postmule.data.forward_to_me import set_entity_override
        assert set_entity_override(tmp_path, "ghost-id", "entity-uuid") is False


class TestSetCategoryOverride:
    def test_sets_category_and_returns_true(self, tmp_path):
        from postmule.data.forward_to_me import set_category_override
        add_item(tmp_path, {"id": "ftm2", "sender": "Visa"})
        result = set_category_override(tmp_path, "ftm2", "Personal")
        assert result is True
        saved = load_forward_to_me(tmp_path)
        assert saved[0]["category_override"] == "Personal"

    def test_returns_false_when_not_found(self, tmp_path):
        from postmule.data.forward_to_me import set_category_override
        assert set_category_override(tmp_path, "ghost-id", "Personal") is False


class TestSetOwnerIds:
    def test_sets_owner_ids_and_returns_true(self, tmp_path):
        from postmule.data.forward_to_me import set_owner_ids
        add_item(tmp_path, {"id": "ftm3", "sender": "Visa"})
        result = set_owner_ids(tmp_path, "ftm3", ["uuid-alice", "uuid-bob"])
        assert result is True
        saved = load_forward_to_me(tmp_path)
        assert saved[0]["owner_ids"] == ["uuid-alice", "uuid-bob"]

    def test_clears_owner_ids(self, tmp_path):
        from postmule.data.forward_to_me import set_owner_ids
        add_item(tmp_path, {"id": "ftm4", "sender": "Visa", "owner_ids": ["uuid-alice"]})
        set_owner_ids(tmp_path, "ftm4", [])
        saved = load_forward_to_me(tmp_path)
        assert saved[0]["owner_ids"] == []

    def test_returns_false_when_not_found(self, tmp_path):
        from postmule.data.forward_to_me import set_owner_ids
        assert set_owner_ids(tmp_path, "ghost-id", ["uuid-alice"]) is False


class TestSetFiled:
    def test_sets_filed_true_and_returns_true(self, tmp_path):
        from postmule.data.forward_to_me import set_filed
        add_item(tmp_path, {"id": "ftm-filed", "sender": "Visa"})
        result = set_filed(tmp_path, "ftm-filed", True)
        assert result is True
        saved = load_forward_to_me(tmp_path)
        assert saved[0]["filed"] is True

    def test_sets_filed_false(self, tmp_path):
        from postmule.data.forward_to_me import set_filed
        add_item(tmp_path, {"id": "ftm-unfiled", "sender": "Visa", "filed": True})
        set_filed(tmp_path, "ftm-unfiled", False)
        saved = load_forward_to_me(tmp_path)
        assert saved[0]["filed"] is False

    def test_returns_false_when_not_found(self, tmp_path):
        from postmule.data.forward_to_me import set_filed
        assert set_filed(tmp_path, "ghost-id", True) is False
