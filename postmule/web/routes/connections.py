"""Connections blueprint — Google OAuth flow routes and credential management."""

from __future__ import annotations

import logging
import os

import yaml
from flask import Blueprint, jsonify, redirect, request, session, url_for

from postmule.core.constants import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_SCOPES

import postmule.web.app as _app

log = logging.getLogger("postmule.web")

connections_bp = Blueprint("connections", __name__)


@connections_bp.route("/setup/oauth/google")
def setup_oauth_google():
    """Redirect the user to Google's consent screen using baked-in client credentials."""
    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore[import]
    except ImportError:
        return jsonify({"error": "google-auth-oauthlib not installed"}), 500

    if not GOOGLE_CLIENT_ID:
        return jsonify({"error": "GOOGLE_CLIENT_ID not configured — run scripts/dev_setup.sh"}), 500

    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [url_for("connections.setup_oauth_google_callback", _external=True)],
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=GOOGLE_SCOPES,
        redirect_uri=url_for("connections.setup_oauth_google_callback", _external=True),
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    session["setup_google_oauth_state"] = state
    return redirect(auth_url)


@connections_bp.route("/setup/oauth/google/callback")
def setup_oauth_google_callback():
    """Receive the authorization code from Google, exchange for tokens, save refresh token to keychain."""
    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore[import]
    except ImportError:
        return "google-auth-oauthlib not installed", 500

    state = session.get("setup_google_oauth_state")
    if not state:
        return redirect(url_for("pages.connections") + "?error=session_expired")

    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [url_for("connections.setup_oauth_google_callback", _external=True)],
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=GOOGLE_SCOPES,
        state=state,
        redirect_uri=url_for("connections.setup_oauth_google_callback", _external=True),
    )

    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as exc:
        log.error(f"Google OAuth token exchange failed: {exc}")
        return redirect(url_for("pages.connections") + "?error=oauth_failed")

    creds = flow.credentials
    if not creds.refresh_token:
        return redirect(url_for("pages.connections") + "?error=no_refresh_token")

    try:
        from postmule.core.credentials import save_google_refresh_token
        save_google_refresh_token(creds.refresh_token)
    except Exception as exc:
        log.error(f"Failed to save Google refresh token: {exc}")
        return redirect(url_for("pages.connections") + "?error=keychain_save_failed")

    log.info("Google OAuth refresh token saved to system keychain")
    session.pop("setup_google_oauth_state", None)
    return redirect(url_for("pages.connections") + "?google_ok=1")


@connections_bp.route("/api/connection/provider", methods=["POST"])
def set_connection_provider():
    """Switch active provider for a config category. Updates config.yaml in-place."""
    category = request.form.get("category", "").strip()
    provider_type = request.form.get("type", "").strip()
    tab = request.form.get("tab", category)

    _VALID = {"mailbox", "email", "storage", "spreadsheet", "llm", "finance"}
    if category not in _VALID:
        return redirect(url_for("pages.connections") + f"?tab={tab}&error=invalid_category")

    config_path = _app._config_path
    if not config_path or not config_path.exists():
        return redirect(url_for("pages.connections") + f"?tab={tab}&error=no_config")

    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        providers = raw.setdefault(category, {}).setdefault("providers", [{}])
        if not providers:
            providers.append({})
        providers[0]["type"] = provider_type
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(raw, f, allow_unicode=True, default_flow_style=False)
        _app._config_raw = raw
        try:
            from postmule.core.config import load_config
            _app._config = load_config(config_path)
        except Exception:
            pass
    except Exception as exc:
        log.error(f"Failed to update provider: {exc}")
        return redirect(url_for("pages.connections") + f"?tab={tab}&error=save_failed")

    return redirect(url_for("pages.connections") + f"?tab={tab}&saved=1")


@connections_bp.route("/api/credential", methods=["POST"])
def save_credential():
    """Save a credential field to credentials.enc without writing plaintext to disk."""
    provider = request.form.get("provider", "").strip()
    field = request.form.get("field", "").strip()
    value = request.form.get("value", "").strip()
    tab = request.form.get("tab", "")

    if not provider or not field:
        return redirect(url_for("pages.connections") + f"?tab={tab}&error=missing_fields")
    if not value:
        return redirect(url_for("pages.connections") + f"?tab={tab}&error=empty_value")

    enc_path = _app._enc_path
    try:
        from postmule.core.credentials import (
            _derive_key,
            _SALT_LEN,
            load_master_password,
            decrypt_credentials,
            CredentialsError,
        )
        from cryptography.fernet import Fernet

        master_pw = load_master_password()
        if not master_pw:
            return redirect(url_for("pages.connections") + f"?tab={tab}&error=no_master_password")

        try:
            creds: dict = decrypt_credentials(enc_path, master_pw)
        except (CredentialsError, FileNotFoundError, OSError):
            creds = {}

        if provider not in creds or not isinstance(creds[provider], dict):
            creds[provider] = {}
        creds[provider][field] = value

        plaintext = yaml.dump(creds, allow_unicode=True).encode("utf-8")
        salt = os.urandom(_SALT_LEN)
        key = _derive_key(master_pw, salt)
        token = Fernet(key).encrypt(plaintext)
        enc_path.write_bytes(salt + token)

    except Exception as exc:
        log.error(f"Failed to save credential: {exc}")
        return redirect(url_for("pages.connections") + f"?tab={tab}&error=cred_save_failed")

    return redirect(url_for("pages.connections") + f"?tab={tab}&saved=1")
