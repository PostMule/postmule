"""
Outlook / Microsoft 365 email provider — Microsoft Graph API.

Covers Microsoft 365 / work accounts (outlook.office365.com).
Uses the Microsoft Graph API with an OAuth2 access token.

Config example:
    email:
      providers:
        - service: outlook_365
          enabled: true
          role: mailbox_notifications
          address: you@yourcompany.com
"""

from __future__ import annotations

from postmule.providers.email._graph import GraphEmailProvider

SERVICE_KEY = "outlook_365"
DISPLAY_NAME = "Outlook / Microsoft 365"


class Outlook365Provider(GraphEmailProvider):
    """
    Outlook 365 (Microsoft 365 / work accounts) email provider.

    Uses the Microsoft Graph API. Requires a valid OAuth2 access token —
    obtain via the Azure AD OAuth flow in the Providers setup page.

    Args:
        access_token:       Microsoft Graph API bearer token.
        processed_category: Outlook category name applied to processed mail (default: PostMule).
        sender_filter:      Default From address filter (applied when no override given).
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
