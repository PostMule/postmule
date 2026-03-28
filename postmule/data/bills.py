"""
Bills JSON data layer — reads/writes bills_YYYY.json.

Schema for each bill record:
{
  "id": "uuid",
  "date_received": "YYYY-MM-DD",
  "date_processed": "YYYY-MM-DD",
  "sender": "ATT",
  "recipients": ["Alice"],
  "amount_due": 94.00,
  "due_date": "YYYY-MM-DD",
  "statement_date": "YYYY-MM-DD",   # billing cycle/statement date (may differ from due_date)
  "account_number": "1234",
  "ach_descriptor": "ATT*PAYMENT",  # ACH descriptor as shown on bank statements (for matching)
  "summary": "...",
  "drive_file_id": "...",
  "filename": "2025-11-15_Alice_ATT_Bill.pdf",
  "status": "pending" | "paid" | "matched",
  "matched_transaction_id": null,
  "alert_sent_date": "YYYY-MM-DD",  # date last bill-due alert was sent (null if never)
  "owner_ids": []                   # resolved owner UUIDs (from owners.json); [] = unassigned
}
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from postmule.data._io import atomic_write, recent_years, year_from

_HEADERS = [
    "ID", "Date Received", "Date Processed", "Sender", "Recipients",
    "Amount Due", "Due Date", "Statement Date", "Account Number", "ACH Descriptor", "Summary",
    "Drive File ID", "Filename", "Status", "Matched Transaction ID", "Alert Sent Date",
]


def _data_file(data_dir: Path, year: int | None = None) -> Path:
    y = year or date.today().year
    return data_dir / f"bills_{y}.json"


def load_bills(data_dir: Path, year: int | None = None) -> list[dict[str, Any]]:
    path = _data_file(data_dir, year)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_bills(data_dir: Path, bills: list[dict[str, Any]], year: int | None = None) -> None:
    path = _data_file(data_dir, year)
    atomic_write(path, json.dumps(bills, indent=2, ensure_ascii=False))


def add_bill(data_dir: Path, bill: dict[str, Any]) -> dict[str, Any]:
    """Add a bill record; assign a UUID if not present. Returns the saved record."""
    year = year_from(bill.get("date_received", ""))
    bills = load_bills(data_dir, year)
    if "id" not in bill or not bill["id"]:
        bill["id"] = str(uuid.uuid4())
    bills.append(bill)
    save_bills(data_dir, bills, year)
    return bill


def find_bill(data_dir: Path, bill_id: str) -> dict[str, Any] | None:
    for year in recent_years():
        for bill in load_bills(data_dir, year):
            if bill.get("id") == bill_id:
                return bill
    return None


def update_bill_status(data_dir: Path, bill_id: str, status: str, transaction_id: str | None = None) -> bool:
    for year in recent_years():
        bills = load_bills(data_dir, year)
        for bill in bills:
            if bill.get("id") == bill_id:
                bill["status"] = status
                if transaction_id is not None:
                    bill["matched_transaction_id"] = transaction_id
                save_bills(data_dir, bills, year)
                return True
    return False


def mark_bill_alerted(data_dir: Path, bill_id: str) -> bool:
    """Set alert_sent_date to today on a bill record. Returns True if found."""
    today = date.today().isoformat()
    for year in recent_years():
        bills = load_bills(data_dir, year)
        for bill in bills:
            if bill.get("id") == bill_id:
                bill["alert_sent_date"] = today
                save_bills(data_dir, bills, year)
                return True
    return False


def set_entity_override(data_dir: Path, bill_id: str, entity_id: str) -> bool:
    """Set entity_override_id on a bill record. Returns True if found and updated."""
    for year in recent_years():
        bills = load_bills(data_dir, year)
        for bill in bills:
            if bill.get("id") == bill_id:
                bill["entity_override_id"] = entity_id
                save_bills(data_dir, bills, year)
                return True
    return False


def set_owner_ids(data_dir: Path, bill_id: str, owner_ids: list[str]) -> bool:
    """Set owner_ids on a bill record. Returns True if found."""
    for year in recent_years():
        bills = load_bills(data_dir, year)
        for bill in bills:
            if bill.get("id") == bill_id:
                bill["owner_ids"] = owner_ids
                save_bills(data_dir, bills, year)
                return True
    return False


def set_category_override(data_dir: Path, bill_id: str, category: str) -> bool:
    """Set category_override on a bill record. Returns True if found and updated."""
    for year in recent_years():
        bills = load_bills(data_dir, year)
        for bill in bills:
            if bill.get("id") == bill_id:
                bill["category_override"] = category
                save_bills(data_dir, bills, year)
                return True
    return False


def to_sheet_rows(bills: list[dict[str, Any]]) -> list[list[Any]]:
    rows = [_HEADERS]
    for b in bills:
        rows.append([
            b.get("id", ""),
            b.get("date_received", ""),
            b.get("date_processed", ""),
            b.get("sender", ""),
            ", ".join(b.get("recipients", [])),
            b.get("amount_due", ""),
            b.get("due_date", ""),
            b.get("statement_date", ""),
            b.get("account_number", ""),
            b.get("ach_descriptor", ""),
            b.get("summary", ""),
            b.get("drive_file_id", ""),
            b.get("filename", ""),
            b.get("status", "pending"),
            b.get("matched_transaction_id", ""),
            b.get("alert_sent_date", ""),
        ])
    return rows


