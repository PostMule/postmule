"""
Proton Mail email provider — thin wrapper around ImapProvider.

Uses Proton Bridge (localhost IMAP proxy) — no cloud credentials are sent.
PostMule pre-fills Proton Bridge defaults: host=127.0.0.1, port=1143.

Config example:
    email:
      providers:
        - service: proton
          enabled: true
          role: mailbox_notifications
          address: you@proton.me
          # bridge_host and bridge_port default to 127.0.0.1 / 1143
"""

from __future__ import annotations

from postmule.providers.email.imap import ImapProvider

SERVICE_KEY = "proton"
DISPLAY_NAME = "Proton Mail"

# Proton Bridge IMAP defaults — pre-filled when service: proton is selected
BRIDGE_DEFAULT_HOST = "127.0.0.1"
BRIDGE_DEFAULT_PORT = 1143


class ProtonMailProvider(ImapProvider):
    """
    Proton Mail provider via Proton Bridge (local IMAP proxy).

    Requires Proton Bridge to be running locally before PostMule can connect.
    All IMAP logic is inherited from ImapProvider — only the defaults differ.

    Args:
        username:          Proton Mail address (e.g., you@proton.me).
        password:          Proton Bridge password (NOT your Proton account password).
        bridge_host:       Proton Bridge hostname (default: 127.0.0.1).
        bridge_port:       Proton Bridge IMAP port (default: 1143).
        use_ssl:           Use SSL for Bridge connection (default: False — Bridge handles it locally).
        processed_folder:  IMAP folder to move processed emails into (default: PostMule).
    """

    def __init__(
        self,
        username: str,
        password: str,
        bridge_host: str = BRIDGE_DEFAULT_HOST,
        bridge_port: int = BRIDGE_DEFAULT_PORT,
        use_ssl: bool = False,
        processed_folder: str = "PostMule",
    ) -> None:
        super().__init__(
            host=bridge_host,
            port=bridge_port,
            username=username,
            password=password,
            use_ssl=use_ssl,
            processed_folder=processed_folder,
        )

    def health_check(self):
        """Return a HealthResult indicating whether Proton Bridge is reachable."""
        from postmule.providers import HealthResult
        result = super().health_check()
        if result.ok:
            return HealthResult(
                ok=True,
                status="ok",
                message=f"Proton Bridge connected at {self.host}:{self.port}",
            )
        return HealthResult(
            ok=False,
            status="error",
            message=f"Proton Bridge not reachable at {self.host}:{self.port}: {result.message}",
        )
