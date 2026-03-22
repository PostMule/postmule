"""
Simplifi finance provider — scrapes bank transactions using Playwright.

Architecture reference: finance-dl (MIT) by Jeremy Maitin-Shepard.
See ATTRIBUTION.md.

NOTE: Simplifi has no public API. This provider uses browser automation.
YNAB is the preferred alternative if you use it (real REST API, no scraping).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

log = logging.getLogger("postmule.finance.simplifi")


@dataclass
class BankTransaction:
    transaction_id: str
    date: str            # YYYY-MM-DD
    amount: float        # negative = expense
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
    confidence: str      # "exact" | "amount_only"
    approved: bool = False


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
        log.info(f"Would update Simplifi transaction {transaction_id} -> '{new_name}' (not yet implemented)")
        return False


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
      - Payee name NOT used (Simplifi overwrites with wrong names)

    Args:
        bills:             List of pending bill dicts from bills_YYYY.json.
        transactions:      List of BankTransaction from Simplifi.
        amount_tolerance:  Maximum cent difference (0 = exact match).

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
            # Amount must match (debit = negative amount in Simplifi)
            txn_amount = abs(txn.amount)
            if abs(txn_amount - bill_amount) > amount_tolerance:
                continue

            # Date must be within 7 days of due date
            try:
                from datetime import date as date_type
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
