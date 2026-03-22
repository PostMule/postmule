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
  "account_number": "1234",
  "summary": "...",
  "drive_file_id": "...",
  "filename": "2025-11-15_Alice_ATT_Bill.pdf",
  "status": "pending" | "paid" | "matched",
  "matched_transaction_id": null,
  "alert_sent_date": "YYYY-MM-DD"   # date last bill-due alert was sent (null if never)
}
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

_HEADERS = [
    "ID", "Date Received", "Date Processed", "Sender", "Recipients",
    "Amount Due", "Due Date", "Account Number", "Summary",
    "Drive File ID", "Filename", "Status", "Matched Transaction ID",
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
    _atomic_write(path, json.dumps(bills, indent=2, ensure_ascii=False))


def add_bill(data_dir: Path, bill: dict[str, Any]) -> dict[str, Any]:
    """Add a bill record; assign a UUID if not present. Returns the saved record."""
    year = _year_from(bill.get("date_received", ""))
    bills = load_bills(data_dir, year)
    if "id" not in bill or not bill["id"]:
        bill["id"] = str(uuid.uuid4())
    bills.append(bill)
    save_bills(data_dir, bills, year)
    return bill


def find_bill(data_dir: Path, bill_id: str) -> dict[str, Any] | None:
    for year in _recent_years():
        for bill in load_bills(data_dir, year):
            if bill.get("id") == bill_id:
                return bill
    return None


def update_bill_status(data_dir: Path, bill_id: str, status: str, transaction_id: str | None = None) -> bool:
    for year in _recent_years():
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
    for year in _recent_years():
        bills = load_bills(data_dir, year)
        for bill in bills:
            if bill.get("id") == bill_id:
                bill["alert_sent_date"] = today
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
            b.get("account_number", ""),
            b.get("summary", ""),
            b.get("drive_file_id", ""),
            b.get("filename", ""),
            b.get("status", "pending"),
            b.get("matched_transaction_id", ""),
        ])
    return rows


def _atomic_write(path: Path, text: str) -> None:
    """Write text to path atomically via a sibling temp file + os.replace()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _year_from(date_str: str) -> int:
    try:
        return int(date_str[:4])
    except (ValueError, TypeError):
        return date.today().year


def _recent_years(n: int = 3) -> list[int]:
    current = date.today().year
    return list(range(current, current - n, -1))
