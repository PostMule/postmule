"""
Unit tests for SqliteSpreadsheetProvider.
All tests use a temporary directory — no side effects outside tmp_path.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from postmule.providers.spreadsheet.sqlite import SqliteSpreadsheetProvider, _safe_identifier, _pad_row


@pytest.fixture
def provider(tmp_path):
    return SqliteSpreadsheetProvider(db_path=tmp_path / "postmule.db")


class TestGetOrCreateWorkbook:
    def test_creates_db_file(self, provider):
        provider.get_or_create_workbook()
        assert provider.db_path.exists()

    def test_returns_db_path_string(self, provider):
        result = provider.get_or_create_workbook()
        assert result == str(provider.db_path)

    def test_idempotent(self, provider):
        provider.get_or_create_workbook()
        result = provider.get_or_create_workbook()
        assert result == str(provider.db_path)

    def test_drive_folder_id_ignored(self, provider):
        result = provider.get_or_create_workbook(drive_folder_id="some-drive-id")
        assert result == str(provider.db_path)


class TestWriteSheet:
    def test_creates_table_with_headers(self, provider):
        provider.get_or_create_workbook()
        provider.write_sheet("Bills", [["Sender", "Amount", "Date"]])
        conn = sqlite3.connect(provider.db_path)
        cur = conn.execute('SELECT * FROM "Bills"')
        cols = [d[0] for d in cur.description]
        conn.close()
        assert cols == ["Sender", "Amount", "Date"]

    def test_writes_data_rows(self, provider):
        provider.get_or_create_workbook()
        provider.write_sheet("Bills", [
            ["Sender", "Amount"],
            ["ATT", "120.00"],
            ["Comcast", "89.99"],
        ])
        conn = sqlite3.connect(provider.db_path)
        rows = conn.execute('SELECT * FROM "Bills"').fetchall()
        conn.close()
        assert len(rows) == 2
        assert rows[0] == ("ATT", "120.00")
        assert rows[1] == ("Comcast", "89.99")

    def test_overwrites_on_second_write(self, provider):
        provider.get_or_create_workbook()
        provider.write_sheet("RunLog", [["Status"], ["success"]])
        provider.write_sheet("RunLog", [["Status"], ["failed"], ["success"]])
        conn = sqlite3.connect(provider.db_path)
        rows = conn.execute('SELECT * FROM "RunLog"').fetchall()
        conn.close()
        assert len(rows) == 2

    def test_empty_rows_is_noop(self, provider):
        provider.get_or_create_workbook()
        provider.write_sheet("Empty", [])

    def test_none_values_become_empty_string(self, provider):
        provider.get_or_create_workbook()
        provider.write_sheet("Test", [["A", "B"], [None, "x"]])
        conn = sqlite3.connect(provider.db_path)
        row = conn.execute('SELECT * FROM "Test"').fetchone()
        conn.close()
        assert row == ("", "x")

    def test_short_rows_are_padded(self, provider):
        provider.get_or_create_workbook()
        provider.write_sheet("Test", [["A", "B", "C"], ["only_one"]])
        conn = sqlite3.connect(provider.db_path)
        row = conn.execute('SELECT * FROM "Test"').fetchone()
        conn.close()
        assert row == ("only_one", "", "")

    def test_long_rows_are_trimmed(self, provider):
        provider.get_or_create_workbook()
        provider.write_sheet("Test", [["A", "B"], ["x", "y", "z_extra"]])
        conn = sqlite3.connect(provider.db_path)
        row = conn.execute('SELECT * FROM "Test"').fetchone()
        conn.close()
        assert row == ("x", "y")

    def test_multiple_sheets_independent(self, provider):
        provider.get_or_create_workbook()
        provider.write_sheet("Bills", [["Sender"], ["ATT"]])
        provider.write_sheet("Notices", [["Text"], ["hello"]])
        conn = sqlite3.connect(provider.db_path)
        bills = conn.execute('SELECT * FROM "Bills"').fetchall()
        notices = conn.execute('SELECT * FROM "Notices"').fetchall()
        conn.close()
        assert bills == [("ATT",)]
        assert notices == [("hello",)]


class TestHealthCheck:
    def test_ok_after_workbook_created(self, provider):
        provider.get_or_create_workbook()
        result = provider.health_check()
        assert result.ok
        assert result.status == "ok"

    def test_ok_creates_file_if_needed(self, provider):
        result = provider.health_check()
        assert result.ok


class TestHelpers:
    def test_safe_identifier_alphanumeric(self):
        assert _safe_identifier("RunLog") == "RunLog"

    def test_safe_identifier_replaces_spaces(self):
        assert _safe_identifier("Run Log") == "Run_Log"

    def test_safe_identifier_replaces_dash(self):
        assert _safe_identifier("run-log") == "run_log"

    def test_pad_row_exact(self):
        assert _pad_row(["a", "b"], 2) == ["a", "b"]

    def test_pad_row_short(self):
        assert _pad_row(["a"], 3) == ["a", "", ""]

    def test_pad_row_long(self):
        assert _pad_row(["a", "b", "c"], 2) == ["a", "b"]

    def test_pad_row_none_to_empty(self):
        assert _pad_row([None, "x"], 2) == ["", "x"]
