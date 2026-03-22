"""Unit tests for postmule.data.bills."""

from pathlib import Path

import pytest

from postmule.data.bills import add_bill, find_bill, load_bills, save_bills, to_sheet_rows, update_bill_status


def test_add_and_load(tmp_path):
    bill = {
        "date_received": "2025-03-01",
        "sender": "ATT",
        "amount_due": 94.0,
        "due_date": "2025-04-05",
        "status": "pending",
    }
    saved = add_bill(tmp_path, bill)
    assert "id" in saved

    loaded = load_bills(tmp_path, 2025)
    assert len(loaded) == 1
    assert loaded[0]["sender"] == "ATT"


def test_find_bill(tmp_path):
    bill = add_bill(tmp_path, {"date_received": "2025-03-01", "sender": "Verizon"})
    found = find_bill(tmp_path, bill["id"])
    assert found is not None
    assert found["sender"] == "Verizon"


def test_find_bill_not_found(tmp_path):
    assert find_bill(tmp_path, "nonexistent-id") is None


def test_update_status(tmp_path):
    bill = add_bill(tmp_path, {"date_received": "2025-03-01", "sender": "PGE", "status": "pending"})
    ok = update_bill_status(tmp_path, bill["id"], "paid", "txn-123")
    assert ok
    updated = find_bill(tmp_path, bill["id"])
    assert updated["status"] == "paid"
    assert updated["matched_transaction_id"] == "txn-123"


def test_to_sheet_rows(tmp_path):
    add_bill(tmp_path, {"date_received": "2025-03-01", "sender": "ATT", "amount_due": 94.0, "recipients": ["Alice"]})
    bills = load_bills(tmp_path, 2025)
    rows = to_sheet_rows(bills)
    assert rows[0] == ["ID", "Date Received", "Date Processed", "Sender", "Recipients",
                       "Amount Due", "Due Date", "Account Number", "Summary",
                       "Drive File ID", "Filename", "Status", "Matched Transaction ID", "Alert Sent Date"]
    assert rows[1][3] == "ATT"
