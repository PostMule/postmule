"""
PostMule Google authentication helper (developer use only).

Run this once after scripts/dev_setup.sh to authenticate with Google and
save the refresh token to the system keychain.  Uses the client_id and
client_secret already baked into postmule/core/constants.py.

Usage:
    python scripts/google_auth.py
"""

from __future__ import annotations

import sys


def _require(package: str, install: str) -> None:
    try:
        __import__(package)
    except ImportError:
        print(f"\nError: '{install}' is not installed.")
        print(f"Run:  pip install {install}")
        sys.exit(1)


def main() -> None:
    _require("google_auth_oauthlib", "google-auth-oauthlib")

    from postmule.core.constants import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_SCOPES
    from postmule.core.credentials import save_google_refresh_token

    if not GOOGLE_CLIENT_ID:
        print("Error: GOOGLE_CLIENT_ID is empty in postmule/core/constants.py.")
        print("Run scripts/dev_setup.sh first to bake in the OAuth client credentials.")
        sys.exit(1)

    from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import]

    client_config = {
        "installed": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=GOOGLE_SCOPES)

    print("=" * 60)
    print("  PostMule — Google Authentication")
    print("=" * 60)
    print()
    print("Opening browser for Google authentication...")
    print("Sign in and click Allow to grant all requested permissions.")
    print()

    try:
        creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    except Exception as exc:
        print(f"Browser-based flow failed ({exc}).")
        print("Falling back to manual copy-paste flow...")
        creds = flow.run_console()

    if not creds.refresh_token:
        print()
        print("Error: no refresh_token received.")
        print("This usually means this app was already authorized.")
        print("Revoke it at https://myaccount.google.com/permissions then re-run.")
        sys.exit(1)

    save_google_refresh_token(creds.refresh_token)

    print()
    print("Google authentication successful.")
    print("Refresh token saved to system keychain (Windows Credential Manager).")
    print()
    print("Next steps:")
    print("  1. Run a dry-run:  postmule --dry-run")
    print("  2. Check the dashboard:  postmule serve")
    print()


if __name__ == "__main__":
    main()
