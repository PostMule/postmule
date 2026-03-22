"""
PostMule application-level constants.

GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are the pre-registered OAuth 2.0
Desktop client credentials for the PostMule application.  These are intentionally
baked into the application — this is standard practice for installed Desktop apps.

Per Google's guidance, Desktop app client secrets are not truly secret (they can
be extracted from the binary), but they are required by the OAuth flow.  A stolen
client_id/secret cannot be used to access any user data without the user first
clicking Allow in their own Google account.

Reference: https://developers.google.com/identity/protocols/oauth2/native-app

To generate these values, run (developer only, one-time):
    bash scripts/dev_setup.sh
"""

# ---------------------------------------------------------------------------
# Pre-registered PostMule OAuth 2.0 Desktop client.
# Created once by the PostMule developer; baked into all installs.
# Users never need to touch Google Cloud Console.
# TODO: Replace "" with real values after running  bash scripts/dev_setup.sh
# ---------------------------------------------------------------------------
GOOGLE_CLIENT_ID: str = ""   # Set by running: bash scripts/dev_setup.sh
GOOGLE_CLIENT_SECRET: str = ""  # Set by running: bash scripts/dev_setup.sh

# OAuth scopes requested during the single Google consent screen.
# One consent covers Gmail (read + label), Drive, Sheets, and Gemini.
GOOGLE_SCOPES: list[str] = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

# ---------------------------------------------------------------------------
# Keyring service and credential keys
# System keyring (Windows Credential Manager / macOS Keychain / libsecret)
# is used for all credential storage — no plaintext files at rest.
# ---------------------------------------------------------------------------
KEYRING_SERVICE = "PostMule"
KEYRING_GOOGLE_REFRESH_TOKEN = "google_refresh_token"
KEYRING_MASTER_PASSWORD = "MasterPassword"
