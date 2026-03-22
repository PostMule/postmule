"""Unit tests for postmule.providers.finance.plaid."""

from unittest.mock import MagicMock, patch

import pytest

from postmule.providers.finance.plaid import PlaidProvider, _ENVIRONMENTS
from postmule.providers.finance.base import BankTransaction


class TestPlaidProviderInit:
    def test_stores_credentials(self):
        provider = PlaidProvider(
            client_id="cid", secret="sec", access_token="access-dev-xxx"
        )
        assert provider.client_id == "cid"
        assert provider.secret == "sec"
        assert provider.access_token == "access-dev-xxx"

    def test_default_environment_is_development(self):
        provider = PlaidProvider(client_id="cid", secret="sec", access_token="tok")
        assert provider.base_url == _ENVIRONMENTS["development"]

    def test_sandbox_environment(self):
        provider = PlaidProvider(
            client_id="cid", secret="sec", access_token="tok", environment="sandbox"
        )
        assert provider.base_url == _ENVIRONMENTS["sandbox"]

    def test_production_environment(self):
        provider = PlaidProvider(
            client_id="cid", secret="sec", access_token="tok", environment="production"
        )
        assert provider.base_url == _ENVIRONMENTS["production"]

    def test_unknown_environment_falls_back_to_development(self):
        provider = PlaidProvider(
            client_id="cid", secret="sec", access_token="tok", environment="unknown"
        )
        assert provider.base_url == _ENVIRONMENTS["development"]

    def test_auth_dict(self):
        provider = PlaidProvider(client_id="cid", secret="sec", access_token="tok")
        assert provider._auth() == {"client_id": "cid", "secret": "sec"}


class TestPlaidGetRecentTransactions:
    def _make_plaid_response(self, transactions: list) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"transactions": transactions}
        return resp

    def test_returns_bank_transactions(self):
        provider = PlaidProvider(client_id="cid", secret="sec", access_token="tok")
        plaid_txns = [
            {
                "transaction_id": "txn-abc",
                "date": "2025-03-15",
                "amount": 55.99,  # Plaid positive = debit (spending)
                "name": "Netflix",
                "account_id": "acct-1",
                "original_description": "NETFLIX.COM",
            }
        ]
        with patch("requests.post", return_value=self._make_plaid_response(plaid_txns)):
            txns = provider.get_recent_transactions(days=30)

        assert len(txns) == 1
        assert isinstance(txns[0], BankTransaction)
        assert txns[0].transaction_id == "txn-abc"
        assert txns[0].date == "2025-03-15"
        assert txns[0].amount == pytest.approx(-55.99)  # negated
        assert txns[0].payee == "Netflix"
        assert txns[0].account == "acct-1"
        assert txns[0].memo == "NETFLIX.COM"

    def test_negates_amount(self):
        """Plaid positive amounts (debits) become negative (PostMule expenses)."""
        provider = PlaidProvider(client_id="cid", secret="sec", access_token="tok")
        plaid_txns = [
            {"transaction_id": "t1", "date": "2025-01-01", "amount": 120.00,
             "name": "Store", "account_id": "acct", "original_description": None},
        ]
        with patch("requests.post", return_value=self._make_plaid_response(plaid_txns)):
            txns = provider.get_recent_transactions()
        assert txns[0].amount == pytest.approx(-120.00)

    def test_handles_null_name_and_description(self):
        provider = PlaidProvider(client_id="cid", secret="sec", access_token="tok")
        plaid_txns = [
            {"transaction_id": "t1", "date": "2025-01-01", "amount": 10.0,
             "name": None, "account_id": None, "original_description": None},
        ]
        with patch("requests.post", return_value=self._make_plaid_response(plaid_txns)):
            txns = provider.get_recent_transactions()
        assert txns[0].payee == ""
        assert txns[0].account == ""
        assert txns[0].memo == ""

    def test_empty_response(self):
        provider = PlaidProvider(client_id="cid", secret="sec", access_token="tok")
        with patch("requests.post", return_value=self._make_plaid_response([])):
            txns = provider.get_recent_transactions()
        assert txns == []

    def test_posts_to_correct_url(self):
        provider = PlaidProvider(
            client_id="cid", secret="sec", access_token="tok", environment="sandbox"
        )
        mock_resp = self._make_plaid_response([])
        with patch("requests.post", return_value=mock_resp) as mock_post:
            provider.get_recent_transactions()
        url_called = mock_post.call_args[0][0]
        assert "sandbox.plaid.com" in url_called
        assert url_called.endswith("/transactions/get")

    def test_request_body_includes_auth_and_token(self):
        provider = PlaidProvider(client_id="cid", secret="sec", access_token="my-access")
        mock_resp = self._make_plaid_response([])
        with patch("requests.post", return_value=mock_resp) as mock_post:
            provider.get_recent_transactions()
        body = mock_post.call_args[1]["json"]
        assert body["client_id"] == "cid"
        assert body["secret"] == "sec"
        assert body["access_token"] == "my-access"

    def test_raises_when_requests_not_available(self):
        provider = PlaidProvider(client_id="cid", secret="sec", access_token="tok")
        with patch.dict("sys.modules", {"requests": None}):
            with pytest.raises(Exception):
                provider.get_recent_transactions()


class TestPlaidUpdateTransactionName:
    def test_returns_false(self):
        """Plaid has no rename endpoint — always returns False."""
        provider = PlaidProvider(client_id="cid", secret="sec", access_token="tok")
        result = provider.update_transaction_name("txn-1", "New Name")
        assert result is False

    def test_returns_false_for_any_input(self):
        provider = PlaidProvider(client_id="cid", secret="sec", access_token="tok")
        assert provider.update_transaction_name("", "") is False
        assert provider.update_transaction_name("x", "y") is False
