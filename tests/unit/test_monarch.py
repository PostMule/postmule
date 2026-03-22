"""Unit tests for postmule.providers.finance.monarch."""

from unittest.mock import MagicMock, patch

import pytest

from postmule.providers.finance.monarch import MonarchProvider
from postmule.providers.finance.base import BankTransaction


class TestMonarchProviderInit:
    def test_stores_credentials(self):
        provider = MonarchProvider(username="user@example.com", password="pass")
        assert provider.username == "user@example.com"
        assert provider.password == "pass"


class TestMonarchGetRecentTransactions:
    def test_raises_when_playwright_not_available(self):
        provider = MonarchProvider(username="u", password="p")
        with patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None}):
            with pytest.raises(RuntimeError, match="playwright"):
                provider.get_recent_transactions()

    def test_returns_bank_transactions(self):
        provider = MonarchProvider(username="u", password="p")

        mock_txn = MagicMock(spec=BankTransaction)
        mock_txn.date = "2099-01-01"

        # sync_playwright is imported inside get_recent_transactions — mock via sys.modules.
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser.new_page.return_value = mock_page
        mock_p = MagicMock()
        mock_p.chromium.launch.return_value = mock_browser

        mock_pw_ctx = MagicMock()
        mock_pw_ctx.__enter__ = MagicMock(return_value=mock_p)
        mock_pw_ctx.__exit__ = MagicMock(return_value=False)

        mock_sync_playwright = MagicMock(return_value=mock_pw_ctx)
        mock_pw_module = MagicMock()
        mock_pw_module.sync_playwright = mock_sync_playwright

        with patch.object(provider, "_scrape_transactions", return_value=[mock_txn]) as mock_scrape:
            with patch.dict("sys.modules", {
                "playwright": MagicMock(),
                "playwright.sync_api": mock_pw_module,
            }):
                result = provider.get_recent_transactions(days=30)

        mock_scrape.assert_called_once()
        assert result == [mock_txn]

    def test_scrape_returns_empty_when_no_rows(self):
        provider = MonarchProvider(username="u", password="p")
        page = MagicMock()
        page.query_selector_all.return_value = []

        result = provider._scrape_transactions(page, days=30)
        assert result == []

    def test_scrape_skips_rows_outside_cutoff(self):
        provider = MonarchProvider(username="u", password="p")
        page = MagicMock()

        # Row that will parse to a date before the cutoff
        old_txn = BankTransaction(
            transaction_id="old_0.0",
            date="2000-01-01",
            amount=-10.0,
            payee="Old",
            account="",
        )
        new_txn = BankTransaction(
            transaction_id="new_10.0",
            date="2099-01-01",
            amount=-10.0,
            payee="New",
            account="",
        )

        with patch.object(
            provider,
            "_parse_transaction_row",
            side_effect=[old_txn, new_txn],
        ):
            page.query_selector_all.return_value = [MagicMock(), MagicMock()]
            result = provider._scrape_transactions(page, days=30)

        assert len(result) == 1
        assert result[0].payee == "New"

    def test_scrape_handles_parse_exception(self):
        """Rows that raise during parse are skipped, not propagated."""
        provider = MonarchProvider(username="u", password="p")
        page = MagicMock()
        page.query_selector_all.return_value = [MagicMock()]

        with patch.object(provider, "_parse_transaction_row", side_effect=Exception("bad row")):
            result = provider._scrape_transactions(page, days=30)

        assert result == []


class TestMonarchParseTransactionRow:
    def _make_row(self, date_text: str, amount_text: str, payee_text: str) -> MagicMock:
        row = MagicMock()

        date_el = MagicMock()
        date_el.inner_text.return_value = date_text
        amount_el = MagicMock()
        amount_el.inner_text.return_value = amount_text
        merchant_el = MagicMock()
        merchant_el.inner_text.return_value = payee_text

        # query_selector returns elements in order: date, amount, merchant
        row.query_selector.side_effect = [date_el, None, amount_el, None, merchant_el, None]
        return row

    def test_parses_slash_date_format(self):
        provider = MonarchProvider(username="u", password="p")
        row = MagicMock()

        date_el = MagicMock()
        date_el.inner_text.return_value = "03/15/2025"
        amount_el = MagicMock()
        amount_el.inner_text.return_value = "$55.99"
        merchant_el = MagicMock()
        merchant_el.inner_text.return_value = "Netflix"

        def query_selector(selector):
            if "date" in selector:
                return date_el
            if "amount" in selector:
                return amount_el
            if "merchant" in selector or "payee" in selector:
                return merchant_el
            return None

        row.query_selector.side_effect = query_selector
        txn = provider._parse_transaction_row(row)
        assert txn is not None
        assert txn.date == "2025-03-15"
        assert txn.payee == "Netflix"
        assert txn.amount == pytest.approx(-55.99)

    def test_parses_named_month_date_format(self):
        provider = MonarchProvider(username="u", password="p")
        row = MagicMock()

        date_el = MagicMock()
        date_el.inner_text.return_value = "Mar 15, 2025"
        amount_el = MagicMock()
        amount_el.inner_text.return_value = "55.99"
        merchant_el = MagicMock()
        merchant_el.inner_text.return_value = "Spotify"

        def query_selector(selector):
            if "date" in selector:
                return date_el
            if "amount" in selector:
                return amount_el
            if "merchant" in selector or "payee" in selector:
                return merchant_el
            return None

        row.query_selector.side_effect = query_selector
        txn = provider._parse_transaction_row(row)
        assert txn is not None
        assert txn.date == "2025-03-15"
        assert txn.payee == "Spotify"

    def test_returns_none_when_elements_missing(self):
        provider = MonarchProvider(username="u", password="p")
        row = MagicMock()
        row.query_selector.return_value = None
        txn = provider._parse_transaction_row(row)
        assert txn is None

    def test_amount_is_always_negative(self):
        """Monarch expenses should be normalized to negative."""
        provider = MonarchProvider(username="u", password="p")
        row = MagicMock()

        date_el = MagicMock()
        date_el.inner_text.return_value = "2025-03-01"
        amount_el = MagicMock()
        amount_el.inner_text.return_value = "+100.00"  # positive sign stripped
        merchant_el = MagicMock()
        merchant_el.inner_text.return_value = "Store"

        def query_selector(selector):
            if "date" in selector:
                return date_el
            if "amount" in selector:
                return amount_el
            if "merchant" in selector or "payee" in selector:
                return merchant_el
            return None

        row.query_selector.side_effect = query_selector
        txn = provider._parse_transaction_row(row)
        assert txn is not None
        assert txn.amount < 0

    def test_returns_none_on_parse_error(self):
        provider = MonarchProvider(username="u", password="p")
        row = MagicMock()
        row.query_selector.side_effect = RuntimeError("DOM exploded")
        txn = provider._parse_transaction_row(row)
        assert txn is None


class TestMonarchUpdateTransactionName:
    def test_returns_false(self):
        """Monarch has no rename API — always returns False."""
        provider = MonarchProvider(username="u", password="p")
        result = provider.update_transaction_name("txn-1", "New Name")
        assert result is False

    def test_returns_false_for_any_input(self):
        provider = MonarchProvider(username="u", password="p")
        assert provider.update_transaction_name("", "") is False
        assert provider.update_transaction_name("x", "y") is False
