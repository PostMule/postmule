"""Unit tests for postmule.providers.finance.simplifi."""

from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from postmule.providers.finance.simplifi import (
    BankTransaction,
    BillMatchResult,
    SimplifiProvider,
    match_bills_to_transactions,
)


class TestSimplifiProviderInit:
    def test_stores_credentials(self):
        provider = SimplifiProvider("user@example.com", "pass")
        assert provider.username == "user@example.com"
        assert provider.password == "pass"


class TestSimplifiGetRecentTransactions:
    def test_raises_when_playwright_not_available(self):
        provider = SimplifiProvider("user", "pass")
        with pytest.raises(Exception):
            # Will raise either ImportError (playwright not installed) or RuntimeError
            provider.get_recent_transactions(days=1)


class TestSimplifiUpdateTransactionName:
    def test_returns_false(self):
        provider = SimplifiProvider("user", "pass")
        result = provider.update_transaction_name("txn-id", "New Name")
        assert result is False


class TestParseTransactionRow:
    def _make_row(self, date_str="Jan 15, 2025", amount_str="$94.00", payee="AT&T"):
        row = MagicMock()
        date_el = MagicMock()
        date_el.inner_text.return_value = date_str
        amount_el = MagicMock()
        amount_el.inner_text.return_value = amount_str
        payee_el = MagicMock()
        payee_el.inner_text.return_value = payee
        row.query_selector.side_effect = lambda sel: {
            "[data-testid='transaction-date']": date_el,
            "[data-testid='transaction-amount']": amount_el,
            "[data-testid='transaction-payee']": payee_el,
        }[sel]
        return row

    def test_parses_valid_row(self):
        provider = SimplifiProvider("u", "p")
        row = self._make_row()
        txn = provider._parse_transaction_row(row)
        assert txn is not None
        assert txn.date == "2025-01-15"
        assert txn.amount == 94.0
        assert txn.payee == "AT&T"

    def test_returns_none_when_elements_missing(self):
        provider = SimplifiProvider("u", "p")
        row = MagicMock()
        row.query_selector.return_value = None
        result = provider._parse_transaction_row(row)
        assert result is None

    def test_handles_invalid_amount(self):
        provider = SimplifiProvider("u", "p")
        row = self._make_row(amount_str="invalid")
        result = provider._parse_transaction_row(row)
        assert result is None

    def test_handles_unknown_date_format(self):
        provider = SimplifiProvider("u", "p")
        row = self._make_row(date_str="2025-01-15")  # Not "Jan 15, 2025" format
        txn = provider._parse_transaction_row(row)
        # Falls back to raw date string
        assert txn is not None
        assert txn.date == "2025-01-15"


class TestMatchBillsToTransactions:
    def _make_bill(self, amount=94.0, due_date=None, status="pending", bill_id="bill-1"):
        today = date.today()
        return {
            "id": bill_id,
            "sender": "ATT",
            "amount_due": amount,
            "due_date": due_date or today.isoformat(),
            "status": status,
        }

    def _make_txn(self, amount=-94.0, txn_date=None, payee="AT&T"):
        today = date.today()
        d = txn_date or today.isoformat()
        return BankTransaction(
            transaction_id=f"{d}_{payee}_{amount}",
            date=d,
            amount=amount,
            payee=payee,
            account="checking",
        )

    def test_exact_match_found(self):
        bill = self._make_bill(amount=94.0)
        txn = self._make_txn(amount=-94.0)
        matches = match_bills_to_transactions([bill], [txn])
        assert len(matches) == 1
        assert matches[0].bill_id == "bill-1"
        assert matches[0].confidence == "exact"

    def test_no_match_wrong_amount(self):
        bill = self._make_bill(amount=94.0)
        txn = self._make_txn(amount=-50.0)
        matches = match_bills_to_transactions([bill], [txn])
        assert matches == []

    def test_no_match_too_far_in_date(self):
        bill = self._make_bill(due_date="2025-01-01")
        txn = self._make_txn(txn_date="2025-01-15")  # 14 days away, > 7
        matches = match_bills_to_transactions([bill], [txn])
        assert matches == []

    def test_skips_non_pending_bills(self):
        bill = self._make_bill(status="paid")
        txn = self._make_txn()
        matches = match_bills_to_transactions([bill], [txn])
        assert matches == []

    def test_skips_bills_without_amount(self):
        bill = {"id": "x", "status": "pending", "due_date": "2025-01-01", "amount_due": None}
        txn = self._make_txn()
        matches = match_bills_to_transactions([bill], [txn])
        assert matches == []

    def test_skips_bills_without_due_date(self):
        bill = {"id": "x", "status": "pending", "amount_due": 94.0}
        txn = self._make_txn()
        matches = match_bills_to_transactions([bill], [txn])
        assert matches == []

    def test_one_match_per_bill(self):
        bill = self._make_bill()
        txn1 = self._make_txn(payee="ATT1")
        txn2 = self._make_txn(payee="ATT2")
        matches = match_bills_to_transactions([bill], [txn1, txn2])
        assert len(matches) == 1

    def test_tolerance_allows_close_amount(self):
        bill = self._make_bill(amount=94.00)
        txn = self._make_txn(amount=-94.01)
        matches = match_bills_to_transactions([bill], [txn], amount_tolerance=0.05)
        assert len(matches) == 1
        assert matches[0].confidence == "amount_only"

    def test_invalid_date_skipped(self):
        bill = {"id": "x", "status": "pending", "amount_due": 10.0, "due_date": "not-a-date"}
        txn = self._make_txn(amount=-10.0)
        matches = match_bills_to_transactions([bill], [txn])
        assert matches == []
