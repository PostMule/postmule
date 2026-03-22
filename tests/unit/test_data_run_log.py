"""Unit tests for postmule.data.run_log."""

from pathlib import Path

import pytest

from postmule.data.run_log import (
    append_run,
    get_last_run,
    load_run_log,
    to_sheet_rows,
)


class TestLoadRunLog:
    def test_returns_empty_list_when_no_file(self, tmp_path):
        assert load_run_log(tmp_path) == []

    def test_loads_existing_entries(self, tmp_path):
        import json
        entries = [{"run_id": "abc", "status": "success"}]
        (tmp_path / "run_log.json").write_text(json.dumps(entries), encoding="utf-8")
        assert load_run_log(tmp_path) == entries


class TestAppendRun:
    def test_creates_file_on_first_append(self, tmp_path):
        append_run(tmp_path, {"status": "success"})
        assert (tmp_path / "run_log.json").exists()

    def test_auto_assigns_run_id(self, tmp_path):
        append_run(tmp_path, {"status": "success"})
        log = load_run_log(tmp_path)
        assert "run_id" in log[0]
        assert len(log[0]["run_id"]) > 8

    def test_preserves_provided_run_id(self, tmp_path):
        append_run(tmp_path, {"run_id": "my-id", "status": "success"})
        log = load_run_log(tmp_path)
        assert log[0]["run_id"] == "my-id"

    def test_appends_multiple_entries(self, tmp_path):
        for i in range(3):
            append_run(tmp_path, {"status": "success", "n": i})
        log = load_run_log(tmp_path)
        assert len(log) == 3

    def test_caps_at_365_entries(self, tmp_path):
        for i in range(370):
            append_run(tmp_path, {"status": "success", "n": i})
        log = load_run_log(tmp_path)
        assert len(log) == 365

    def test_creates_parent_directories(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        append_run(nested, {"status": "success"})
        assert (nested / "run_log.json").exists()


class TestGetLastRun:
    def test_returns_none_when_empty(self, tmp_path):
        assert get_last_run(tmp_path) is None

    def test_returns_last_entry(self, tmp_path):
        append_run(tmp_path, {"status": "success", "n": 1})
        append_run(tmp_path, {"status": "failed", "n": 2})
        last = get_last_run(tmp_path)
        assert last["n"] == 2
        assert last["status"] == "failed"


class TestToSheetRows:
    def test_returns_header_row(self):
        rows = to_sheet_rows([])
        assert rows[0][0] == "Run ID"

    def test_maps_fields_correctly(self):
        entry = {
            "run_id": "abc",
            "start_time": "2025-01-01T02:00:00",
            "end_time": "2025-01-01T02:05:00",
            "status": "success",
            "emails_found": 5,
            "pdfs_processed": 4,
            "bills": 2,
            "notices": 1,
            "forward_to_me": 0,
            "junk": 1,
            "needs_review": 0,
            "errors": ["oops"],
        }
        rows = to_sheet_rows([entry])
        data_row = rows[1]  # rows[0] is headers, entries are most-recent-first
        assert data_row[0] == "abc"
        assert data_row[3] == "success"
        assert data_row[4] == 5
        assert data_row[11] == "oops"

    def test_most_recent_first_order(self):
        entries = [{"run_id": "first"}, {"run_id": "last"}]
        rows = to_sheet_rows(entries)
        assert rows[1][0] == "last"
        assert rows[2][0] == "first"
