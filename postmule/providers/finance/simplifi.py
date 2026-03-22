"""
Simplifi finance provider — scrapes bank transactions using Playwright.

Architecture reference: finance-dl (MIT) by Jeremy Maitin-Shepard.
See ATTRIBUTION.md.

NOTE: Simplifi has no public API. This provider uses browser automation.
YNAB is the preferred alternative if you use it (real REST API, no scraping).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

# Shared types live in base; re-exported here for backward compatibility.
from postmule.providers.finance.base import (  # noqa: F401
    BankTransaction,
    BillMatchResult,
    match_bills_to_transactions,
)

log = logging.getLogger("postmule.finance.simplifi")


class SimplifiProvider:
    """
    Simplifi by Quicken — browser-based transaction scraping.

    Args:
        username: Simplifi login email.
        password: Simplifi login password.
    """

    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password
        self._browser = None
        self._page = None

    def get_recent_transactions(self, days: int = 30) -> list[BankTransaction]:
        """
        Log in to Simplifi and scrape transactions from the last N days.

        Returns:
            List of BankTransaction objects.
        """
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import]
        except ImportError:
            raise RuntimeError(
                "playwright is not installed.\n"
                "Run: pip install playwright && playwright install chromium"
            )

        transactions = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            try:
                transactions = self._scrape_transactions(page, days)
            finally:
                browser.close()

        log.info(f"Scraped {len(transactions)} transactions from Simplifi")
        return transactions

    def _scrape_transactions(self, page, days: int) -> list[BankTransaction]:
        """Log in and scrape transactions. Returns list of BankTransaction."""
        log.debug("Logging in to Simplifi...")
        page.goto("https://app.simplifimoney.com")
        page.wait_for_load_state("networkidle")

        # Login form
        page.fill('input[type="email"]', self.username)
        page.fill('input[type="password"]', self.password)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        # Navigate to transactions
        page.goto("https://app.simplifimoney.com/transactions")
        page.wait_for_load_state("networkidle")

        # Scrape transaction rows
        # NOTE: Simplifi's DOM structure changes; this is a best-effort scraper.
        transactions = []
        rows = page.query_selector_all("[data-testid='transaction-row']")
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        for row in rows:
            try:
                txn = self._parse_transaction_row(row)
                if txn and txn.date >= cutoff:
                    transactions.append(txn)
            except Exception as exc:
                log.debug(f"Failed to parse transaction row: {exc}")

        return transactions

    def _parse_transaction_row(self, row) -> BankTransaction | None:
        """Parse a single Simplifi transaction row element."""
        try:
            date_el = row.query_selector("[data-testid='transaction-date']")
            amount_el = row.query_selector("[data-testid='transaction-amount']")
            payee_el = row.query_selector("[data-testid='transaction-payee']")

            if not all([date_el, amount_el, payee_el]):
                return None

            date_str = date_el.inner_text().strip()
            amount_str = amount_el.inner_text().strip().replace("$", "").replace(",", "")
            payee = payee_el.inner_text().strip()

            # Parse date (Simplifi shows "Mar 20, 2025" format)
            from datetime import datetime
            try:
                parsed_date = datetime.strptime(date_str, "%b %d, %Y").date().isoformat()
            except ValueError:
                parsed_date = date_str

            amount = float(amount_str)

            return BankTransaction(
                transaction_id=f"{parsed_date}_{payee[:20]}_{amount}",
                date=parsed_date,
                amount=amount,
                payee=payee,
                account="",
            )
        except Exception:
            return None

    def update_transaction_name(self, transaction_id: str, new_name: str) -> bool:
        """
        Update a transaction's payee name in Simplifi.
        Called after approving a bill match to correct the payee name.

        Returns:
            True if successful.
        """
        log.warning(
            f"Simplifi update_transaction_name is not implemented — "
            f"transaction {transaction_id} payee was NOT renamed to '{new_name}'. "
            "Use YNAB for automatic payee correction."
        )
        return False
