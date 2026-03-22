"""
Monarch Money finance provider — browser automation via Playwright.

NOTE: Monarch Money has no public API. This provider uses browser automation.
It is labeled EXPERIMENTAL — DOM changes may break it without notice.
YNAB or Plaid are preferred alternatives (real REST APIs, no scraping).

Architecture reference: finance-dl (MIT) by Jeremy Maitin-Shepard.
See ATTRIBUTION.md.

Setup:
  credentials.yaml:
    monarch:
      username: "your@email.com"
      password: "your-password"

  config.yaml:
    finance:
      providers:
        - type: monarch
          enabled: true
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from postmule.providers.finance.base import BankTransaction, BillMatchResult

log = logging.getLogger("postmule.finance.monarch")


class MonarchProvider:
    """
    Monarch Money — browser-based transaction scraping (experimental).

    Args:
        username: Monarch Money login email.
        password: Monarch Money login password.
    """

    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password

    def get_recent_transactions(self, days: int = 30) -> list[BankTransaction]:
        """
        Log in to Monarch Money and scrape transactions from the last N days.

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

        log.info(f"Scraped {len(transactions)} transactions from Monarch Money")
        return transactions

    def _scrape_transactions(self, page, days: int) -> list[BankTransaction]:
        """Log in to Monarch and scrape the transactions page."""
        log.debug("Logging in to Monarch Money...")
        page.goto("https://app.monarchmoney.com/login")
        page.wait_for_load_state("networkidle")

        page.fill('input[type="email"]', self.username)
        page.fill('input[type="password"]', self.password)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        page.goto("https://app.monarchmoney.com/transactions")
        page.wait_for_load_state("networkidle")

        cutoff = (date.today() - timedelta(days=days)).isoformat()
        transactions = []

        # NOTE: Monarch's DOM structure changes; these selectors are best-effort.
        rows = page.query_selector_all(
            "[data-testid='transaction-row'], [class*='TransactionRow'], tr[class*='transaction']"
        )

        for row in rows:
            try:
                txn = self._parse_transaction_row(row)
                if txn and txn.date >= cutoff:
                    transactions.append(txn)
            except Exception as exc:
                log.debug(f"Failed to parse Monarch transaction row: {exc}")

        return transactions

    def _parse_transaction_row(self, row) -> BankTransaction | None:
        """Parse a single Monarch transaction row element."""
        try:
            # Attempt multiple selector patterns — Monarch's DOM varies across releases.
            date_el = (
                row.query_selector("[data-testid='transaction-date']")
                or row.query_selector("[class*='date']")
            )
            amount_el = (
                row.query_selector("[data-testid='transaction-amount']")
                or row.query_selector("[class*='amount']")
            )
            merchant_el = (
                row.query_selector("[data-testid='transaction-merchant']")
                or row.query_selector("[class*='merchant']")
                or row.query_selector("[class*='payee']")
            )

            if not all([date_el, amount_el, merchant_el]):
                return None

            date_str = date_el.inner_text().strip()
            amount_str = (
                amount_el.inner_text().strip()
                .replace("$", "").replace(",", "").replace("+", "")
            )
            payee = merchant_el.inner_text().strip()

            # Monarch shows dates in multiple formats depending on UI version.
            parsed_date = None
            for fmt in ("%m/%d/%Y", "%b %d, %Y", "%Y-%m-%d"):
                try:
                    parsed_date = datetime.strptime(date_str, fmt).date().isoformat()
                    break
                except ValueError:
                    continue
            if parsed_date is None:
                parsed_date = date_str  # fall back to raw string

            amount = float(amount_str)

            return BankTransaction(
                transaction_id=f"{parsed_date}_{payee[:20]}_{amount}",
                date=parsed_date,
                amount=-abs(amount),  # normalize: expenses are negative
                payee=payee,
                account="",
            )
        except Exception:
            return None

    def update_transaction_name(self, transaction_id: str, new_name: str) -> bool:
        """
        Monarch Money does not expose a transaction rename API.
        The payee name correction is logged but not written back to Monarch.

        Returns:
            False (not supported).
        """
        log.info(
            f"Monarch: transaction rename not supported via API "
            f"(would rename {transaction_id} to '{new_name}')"
        )
        return False
