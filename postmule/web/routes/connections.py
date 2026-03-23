"""Connections blueprint — Google OAuth flow routes."""

from __future__ import annotations

import logging

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
