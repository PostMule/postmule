"""
Plaid finance provider — real REST API.

API docs: https://plaid.com/docs/api/
Auth: client_id + secret (from Plaid Dashboard) + access_token (per linked institution).

Development tier: up to 100 live Items free.
Sandbox: unlimited test data, use environment: sandbox.

Getting an access_token requires running the Plaid Link flow (browser OAuth) once per
institution. The resulting access_token is long-lived and stored in credentials.yaml.

Setup:
  1. Create a Plaid account at dashboard.plaid.com
  2. Create an application — copy client_id and secret (development or sandbox keys)
  3. Complete the Link flow for each bank account you want to track
     (see: https://plaid.com/docs/link/)
  4. Store the resulting access_token in credentials.yaml

  credentials.yaml:
    plaid:
      client_id: "your-client-id"
      secret: "your-development-secret"
      access_token: "access-development-xxxx"  # one per linked institution

  config.yaml:
    finance:
      providers:
        - type: plaid
          enabled: true
          environment: development  # sandbox | development | production

Note: PostMule currently supports one Plaid access_token (one institution).
For multiple institutions, list multiple finance provider entries.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from postmule.providers.finance.base import BankTransaction, BillMatchResult

log = logging.getLogger("postmule.finance.plaid")

_ENVIRONMENTS = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}


class PlaidProvider:
    """
    Fetches bank transactions from Plaid via the /transactions/get endpoint.

    Plaid amount convention: positive = debit (money leaving account).
    This provider normalizes to PostMule convention: negative = expense.

    Args:
        client_id:    Plaid application client_id.
        secret:       Plaid secret for the chosen environment.
        access_token: Per-institution access token from the Link flow.
        environment:  "sandbox" | "development" | "production" (default: development).
    """

    def __init__(
        self,
        client_id: str,
        secret: str,
        access_token: str,
        environment: str = "development",
    ) -> None:
        self.client_id = client_id
        self.secret = secret
        self.access_token = access_token
        self.base_url = _ENVIRONMENTS.get(environment, _ENVIRONMENTS["development"])

    def _auth(self) -> dict:
        return {"client_id": self.client_id, "secret": self.secret}

    def get_recent_transactions(self, days: int = 30) -> list[BankTransaction]:
        """
        Fetch transactions from Plaid for the last N days.

        Returns:
            List of BankTransaction objects (amount negative = expense).
        """
        try:
            import requests
        except ImportError:
            raise RuntimeError(
                "requests is not installed.\nRun: pip install requests"
            )

        today = date.today()
        start_date = (today - timedelta(days=days)).isoformat()
        end_date = today.isoformat()

        body = {
            **self._auth(),
            "access_token": self.access_token,
            "start_date": start_date,
            "end_date": end_date,
            "options": {"count": 500, "offset": 0},
        }
        url = f"{self.base_url}/transactions/get"
        resp = requests.post(url, json=body, timeout=30)
        resp.raise_for_status()

        transactions = []
        for t in resp.json().get("transactions", []):
            # Plaid: positive amount = debit (spending). Negate to match PostMule convention.
            transactions.append(BankTransaction(
                transaction_id=t["transaction_id"],
                date=t["date"],
                amount=-t["amount"],
                payee=t.get("name") or "",
                account=t.get("account_id") or "",
                memo=t.get("original_description") or "",
            ))

        log.info(f"Fetched {len(transactions)} transactions from Plaid")
        return transactions

    def update_transaction_name(self, transaction_id: str, new_name: str) -> bool:
        """
        Plaid does not expose a transaction rename endpoint for standard API access.
        The payee name correction is logged but not written back to Plaid.

        Returns:
            False (not supported).
        """
        log.info(
            f"Plaid: transaction rename not supported via API "
            f"(would rename {transaction_id} to '{new_name}')"
        )
        return False
