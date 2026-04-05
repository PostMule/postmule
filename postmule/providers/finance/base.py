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
    confidence: str  # "exact" | "fuzzy_amount" | "fuzzy_date" | "fuzzy_both"
    approved: bool = False


def match_bills_to_transactions(
    bills: list[dict[str, Any]],
    transactions: list[BankTransaction],
    amount_tolerance: float = 0.0,
    date_tolerance_days: int = 7,
) -> list[BillMatchResult]:
    """
    Match pending bills to bank transactions by amount + date proximity.

    Matching rules (per design spec):
      - Amount must match within amount_tolerance dollars (0 = exact)
      - Transaction date within date_tolerance_days of bill due date
      - Payee name NOT used (finance apps overwrite with wrong names)

    Confidence values:
      "exact"        — amount and date both exact
      "fuzzy_amount" — date exact, amount within tolerance
      "fuzzy_date"   — amount exact, date within tolerance
      "fuzzy_both"   — both amount and date within tolerance (not exact)

    Args:
        bills:              List of pending bill dicts from bills_YYYY.json.
        transactions:       List of BankTransaction from any provider.
        amount_tolerance:   Maximum dollar difference (0 = exact match).
        date_tolerance_days: Maximum days between transaction date and due date.

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
            amount_diff = abs(txn_amount - bill_amount)
            if amount_diff > amount_tolerance:
                continue

            try:
                due = date_type.fromisoformat(bill_due)
                txn_date = date_type.fromisoformat(txn.date)
                date_diff = abs((txn_date - due).days)
                if date_diff > date_tolerance_days:
                    continue
            except ValueError:
                continue

            amount_exact = amount_diff == 0
            date_exact = date_diff == 0
            if amount_exact and date_exact:
                confidence = "exact"
            elif amount_exact:
                confidence = "fuzzy_date"
            elif date_exact:
                confidence = "fuzzy_amount"
            else:
                confidence = "fuzzy_both"

            matches.append(BillMatchResult(
                bill_id=bill["id"],
                transaction_id=txn.transaction_id,
                amount=bill_amount,
                date=txn.date,
                confidence=confidence,
            ))
            break  # one match per bill

    log.info(f"Bill matching: {len(matches)} matches found from {len(pending_bills)} pending bills")
    return matches
