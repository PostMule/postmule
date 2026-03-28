"""Unit tests for postmule.data.notices."""

import json

import pytest

from postmule.data.notices import (
    add_notice,
    load_notices,
    save_notices,
    to_sheet_rows,
)


class TestLoadNotices:
    def test_empty_when_no_file(self, tmp_path):
        assert load_notices(tmp_path) == []

    def test_loads_current_year_by_default(self, tmp_path):
        from datetime import date
        year = date.today().year
        data = [{"sender": "IRS", "id": "x"}]
        (tmp_path / f"notices_{year}.json").write_text(json.dumps(data), encoding="utf-8")
        assert load_notices(tmp_path) == data

    def test_loads_specified_year(self, tmp_path):
        data = [{"sender": "IRS"}]
        (tmp_path / "notices_2023.json").write_text(json.dumps(data), encoding="utf-8")
        assert load_notices(tmp_path, year=2023) == data


class TestSaveNotices:
    def test_creates_file(self, tmp_path):
        save_notices(tmp_path, [{"id": "1"}], year=2025)
        assert (tmp_path / "notices_2025.json").exists()

    def test_round_trip(self, tmp_path):
        data = [{"id": "abc", "sender": "AT&T"}]
        save_notices(tmp_path, data, year=2025)
        assert load_notices(tmp_path, year=2025) == data

    def test_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "x" / "y"
        save_notices(nested, [], year=2025)
        assert (nested / "notices_2025.json").exists()


class TestAddNotice:
    def test_assigns_id_when_missing(self, tmp_path):
        notice = add_notice(tmp_path, {"sender": "IRS", "date_received": "2025-01-15"})
        assert "id" in notice
        assert len(notice["id"]) > 8

    def test_preserves_existing_id(self, tmp_path):
        notice = add_notice(tmp_path, {"id": "my-id", "date_received": "2025-01-15"})
        assert notice["id"] == "my-id"

    def test_persists_to_correct_year_file(self, tmp_path):
        add_notice(tmp_path, {"date_received": "2025-06-01", "sender": "Test"})
        assert (tmp_path / "notices_2025.json").exists()
        saved = load_notices(tmp_path, year=2025)
        assert saved[0]["sender"] == "Test"

    def test_appends_to_existing(self, tmp_path):
        add_notice(tmp_path, {"date_received": "2025-01-01", "sender": "A"})
        add_notice(tmp_path, {"date_received": "2025-01-02", "sender": "B"})
        saved = load_notices(tmp_path, year=2025)
        assert len(saved) == 2


class TestToSheetRows:
    def test_has_headers(self):
        rows = to_sheet_rows([])
        assert rows[0][0] == "ID"

    def test_maps_fields(self):
        notice = {
            "id": "x1",
            "date_received": "2025-01-01",
            "date_processed": "2025-01-02",
            "sender": "IRS",
            "recipients": ["Alice", "Bob"],
            "summary": "Tax notice",
            "drive_file_id": "abc123",
            "filename": "2025-01-01_Alice_IRS_Notice.pdf",
        }
        rows = to_sheet_rows([notice])
        row = rows[1]
        assert row[0] == "x1"
        assert row[3] == "IRS"
        assert row[4] == "Alice, Bob"
        assert row[7] == "2025-01-01_Alice_IRS_Notice.pdf"


class TestFindNotice:
    def test_returns_none_when_not_found(self, tmp_path):
        from postmule.data.notices import find_notice
        assert find_notice(tmp_path, "nonexistent-id") is None

    def test_finds_notice_by_id(self, tmp_path):
        from postmule.data.notices import find_notice
        added = add_notice(tmp_path, {"id": "target-id", "date_received": "2025-03-01", "sender": "IRS"})
        result = find_notice(tmp_path, "target-id")
        assert result is not None
        assert result["sender"] == "IRS"

    def test_returns_none_for_wrong_id(self, tmp_path):
        from postmule.data.notices import find_notice
        add_notice(tmp_path, {"id": "real-id", "date_received": "2025-03-01"})
        assert find_notice(tmp_path, "wrong-id") is None


class TestSetEntityOverride:
    def test_sets_override_and_returns_true(self, tmp_path):
        from postmule.data.notices import set_entity_override
        add_notice(tmp_path, {"id": "n1", "date_received": "2025-03-01", "sender": "IRS"})
        result = set_entity_override(tmp_path, "n1", "entity-uuid")
        assert result is True
        saved = load_notices(tmp_path, year=2025)
        assert saved[0]["entity_override_id"] == "entity-uuid"

    def test_returns_false_when_not_found(self, tmp_path):
        from postmule.data.notices import set_entity_override
        assert set_entity_override(tmp_path, "ghost-id", "entity-uuid") is False


class TestSetCategoryOverride:
    def test_sets_category_and_returns_true(self, tmp_path):
        from postmule.data.notices import set_category_override
        add_notice(tmp_path, {"id": "n2", "date_received": "2025-03-01", "sender": "IRS"})
        result = set_category_override(tmp_path, "n2", "Junk")
        assert result is True
        saved = load_notices(tmp_path, year=2025)
        assert saved[0]["category_override"] == "Junk"

    def test_returns_false_when_not_found(self, tmp_path):
        from postmule.data.notices import set_category_override
        assert set_category_override(tmp_path, "ghost-id", "Junk") is False


class TestSetOwnerIds:
    def test_sets_owner_ids_and_returns_true(self, tmp_path):
        from postmule.data.notices import set_owner_ids
        add_notice(tmp_path, {"id": "n3", "date_received": "2025-03-01", "sender": "IRS"})
        result = set_owner_ids(tmp_path, "n3", ["uuid-alice", "uuid-bob"])
        assert result is True
        saved = load_notices(tmp_path, year=2025)
        assert saved[0]["owner_ids"] == ["uuid-alice", "uuid-bob"]

    def test_clears_owner_ids(self, tmp_path):
        from postmule.data.notices import set_owner_ids
        add_notice(tmp_path, {"id": "n4", "date_received": "2025-03-01",
                              "sender": "IRS", "owner_ids": ["uuid-alice"]})
        set_owner_ids(tmp_path, "n4", [])
        saved = load_notices(tmp_path, year=2025)
        assert saved[0]["owner_ids"] == []

    def test_returns_false_when_not_found(self, tmp_path):
        from postmule.data.notices import set_owner_ids
        assert set_owner_ids(tmp_path, "ghost-id", ["uuid-alice"]) is False


class TestSetFiled:
    def test_sets_filed_true_and_returns_true(self, tmp_path):
        from postmule.data.notices import set_filed
        add_notice(tmp_path, {"id": "n-filed", "date_received": "2025-03-01", "sender": "IRS"})
        result = set_filed(tmp_path, "n-filed", True)
        assert result is True
        saved = load_notices(tmp_path, year=2025)
        assert saved[0]["filed"] is True

    def test_sets_filed_false(self, tmp_path):
        from postmule.data.notices import set_filed
        add_notice(tmp_path, {"id": "n-unfiled", "date_received": "2025-03-01",
                              "sender": "IRS", "filed": True})
        set_filed(tmp_path, "n-unfiled", False)
        saved = load_notices(tmp_path, year=2025)
        assert saved[0]["filed"] is False

    def test_returns_false_when_not_found(self, tmp_path):
        from postmule.data.notices import set_filed
        assert set_filed(tmp_path, "ghost-id", True) is False
