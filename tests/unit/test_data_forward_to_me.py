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
