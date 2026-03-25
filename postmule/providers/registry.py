"""
Provider registry — complete catalog of all supported provider implementations.

This is the authoritative list of every backend PostMule can use. The Providers
page reads from this module to show configured vs. available options.

Structure per entry:
  service       — SERVICE_KEY used in config.yaml
  display_name  — Human-readable name shown in the UI
  status        — "implemented" (ready to configure) or "stub" (planned, not yet built)
  auth_type     — how the provider authenticates:
                    "oauth2"    — OAuth 2.0 flow (requires browser redirect)
                    "api_key"   — static API key or token in credentials.yaml
                    "password"  — username + password (browser automation)
                    "bridge"    — local bridge process required (e.g. Proton Bridge)
                    "local"     — no auth needed; runs on localhost
                    "none"      — no auth (disabled/no-op provider)
"""

from __future__ import annotations

from typing import TypedDict


class ProviderEntry(TypedDict):
    service: str
    display_name: str
    status: str  # "implemented" | "stub"
    auth_type: str  # "oauth2" | "api_key" | "password" | "bridge" | "local" | "none"


PROVIDER_REGISTRY: dict[str, list[ProviderEntry]] = {
    "mailbox": [
        {
            "service": "vpm",
            "display_name": "Virtual Post Mail",
            "status": "implemented",
            "auth_type": "api_key",
        },
        {
            "service": "earth_class",
            "display_name": "Earth Class Mail",
            "status": "stub",
            "auth_type": "api_key",
        },
        {
            "service": "traveling_mailbox",
            "display_name": "Traveling Mailbox",
            "status": "stub",
            "auth_type": "api_key",
        },
        {
            "service": "postscan",
            "display_name": "PostScan Mail",
            "status": "stub",
            "auth_type": "api_key",
        },
    ],
    "email": [
        {
            "service": "gmail",
            "display_name": "Gmail",
            "status": "implemented",
            "auth_type": "oauth2",
        },
        {
            "service": "outlook_com",
            "display_name": "Outlook.com",
            "status": "stub",
            "auth_type": "oauth2",
        },
        {
            "service": "outlook_365",
            "display_name": "Outlook 365",
            "status": "stub",
            "auth_type": "oauth2",
        },
        {
            "service": "proton",
            "display_name": "Proton Mail",
            "status": "stub",
            "auth_type": "bridge",
        },
        {
            "service": "imap",
            "display_name": "Generic IMAP",
            "status": "stub",
            "auth_type": "password",
        },
    ],
    "storage": [
        {
            "service": "google_drive",
            "display_name": "Google Drive",
            "status": "implemented",
            "auth_type": "oauth2",
        },
        {
            "service": "s3",
            "display_name": "Amazon S3",
            "status": "stub",
            "auth_type": "api_key",
        },
        {
            "service": "dropbox",
            "display_name": "Dropbox",
            "status": "stub",
            "auth_type": "oauth2",
        },
        {
            "service": "onedrive",
            "display_name": "OneDrive",
            "status": "stub",
            "auth_type": "oauth2",
        },
    ],
    "spreadsheet": [
        {
            "service": "google_sheets",
            "display_name": "Google Sheets",
            "status": "implemented",
            "auth_type": "oauth2",
        },
        {
            "service": "excel_online",
            "display_name": "Excel Online",
            "status": "stub",
            "auth_type": "oauth2",
        },
        {
            "service": "airtable",
            "display_name": "Airtable",
            "status": "stub",
            "auth_type": "api_key",
        },
        {
            "service": "none",
            "display_name": "None (disabled)",
            "status": "implemented",
            "auth_type": "none",
        },
    ],
    "llm": [
        {
            "service": "gemini",
            "display_name": "Google Gemini",
            "status": "implemented",
            "auth_type": "api_key",
        },
        {
            "service": "openai",
            "display_name": "OpenAI",
            "status": "stub",
            "auth_type": "api_key",
        },
        {
            "service": "anthropic",
            "display_name": "Anthropic Claude",
            "status": "stub",
            "auth_type": "api_key",
        },
        {
            "service": "ollama",
            "display_name": "Ollama (local)",
            "status": "stub",
            "auth_type": "local",
        },
    ],
    "finance": [
        {
            "service": "ynab",
            "display_name": "YNAB",
            "status": "implemented",
            "auth_type": "api_key",
        },
        {
            "service": "plaid",
            "display_name": "Plaid",
            "status": "implemented",
            "auth_type": "api_key",
        },
        {
            "service": "simplifi",
            "display_name": "Simplifi",
            "status": "implemented",
            "auth_type": "password",
        },
        {
            "service": "monarch",
            "display_name": "Monarch Money",
            "status": "implemented",
            "auth_type": "password",
        },
    ],
}

CATEGORY_DISPLAY_NAMES: dict[str, str] = {
    "mailbox": "Mailbox",
    "email": "Email",
    "storage": "Storage",
    "spreadsheet": "Spreadsheet",
    "llm": "AI / LLM",
    "finance": "Finance",
}


def get_provider(category: str, service: str) -> ProviderEntry | None:
    """Return registry entry for a specific category + service, or None."""
    for entry in PROVIDER_REGISTRY.get(category, []):
        if entry["service"] == service:
            return entry
    return None
