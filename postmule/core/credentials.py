"""
Credential encryption and decryption using Fernet symmetric encryption.

Flow:
  1. User fills in credentials.yaml (plaintext, never committed to git).
  2. `postmule encrypt-credentials` reads credentials.yaml, derives a Fernet key from
     the master password (stored in the system keychain), and writes
     credentials.enc (safe to back up / commit).
  3. On each run, PostMule reads the master password from the system keychain,
     decrypts credentials.enc into memory — credentials.yaml is never needed again.

Master password storage uses the system keychain via the `keyring` library:
  - Windows: Windows Credential Manager (DPAPI)
  - macOS:   Keychain
  - Linux:   Secret Service / libsecret

File format for credentials.enc:
  [16 bytes random salt] + [Fernet token]
The salt is generated fresh on each encryption; the Fernet token is the
PBKDF2-derived key applied to the YAML plaintext.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import yaml
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_KEYRING_SERVICE = "PostMule"
_KEYRING_USER = "MasterPassword"
_KDF_ITERATIONS = 480_000
_SALT_LEN = 16


class CredentialsError(Exception):
    """Raised for any credential encryption/decryption problem."""


# ------------------------------------------------------------------
# Key derivation
# ------------------------------------------------------------------

def _derive_key(master_password: str, salt: bytes) -> bytes:
    """Derive a 32-byte Fernet key from the master password and salt using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_KDF_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(master_password.encode("utf-8")))


# ------------------------------------------------------------------
# System keychain (keyring)
# ------------------------------------------------------------------

def save_master_password(password: str) -> None:
    """
    Store the master password in the system keychain.
    Uses `keyring` (Windows Credential Manager, macOS Keychain, Linux Secret Service).
    Called once during initial setup.
    """
    try:
        import keyring  # type: ignore[import]
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USER, password)
    except ImportError:
        raise CredentialsError(
            "keyring is not installed.\n"
            "Run: pip install keyring"
        )
    except Exception as exc:
        raise CredentialsError(
            f"Failed to save master password to system keychain:\n{exc}\n"
            "Make sure you are running as the correct user."
        ) from exc


def load_master_password() -> str:
    """
    Read the master password from the system keychain.
    Raises CredentialsError if not found (setup not complete).
    """
    try:
        import keyring  # type: ignore[import]
        value = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USER)
    except ImportError:
        raise CredentialsError(
            "keyring is not installed — cannot read from system keychain.\n"
            "Run: pip install keyring"
        )
    except Exception as exc:
        raise CredentialsError(
            f"Failed to read master password from system keychain:\n{exc}"
        ) from exc

    if value is None:
        raise CredentialsError(
            "Master password not found in system keychain.\n"
            "Run the setup wizard or: postmule set-master-password"
        )
    return value


# ------------------------------------------------------------------
# Encrypt / decrypt credentials file
# ------------------------------------------------------------------

def encrypt_credentials(yaml_path: Path, enc_path: Path, master_password: str) -> None:
    """
    Read credentials.yaml, encrypt it, write credentials.enc.

    Args:
        yaml_path:       Path to plaintext credentials.yaml
        enc_path:        Output path for credentials.enc
        master_password: The master password string
    """
    if not yaml_path.exists():
        raise CredentialsError(
            f"Credentials file not found: {yaml_path}\n"
            "Copy credentials.example.yaml to credentials.yaml and fill in your values."
        )

    plaintext = yaml_path.read_bytes()

    # Validate it's parseable YAML before encrypting
    try:
        yaml.safe_load(plaintext)
    except yaml.YAMLError as exc:
        raise CredentialsError(
            f"credentials.yaml has a syntax error:\n{exc}\n"
            "Fix the YAML before encrypting."
        ) from exc

    salt = os.urandom(_SALT_LEN)
    key = _derive_key(master_password, salt)
    token = Fernet(key).encrypt(plaintext)
    enc_path.write_bytes(salt + token)


def decrypt_credentials(enc_path: Path, master_password: str) -> dict[str, Any]:
    """
    Decrypt credentials.enc and return the parsed credentials dict.
    The decrypted data is kept only in memory — never written to disk.

    Args:
        enc_path:        Path to credentials.enc
        master_password: The master password string

    Returns:
        Dict of credentials (mirrors credentials.yaml structure).
    """
    if not enc_path.exists():
        raise CredentialsError(
            f"Encrypted credentials not found: {enc_path}\n"
            "Run: postmule encrypt-credentials\n"
            "Or run the setup wizard to create credentials.enc."
        )

    raw = enc_path.read_bytes()
    salt, token = raw[:_SALT_LEN], raw[_SALT_LEN:]
    key = _derive_key(master_password, salt)
    try:
        plaintext = Fernet(key).decrypt(token)
    except InvalidToken:
        raise CredentialsError(
            "Failed to decrypt credentials.enc — wrong master password.\n"
            "If you changed your master password, re-encrypt with: postmule encrypt-credentials"
        )

    data = yaml.safe_load(plaintext)
    if not isinstance(data, dict):
        raise CredentialsError(
            "Decrypted credentials.enc did not produce a valid key-value structure.\n"
            "The file may be corrupt. Re-encrypt from credentials.yaml."
        )
    return data


