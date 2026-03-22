"""
Shared types and bill-matching logic for all finance providers.

Every finance provider returns List[BankTransaction] from get_recent_transactions().
match_bills_to_transactions() is provider-agnostic and lives here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Any

log = logging.getLogger("postmule.finance")


@dataclass
class BankTransaction:
    transaction_id: str
    date: str        # YYYY-MM-DD
    amount: float    # negative = expense/outflow (normalized across all providers)
    payee: str
    account: str
    category: str = ""
    memo: str = ""


@dataclass
class BillMatchResult:
    bill_id: str
    transaction_id: str
    amount: float
    date: str
    confidence: str  # "exact" | "amount_only"
    approved: bool = False


def match_bills_to_transactions(
    bills: list[dict[str, Any]],
    transactions: list[BankTransaction],
    amount_tolerance: float = 0.0,
) -> list[BillMatchResult]:
    """
    Match pending bills to bank transactions by exact amount + date proximity.

    Matching rules (per design spec):
      - Exact amount match required (or within tolerance)
      - Transaction date within 7 days of bill due date
      - Payee name NOT used (finance apps overwrite with wrong names)

    Args:
        bills:             List of pending bill dicts from bills_YYYY.json.
        transactions:      List of BankTransaction from any provider.
        amount_tolerance:  Maximum dollar difference (0 = exact match).

    Returns:
        List of BillMatchResult candidates for human approval.
    """
    matches = []
    pending_bills = [b for b in bills if b.get("status") == "pending"]

    for bill in pending_bills:
        bill_amount = bill.get("amount_due")
        bill_due = bill.get("due_date", "")
        if bill_amount is None or not bill_due:
            continue

        for txn in transactions:
            txn_amount = abs(txn.amount)
            if abs(txn_amount - bill_amount) > amount_tolerance:
                continue

            try:
                due = date_type.fromisoformat(bill_due)
                txn_date = date_type.fromisoformat(txn.date)
                if abs((txn_date - due).days) > 7:
                    continue
            except ValueError:
                continue

            matches.append(BillMatchResult(
                bill_id=bill["id"],
                transaction_id=txn.transaction_id,
                amount=bill_amount,
                date=txn.date,
                confidence="exact" if abs(txn_amount - bill_amount) == 0 else "amount_only",
            ))
            break  # one match per bill

    log.info(f"Bill matching: {len(matches)} matches found from {len(pending_bills)} pending bills")
    return matches
