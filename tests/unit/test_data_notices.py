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