# ------------------------------------------------------------------
# Convenience: load credentials for a running session
# ------------------------------------------------------------------

def load_credentials(enc_path: Path) -> dict[str, Any]:
    """
    Full pipeline: read master password from Credential Manager, decrypt credentials.enc.
    This is the function called at the start of every daily run.
    """
    master_password = load_master_password()
    return decrypt_credentials(enc_path, master_password)


# ------------------------------------------------------------------
# Google OAuth token storage via system keyring
# (used instead of credentials.yaml for the standard Google flow)
# ------------------------------------------------------------------

def save_google_refresh_token(refresh_token: str) -> None:
    """
    Store the Google OAuth refresh token in the system keychain.
    Called once after the user completes the Google consent screen.
    No master password required — the OS keychain handles encryption.
    """
    from postmule.core.constants import KEYRING_SERVICE, KEYRING_GOOGLE_REFRESH_TOKEN
    try:
        import keyring  # type: ignore[import]
        keyring.set_password(KEYRING_SERVICE, KEYRING_GOOGLE_REFRESH_TOKEN, refresh_token)
    except ImportError:
        raise CredentialsError("keyring is not installed.\nRun: pip install keyring")
    except Exception as exc:
        raise CredentialsError(
            f"Failed to save Google refresh token to system keychain:\n{exc}"
        ) from exc


def load_google_refresh_token() -> str:
    """
    Read the Google OAuth refresh token from the system keychain.
    Raises CredentialsError if not found (setup not complete).
    """
    from postmule.core.constants import KEYRING_SERVICE, KEYRING_GOOGLE_REFRESH_TOKEN
    try:
        import keyring  # type: ignore[import]
        value = keyring.get_password(KEYRING_SERVICE, KEYRING_GOOGLE_REFRESH_TOKEN)
    except ImportError:
        raise CredentialsError("keyring is not installed.\nRun: pip install keyring")
    except Exception as exc:
        raise CredentialsError(
            f"Failed to read Google refresh token from system keychain:\n{exc}"
        ) from exc

    if value is None:
        raise CredentialsError(
            "Google account not connected.\n"
            "Open the PostMule dashboard and click 'Connect Google Account'."
        )
    return value


def save_credential(enc_path: "Path", provider: str, field: str, value: str) -> None:
    """
    Update a single nested credential value in credentials.enc without touching
    any other values.  The updated dict is re-encrypted in place.

    Args:
        enc_path: Path to credentials.enc
        provider: Top-level key, e.g. ``"vpm"`` or ``"anthropic"``
        field:    Sub-key, e.g. ``"password"`` or ``"api_key"``
        value:    New string value
    """
    from pathlib import Path as _Path
    master_password = load_master_password()
    # Load existing — create empty dict if file doesn't exist yet
    if enc_path.exists():
        creds = decrypt_credentials(enc_path, master_password)
    else:
        creds = {}

    if not isinstance(creds.get(provider), dict):
        creds[provider] = {}
    creds[provider][field] = value

    # Re-encrypt and write back
    plaintext = yaml.safe_dump(creds, allow_unicode=True, default_flow_style=False).encode("utf-8")
    salt = os.urandom(_SALT_LEN)
    key = _derive_key(master_password, salt)
    token = Fernet(key).encrypt(plaintext)
    enc_path.write_bytes(salt + token)


def google_credentials_available() -> bool:
    """Return True if a Google refresh token exists in the system keychain."""
    try:
        load_google_refresh_token()
        return True
    except CredentialsError:
        return False


def build_google_credentials() -> "google.oauth2.credentials.Credentials":
    """
    Build a google.oauth2.credentials.Credentials object from the stored
    refresh token and the baked-in client_id / client_secret.
    The credentials auto-refresh when expired (no user interaction needed).
    """
    from postmule.core.constants import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_SCOPES
    try:
        from google.oauth2.credentials import Credentials  # type: ignore[import]
        from google.auth.transport.requests import Request  # type: ignore[import]
    except ImportError:
        raise CredentialsError(
            "google-auth is not installed.\nRun: pip install google-auth"
        )

    if not GOOGLE_CLIENT_ID:
        raise CredentialsError(
            "GOOGLE_CLIENT_ID is not set in postmule/core/constants.py.\n"
            "Run scripts/dev_setup.sh to generate and bake in the OAuth client."
        )

    refresh_token = load_google_refresh_token()
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=GOOGLE_SCOPES,
    )
    # Eagerly refresh so callers get a valid access token immediately
    creds.refresh(Request())
    return creds
