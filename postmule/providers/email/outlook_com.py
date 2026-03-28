"""
Outlook.com email provider — Microsoft Graph API.

Covers personal Microsoft accounts (@outlook.com, @hotmail.com, @live.com).
Uses the Microsoft Graph API with an OAuth2 access token.

Config example:
    email:
      providers:
        - service: outlook_com
          enabled: true
          role: mailbox_notifications
          address: you@outlook.com
"""

from __future__ import annotations

from postmule.providers.email._graph import GraphEmailProvider

SERVICE_KEY = "outlook_com"
DISPLAY_NAME = "outlook.com / Hotmail / Live"


class OutlookComProvider(GraphEmailProvider):
    """
    Outlook.com (personal Microsoft accounts) email provider.

    Uses the Microsoft Graph API. Requires a valid OAuth2 access token —
    obtain via the Microsoft personal account OAuth flow in the Providers setup page.

    Args:
        access_token:       Microsoft Graph API bearer token.
        processed_category: Outlook category name applied to processed mail (default: PostMule).
        sender_filter:      Default From address filter.
        subject_filter:     Default Subject filter.
    """

    def __init__(
        self,
        access_token: str,
        processed_category: str = "PostMule",
        sender_filter: str = "",
        subject_filter: str = "",
    ) -> None:
        super().__init__(
            access_token=access_token,
            processed_category=processed_category,
            default_sender_filter=sender_filter,
            default_subject_filter=subject_filter,
        )
