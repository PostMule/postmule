"""
YNAB (You Need A Budget) finance provider — real REST API v1.

API docs: https://api.ynab.com/v1
Auth: Personal Access Token — create one at app.ynab.com → Account Settings → Developer Settings.
Free to use; no rate limit concerns for typical PostMule usage.

Setup:
  credentials.yaml:
    ynab:
      access_token: "your-personal-access-token"
      budget_id: "last-used"   # or a specific budget UUID from the YNAB UI

  config.yaml:
    finance:
      providers:
        - type: ynab
          enabled: true
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from postmule.providers.finance.base import BankTransaction, BillMatchResult

log = logging.getLogger("postmule.finance.ynab")

_BASE_URL = "https://api.ynab.com/v1"


class YnabProvider:
    """
    Fetches bank transactions from YNAB via the official REST API.

    YNAB amounts are in milliunits (1000 milliunits = $1.00).
    Outflows (expenses) are negative; inflows are positive.
    This provider normalizes to the PostMule convention: negative = expense.

    Args:
        access_token: YNAB Personal Access Token.
        budget_id:    YNAB budget UUID, or "last-used" (default).
    """

    def __init__(self, access_token: str, budget_id: str = "last-used") -> None:
        self.access_token = access_token
        self.budget_id = budget_id

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    def get_recent_transactions(self, days: int = 30) -> list[BankTransaction]:
        """
        Fetch transactions from YNAB for the last N days.

        Returns:
            List of BankTransaction objects (amount negative = expense).
        """
        try:
            import requests
        except ImportError:
            raise RuntimeError(
                "requests is not installed.\nRun: pip install requests"
            )

        since_date = (date.today() - timedelta(days=days)).isoformat()
        url = f"{_BASE_URL}/budgets/{self.budget_id}/transactions"
        resp = requests.get(
            url,
            headers=self._headers(),
            params={"since_date": since_date},
            timeout=30,
        )
        resp.raise_for_status()

        transactions = []
        for t in resp.json()["data"]["transactions"]:
            # YNAB milliunits: -94000 = $94.00 outflow. Already negative for expenses.
            amount_dollars = t["amount"] / 1000.0
            transactions.append(BankTransaction(
                transaction_id=t["id"],
                date=t["date"],
                amount=amount_dollars,
                payee=t.get("payee_name") or "",
                account=t.get("account_name") or "",
                memo=t.get("memo") or "",
            ))

        log.info(f"Fetched {len(transactions)} transactions from YNAB")
        return transactions

    def update_transaction_name(self, transaction_id: str, new_name: str) -> bool:
        """
        Update a transaction's payee name in YNAB.
        Called after approving a bill match to correct the merchant name.

        Returns:
            True if successful.
        """
        try:
            import requests
        except ImportError:
            return False

        url = f"{_BASE_URL}/budgets/{self.budget_id}/transactions/{transaction_id}"
        body = {"transaction": {"payee_name": new_name}}
        resp = requests.patch(url, headers=self._headers(), json=body, timeout=30)
        if resp.ok:
            log.info(f"Updated YNAB transaction {transaction_id} payee to '{new_name}'")
            return True
        log.warning(
            f"Failed to update YNAB transaction {transaction_id}: {resp.status_code} {resp.text[:200]}"
        )
        return False
