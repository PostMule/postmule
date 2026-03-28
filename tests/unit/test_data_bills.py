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
                       "Amount Due", "Due Date", "Statement Date", "Account Number", "ACH Descriptor", "Summary",
                       "Drive File ID", "Filename", "Status", "Matched Transaction ID", "Alert Sent Date"]
    assert rows[1][3] == "ATT"


def test_to_sheet_rows_includes_new_fields(tmp_path):
    add_bill(tmp_path, {
        "date_received": "2025-03-01",
        "sender": "ATT",
        "amount_due": 94.0,
        "recipients": ["Alice"],
        "statement_date": "2025-03-15",
        "ach_descriptor": "ATT*PAYMENT",
    })
    bills = load_bills(tmp_path, 2025)
    rows = to_sheet_rows(bills)
    header = rows[0]
    data_row = rows[1]
    stmt_idx = header.index("Statement Date")
    ach_idx = header.index("ACH Descriptor")
    assert data_row[stmt_idx] == "2025-03-15"
    assert data_row[ach_idx] == "ATT*PAYMENT"


def test_new_fields_default_to_empty_in_sheet_rows(tmp_path):
    add_bill(tmp_path, {"date_received": "2025-03-01", "sender": "PGE", "amount_due": 50.0})
    bills = load_bills(tmp_path, 2025)
    rows = to_sheet_rows(bills)
    header = rows[0]
    data_row = rows[1]
    assert data_row[header.index("Statement Date")] == ""
    assert data_row[header.index("ACH Descriptor")] == ""


class TestSetOwnerIds:
    def test_sets_owner_ids_and_returns_true(self, tmp_path):
        from postmule.data.bills import set_owner_ids
        add_bill(tmp_path, {"id": "b1", "date_received": "2025-03-01", "status": "pending"})
        result = set_owner_ids(tmp_path, "b1", ["uuid-alice", "uuid-bob"])
        assert result is True
        saved = load_bills(tmp_path, year=2025)
        assert saved[0]["owner_ids"] == ["uuid-alice", "uuid-bob"]

    def test_clears_owner_ids(self, tmp_path):
        from postmule.data.bills import set_owner_ids
        add_bill(tmp_path, {"id": "b2", "date_received": "2025-03-01",
                            "status": "pending", "owner_ids": ["uuid-alice"]})
        set_owner_ids(tmp_path, "b2", [])
        saved = load_bills(tmp_path, year=2025)
        assert saved[0]["owner_ids"] == []

    def test_returns_false_when_not_found(self, tmp_path):
        from postmule.data.bills import set_owner_ids
        assert set_owner_ids(tmp_path, "ghost-id", ["uuid-alice"]) is False


class TestSetFiled:
    def test_sets_filed_true_and_returns_true(self, tmp_path):
        from postmule.data.bills import set_filed
        add_bill(tmp_path, {"id": "b-filed", "date_received": "2025-03-01", "status": "pending"})
        result = set_filed(tmp_path, "b-filed", True)
        assert result is True
        saved = load_bills(tmp_path, year=2025)
        assert saved[0]["filed"] is True

    def test_sets_filed_false(self, tmp_path):
        from postmule.data.bills import set_filed
        add_bill(tmp_path, {"id": "b-unfiled", "date_received": "2025-03-01",
                            "status": "pending", "filed": True})
        set_filed(tmp_path, "b-unfiled", False)
        saved = load_bills(tmp_path, year=2025)
        assert saved[0]["filed"] is False

    def test_returns_false_when_not_found(self, tmp_path):
        from postmule.data.bills import set_filed
        assert set_filed(tmp_path, "ghost-id", True) is False
