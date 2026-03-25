"""
Extended unit tests for postmule/data/bills.py

Covers: mark_bill_alerted, update_bill_status not-found,
        _atomic_write error path, _year_from edge cases,
        add_bill with no date, _recent_years.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from postmule.data.bills import (
    add_bill,
    find_bill,
    load_bills,
    mark_bill_alerted,
    save_bills,
    to_sheet_rows,
    update_bill_status,
)
from postmule.data._io import atomic_write as _atomic_write, year_from as _year_from, recent_years as _recent_years


# ---------------------------------------------------------------------------
# mark_bill_alerted
# ---------------------------------------------------------------------------

class TestMarkBillAlerted:
    def test_sets_alert_sent_date_to_today(self, tmp_path):
        bill = add_bill(tmp_path, {"date_received": "2025-03-01", "sender": "ATT"})
        result = mark_bill_alerted(tmp_path, bill["id"])
        assert result is True
        found = find_bill(tmp_path, bill["id"])
        assert found["alert_sent_date"] == date.today().isoformat()

    def test_returns_false_when_bill_not_found(self, tmp_path):
        result = mark_bill_alerted(tmp_path, "nonexistent-id")
        assert result is False

    def test_overwrites_previous_alert_date(self, tmp_path):
        bill = add_bill(tmp_path, {
            "date_received": "2025-03-01",
            "sender": "ATT",
            "alert_sent_date": "2025-01-01",
        })
        mark_bill_alerted(tmp_path, bill["id"])
        found = find_bill(tmp_path, bill["id"])
        assert found["alert_sent_date"] == date.today().isoformat()

    def test_persists_across_reload(self, tmp_path):
        bill = add_bill(tmp_path, {"date_received": "2025-03-01", "sender": "PGE"})
        mark_bill_alerted(tmp_path, bill["id"])
        bills = load_bills(tmp_path, year=2025)
        match = next((b for b in bills if b["id"] == bill["id"]), None)
        assert match is not None
        assert match["alert_sent_date"] == date.today().isoformat()


# ---------------------------------------------------------------------------
# update_bill_status — not found
# ---------------------------------------------------------------------------

class TestUpdateBillStatusNotFound:
    def test_returns_false_when_bill_missing(self, tmp_path):
        result = update_bill_status(tmp_path, "no-such-id", "paid")
        assert result is False

    def test_returns_true_when_found_without_transaction_id(self, tmp_path):
        bill = add_bill(tmp_path, {"date_received": "2025-05-01", "sender": "Netflix"})
        result = update_bill_status(tmp_path, bill["id"], "paid")
        assert result is True
        found = find_bill(tmp_path, bill["id"])
        assert found["status"] == "paid"
        assert "matched_transaction_id" not in found


# ---------------------------------------------------------------------------
# _atomic_write — error path
# ---------------------------------------------------------------------------

class TestAtomicWriteErrorPath:
    def test_raises_and_cleans_up_on_write_error(self, tmp_path):
        target = tmp_path / "output.json"

        with patch("os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                _atomic_write(target, '{"test": true}')

        # No stale .tmp files left behind
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_creates_parent_directories(self, tmp_path):
        nested = tmp_path / "deep" / "nested"
        target = nested / "output.json"
        _atomic_write(target, '[]')
        assert target.exists()
        assert json.loads(target.read_text()) == []


# ---------------------------------------------------------------------------
# _year_from
# ---------------------------------------------------------------------------

class TestYearFrom:
    def test_extracts_year_from_valid_date(self):
        assert _year_from("2025-03-15") == 2025

    def test_returns_current_year_on_empty_string(self):
        assert _year_from("") == date.today().year

    def test_returns_current_year_on_none(self):
        assert _year_from(None) == date.today().year

    def test_returns_current_year_on_non_numeric(self):
        assert _year_from("XXXX-03-01") == date.today().year

    def test_returns_current_year_on_short_string(self):
        assert _year_from("20") == date.today().year


# ---------------------------------------------------------------------------
# _recent_years
# ---------------------------------------------------------------------------

class TestRecentYears:
    def test_returns_three_years_by_default(self):
        years = _recent_years()
        assert len(years) == 3

    def test_starts_with_current_year(self):
        years = _recent_years()
        assert years[0] == date.today().year

    def test_descending_order(self):
        years = _recent_years()
        assert years[0] > years[1] > years[2]

    def test_custom_n(self):
        years = _recent_years(n=5)
        assert len(years) == 5


# ---------------------------------------------------------------------------
# add_bill — edge cases
# ---------------------------------------------------------------------------

class TestAddBillEdgeCases:
    def test_preserves_existing_id(self, tmp_path):
        bill = add_bill(tmp_path, {
            "id": "fixed-id",
            "date_received": "2025-03-01",
            "sender": "PGE",
        })
        assert bill["id"] == "fixed-id"

    def test_assigns_id_when_empty_string(self, tmp_path):
        bill = add_bill(tmp_path, {
            "id": "",
            "date_received": "2025-03-01",
            "sender": "PGE",
        })
        assert bill["id"] != ""

    def test_defaults_to_current_year_when_no_date(self, tmp_path):
        bill = add_bill(tmp_path, {"sender": "Unknown"})
        current_year = date.today().year
        assert (tmp_path / f"bills_{current_year}.json").exists()


# ---------------------------------------------------------------------------
# to_sheet_rows — edge cases
# ---------------------------------------------------------------------------

class TestToSheetRowsEdgeCases:
    def test_empty_recipients_renders_as_empty_string(self):
        bill = {"id": "x", "recipients": [], "status": "pending"}
        rows = to_sheet_rows([bill])
        assert rows[1][4] == ""

    def test_missing_optional_fields_default_to_empty(self):
        rows = to_sheet_rows([{}])
        row = rows[1]
        # All fields should be empty strings or "pending"
        assert row[0] == ""   # id
        assert row[13] == "pending"  # status default (index shifted by 2 new fields)
