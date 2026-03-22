"""Unit tests for postmule.providers.finance.ynab."""

from unittest.mock import MagicMock, patch

import pytest

from postmule.providers.finance.ynab import YnabProvider
from postmule.providers.finance.base import BankTransaction


class TestYnabProviderInit:
    def test_stores_credentials(self):
        provider = YnabProvider(access_token="tok", budget_id="budget-123")
        assert provider.access_token == "tok"
        assert provider.budget_id == "budget-123"

    def test_default_budget_id(self):
        provider = YnabProvider(access_token="tok")
        assert provider.budget_id == "last-used"

    def test_headers_include_bearer_token(self):
        provider = YnabProvider(access_token="my-token")
        assert provider._headers() == {"Authorization": "Bearer my-token"}


class TestYnabGetRecentTransactions:
    def _make_ynab_response(self, transactions: list) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"data": {"transactions": transactions}}
        return resp

    def test_returns_bank_transactions(self):
        provider = YnabProvider(access_token="tok")
        ynab_txns = [
            {
                "id": "txn-1",
                "date": "2025-03-01",
                "amount": -94000,  # -$94.00 outflow
                "payee_name": "AT&T",
                "account_name": "Checking",
                "memo": "Monthly bill",
            }
        ]
        with patch("requests.get", return_value=self._make_ynab_response(ynab_txns)):
            txns = provider.get_recent_transactions(days=30)

        assert len(txns) == 1
        assert isinstance(txns[0], BankTransaction)
        assert txns[0].transaction_id == "txn-1"
        assert txns[0].date == "2025-03-01"
        assert txns[0].amount == pytest.approx(-94.0)
        assert txns[0].payee == "AT&T"
        assert txns[0].account == "Checking"
        assert txns[0].memo == "Monthly bill"

    def test_converts_milliunits_to_dollars(self):
        provider = YnabProvider(access_token="tok")
        ynab_txns = [
            {"id": "t1", "date": "2025-01-01", "amount": -12050, "payee_name": "X",
             "account_name": "A", "memo": ""},
        ]
        with patch("requests.get", return_value=self._make_ynab_response(ynab_txns)):
            txns = provider.get_recent_transactions()
        assert txns[0].amount == pytest.approx(-12.05)

    def test_handles_null_payee(self):
        provider = YnabProvider(access_token="tok")
        ynab_txns = [
            {"id": "t1", "date": "2025-01-01", "amount": -1000,
             "payee_name": None, "account_name": None, "memo": None},
        ]
        with patch("requests.get", return_value=self._make_ynab_response(ynab_txns)):
            txns = provider.get_recent_transactions()
        assert txns[0].payee == ""
        assert txns[0].account == ""
        assert txns[0].memo == ""

    def test_empty_response(self):
        provider = YnabProvider(access_token="tok")
        with patch("requests.get", return_value=self._make_ynab_response([])):
            txns = provider.get_recent_transactions()
        assert txns == []

    def test_raises_when_requests_not_available(self):
        provider = YnabProvider(access_token="tok")
        with patch.dict("sys.modules", {"requests": None}):
            with pytest.raises(Exception):
                provider.get_recent_transactions()


class TestYnabUpdateTransactionName:
    def test_returns_true_on_success(self):
        provider = YnabProvider(access_token="tok")
        resp = MagicMock()
        resp.ok = True
        with patch("requests.patch", return_value=resp):
            result = provider.update_transaction_name("txn-1", "AT&T")
        assert result is True

    def test_returns_false_on_failure(self):
        provider = YnabProvider(access_token="tok")
        resp = MagicMock()
        resp.ok = False
        resp.status_code = 404
        resp.text = "Not found"
        with patch("requests.patch", return_value=resp):
            result = provider.update_transaction_name("txn-1", "AT&T")
        assert result is False

    def test_returns_false_when_requests_not_available(self):
        provider = YnabProvider(access_token="tok")
        with patch.dict("sys.modules", {"requests": None}):
            result = provider.update_transaction_name("txn-1", "name")
        assert result is False
