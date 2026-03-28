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
        return redirect(url_for("pages.providers") + "?error=session_expired")

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
        return redirect(url_for("pages.providers") + "?error=oauth_failed")

    creds = flow.credentials
    if not creds.refresh_token:
        return redirect(url_for("pages.providers") + "?error=no_refresh_token")

    try:
        from postmule.core.credentials import save_google_refresh_token
        save_google_refresh_token(creds.refresh_token)
    except Exception as exc:
        log.error(f"Failed to save Google refresh token: {exc}")
        return redirect(url_for("pages.providers") + "?error=keychain_save_failed")

    log.info("Google OAuth refresh token saved to system keychain")
    session.pop("setup_google_oauth_state", None)
    return redirect(url_for("pages.providers") + "?google_ok=1")


@connections_bp.route("/api/connection/provider", methods=["POST"])
def set_connection_provider():
    """Switch active provider for a config category. Updates config.yaml in-place."""
    category = request.form.get("category", "").strip()
    provider_type = request.form.get("service", "").strip()
    tab = request.form.get("tab", category)

    _VALID = {"mailbox", "email", "storage", "spreadsheet", "llm", "finance"}
    if category not in _VALID:
        return redirect(url_for("pages.providers") + f"?tab={tab}&error=invalid_category")

    config_path = _app._config_path
    if not config_path or not config_path.exists():
        return redirect(url_for("pages.providers") + f"?tab={tab}&error=no_config")

    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        providers = raw.setdefault(category, {}).setdefault("providers", [{}])
        if not providers:
            providers.append({})
        providers[0]["service"] = provider_type
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
        return redirect(url_for("pages.providers") + f"?tab={tab}&error=save_failed")

    return redirect(url_for("pages.providers") + f"?tab={tab}&saved=1")


# ------------------------------------------------------------------
# Provider health-check and config-save routes (#44, #47)
# ------------------------------------------------------------------

_CONFIG_FIELDS: dict[str, list[str]] = {
    "email": ["label_name"],
    "storage": ["root_folder"],
    "spreadsheet": ["workbook_name"],
    "llm": ["model"],
}

# Per-service non-sensitive config fields (stored in config.yaml)
_SERVICE_CONFIG_FIELDS: dict[str, list[str]] = {
    "gmail": ["label_name"],
    "imap": ["host", "port", "use_ssl", "processed_folder", "inbox_folder"],
    "proton": ["bridge_host", "bridge_port", "processed_folder"],
    "outlook_365": ["processed_category"],
    "outlook_com": ["processed_category"],
    "google_drive": ["root_folder"],
    "s3": ["bucket", "region", "root_prefix"],
    "dropbox": ["root_folder"],
    "onedrive": ["root_folder"],
    "google_sheets": ["workbook_name"],
    "excel_online": ["workbook_name"],
    "airtable": ["base_id", "workbook_name"],
    "gemini": ["model"],
    "anthropic": ["model"],
    "openai": ["model"],
    "ollama": ["host", "model"],
}

_TAB_MAP = {
    "mailbox": "mailbox",
    "email": "email",
    "storage": "storage",
    "spreadsheet": "spreadsheet",
    "llm": "llm",
    "finance": "finance",
}


def _tab_for(category: str) -> str:
    return _TAB_MAP.get(category, category)


def _get_cred(*keys: str):
    """Decrypt credentials.enc and return a nested key. Returns None on any error."""
    try:
        from postmule.core.credentials import load_credentials
        creds = load_credentials(_app._enc_path)
        node = creds
        for k in keys:
            if not isinstance(node, dict):
                return None
            node = node.get(k)
        return node
    except Exception:
        return None


def _get_account_creds(account_id: str) -> dict:
    """Return the credential dict for a specific email account by UUID."""
    try:
        from postmule.core.credentials import load_credentials
        creds = load_credentials(_app._enc_path)
        return creds.get("accounts", {}).get(account_id, {})
    except Exception:
        return {}


def _find_email_account(account_id: str) -> dict | None:
    """Find an email provider entry by its id field in config.yaml."""
    cfg = _app._config_raw
    return next(
        (p for p in cfg.get("email", {}).get("providers", [])
         if p.get("id") == account_id),
        None,
    )


def _build_provider(category: str, service: str, account_id: str | None = None):
    """Instantiate a provider object for health-check, or raise ValueError."""
    cfg = _app._config_raw

    if category == "email":
        if account_id:
            ep = _find_email_account(account_id)
            if ep is None:
                raise ValueError(f"Email account {account_id!r} not found in config")
            acct_creds = _get_account_creds(account_id)
        else:
            ep = (cfg.get("email", {}).get("providers") or [{}])[0]
            acct_creds = {}

        if service == "gmail":
            from postmule.core.credentials import google_credentials_available, build_google_credentials
            if not google_credentials_available():
                raise ValueError("Google credentials not configured")
            gcreds = build_google_credentials()
            label = ep.get("label_name", "PostMule")
            from postmule.providers.email.gmail import GmailProvider
            return GmailProvider(gcreds, label_name=label)

        if service == "imap":
            username = acct_creds.get("username", "")
            password = acct_creds.get("password", "")
            if not username or not password:
                raise ValueError("IMAP credentials not configured")
            if not ep.get("host"):
                raise ValueError("IMAP host not configured")
            from postmule.providers.email.imap import ImapProvider
            return ImapProvider(
                host=ep.get("host", ""),
                port=int(ep.get("port", 993)),
                username=username,
                password=password,
                use_ssl=str(ep.get("use_ssl", "true")).lower() not in ("false", "0", "no"),
                processed_folder=ep.get("processed_folder", "PostMule"),
            )

        if service == "proton":
            username = acct_creds.get("username", "")
            password = acct_creds.get("password", "")
            if not username or not password:
                raise ValueError("Proton Bridge credentials not configured")
            from postmule.providers.email.proton import ProtonMailProvider
            return ProtonMailProvider(
                username=username,
                password=password,
                bridge_host=ep.get("bridge_host", "127.0.0.1"),
                bridge_port=int(ep.get("bridge_port", 1143)),
                processed_folder=ep.get("processed_folder", "PostMule"),
            )

        if service == "outlook_365":
            token = acct_creds.get("access_token", "")
            if not token:
                raise ValueError("Outlook 365 access token not configured")
            from postmule.providers.email.outlook_365 import Outlook365Provider
            return Outlook365Provider(
                access_token=token,
                processed_category=ep.get("processed_category", "PostMule"),
            )

        if service == "outlook_com":
            token = acct_creds.get("access_token", "")
            if not token:
                raise ValueError("Outlook.com access token not configured")
            from postmule.providers.email.outlook_com import OutlookComProvider
            return OutlookComProvider(
                access_token=token,
                processed_category=ep.get("processed_category", "PostMule"),
            )

        raise ValueError(f"Unknown email service: {service}")

    if category == "storage" and service == "google_drive":
        from postmule.core.credentials import google_credentials_available, build_google_credentials
        if not google_credentials_available():
            raise ValueError("Google credentials not configured")
        creds = build_google_credentials()
        root = (cfg.get("storage", {}).get("providers") or [{}])[0].get("root_folder", "PostMule")
        from postmule.providers.storage.google_drive import DriveProvider
        return DriveProvider(creds, root_folder=root)

    if category == "spreadsheet" and service == "google_sheets":
        from postmule.core.credentials import google_credentials_available, build_google_credentials
        if not google_credentials_available():
            raise ValueError("Google credentials not configured")
        creds = build_google_credentials()
        name = (cfg.get("spreadsheet", {}).get("providers") or [{}])[0].get("workbook_name", "PostMule")
        from postmule.providers.spreadsheet.google_sheets import SheetsProvider
        return SheetsProvider(creds, workbook_name=name)

    if category == "llm" and service == "gemini":
        api_key = _get_cred("gemini", "api_key") or _get_cred("google", "gemini_api_key")
        if not api_key:
            raise ValueError("Gemini API key not configured")
        model = (cfg.get("llm", {}).get("providers") or [{}])[0].get("model", "gemini-1.5-flash")
        from postmule.providers.llm.gemini import GeminiProvider
        return GeminiProvider(api_key, model=model)

    if category == "mailbox" and service == "vpm":
        username = _get_cred("vpm", "username")
        password = _get_cred("vpm", "password")
        if not username or not password:
            raise ValueError("VPM credentials not configured")
        from postmule.providers.mailbox.vpm import VpmProvider
        return VpmProvider(username, password)

    if category == "llm" and service == "anthropic":
        api_key = _get_cred("anthropic", "api_key")
        if not api_key:
            raise ValueError("Anthropic API key not configured")
        model = (cfg.get("llm", {}).get("providers") or [{}])[0].get("model", "claude-haiku-4-5-20251001")
        from postmule.providers.llm.anthropic import AnthropicProvider
        return AnthropicProvider(api_key, model=model)

    if category == "llm" and service == "openai":
        api_key = _get_cred("openai", "api_key")
        if not api_key:
            raise ValueError("OpenAI API key not configured")
        model = (cfg.get("llm", {}).get("providers") or [{}])[0].get("model", "gpt-4o-mini")
        from postmule.providers.llm.openai import OpenAIProvider
        return OpenAIProvider(api_key, model=model)

    if category == "llm" and service == "ollama":
        lp = (cfg.get("llm", {}).get("providers") or [{}])[0]
        host = lp.get("host", "http://localhost:11434")
        model = lp.get("model", "llama3.2")
        from postmule.providers.llm.ollama import OllamaProvider
        return OllamaProvider(host=host, model=model)

    raise ValueError(f"Unknown provider: {category}/{service}")


@connections_bp.route("/api/providers/<category>/<service>/test", methods=["POST"])
def test_provider(category: str, service: str):
    """Run a live health-check against a provider and return JSON.

    For email providers, pass ?account_id=<uuid> to target a specific account.
    """
    account_id = request.args.get("account_id") or request.form.get("account_id") or None
    try:
        provider = _build_provider(category, service, account_id=account_id)
        result = provider.health_check()
        return jsonify({"ok": result.ok, "status": result.status, "message": result.message})
    except ValueError as exc:
        return jsonify({"ok": False, "status": "error", "message": str(exc)})
    except Exception as exc:
        log.error(f"health_check {category}/{service} failed: {exc}")
        return jsonify({"ok": False, "status": "error", "message": str(exc)})


@connections_bp.route("/api/providers/<category>/config", methods=["POST"])
def save_provider_config(category: str):
    """Save non-sensitive provider settings to config.yaml."""
    allowed = _CONFIG_FIELDS.get(category, [])
    tab = _tab_for(category)

    config_path = _app._config_path
    if not config_path or not config_path.exists():
        return redirect(url_for("pages.providers") + f"?tab={tab}&error=no_config")

    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        providers = raw.setdefault(category, {}).setdefault("providers", [{}])
        if not providers:
            providers.append({})
        for field in allowed:
            value = request.form.get(field)
            if value is not None:
                providers[0][field] = value.strip()
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(raw, f, allow_unicode=True, default_flow_style=False)
        _app._config_raw = raw
        try:
            from postmule.core.config import load_config
            _app._config = load_config(config_path)
        except Exception:
            pass
    except Exception as exc:
        log.error(f"Failed to save provider config: {exc}")
        return redirect(url_for("pages.providers") + f"?tab={tab}&error=save_failed")

    return redirect(url_for("pages.providers") + f"?tab={tab}&saved=1")


@connections_bp.route("/api/providers/<category>/<service>/config", methods=["POST"])
def save_service_config(category: str, service: str):
    """Save non-sensitive settings for a specific provider service to config.yaml.

    For email accounts, pass account_id to update a specific account entry by id.
    """
    allowed = _SERVICE_CONFIG_FIELDS.get(service, [])
    tab = _tab_for(category)
    account_id = request.form.get("account_id", "").strip() or None

    config_path = _app._config_path
    if not config_path or not config_path.exists():
        return redirect(url_for("pages.providers") + f"?tab={tab}&error=no_config")

    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        providers = raw.setdefault(category, {}).setdefault("providers", [{}])
        if not providers:
            providers.append({})

        if category == "email" and account_id:
            target = next((p for p in providers if p.get("id") == account_id), None)
            if target is None:
                return redirect(url_for("pages.providers") + f"?tab={tab}&error=account_not_found")
        else:
            target = providers[0]

        for fld in allowed:
            value = request.form.get(fld)
            if value is not None:
                target[fld] = value.strip()
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(raw, f, allow_unicode=True, default_flow_style=False)
        _app._config_raw = raw
        try:
            from postmule.core.config import load_config
            _app._config = load_config(config_path)
        except Exception:
            pass
    except Exception as exc:
        log.error(f"Failed to save service config: {exc}")
        return redirect(url_for("pages.providers") + f"?tab={tab}&error=save_failed")

    return redirect(url_for("pages.providers") + f"?tab={tab}&saved=1")


# ------------------------------------------------------------------
# Email account management routes (#68)
# ------------------------------------------------------------------

_VALID_EMAIL_SERVICES = {"gmail", "imap", "proton", "outlook_365", "outlook_com"}
_VALID_EMAIL_ROLES = {"mailbox_notifications", "bill_intake"}


def _save_config_yaml(raw: dict) -> None:
    """Atomically write config.yaml and refresh the in-memory config."""
    config_path = _app._config_path
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(raw, f, allow_unicode=True, default_flow_style=False)
    _app._config_raw = raw
    try:
        from postmule.core.config import load_config
        _app._config = load_config(config_path)
    except Exception:
        pass


@connections_bp.route("/api/email/accounts", methods=["POST"])
def add_email_account():
    """Add a new email account to config.yaml with a stable UUID id."""
    import uuid as _uuid
    service = request.form.get("service", "").strip()
    role = request.form.get("role", "mailbox_notifications").strip()
    address = request.form.get("address", "").strip()

    if service not in _VALID_EMAIL_SERVICES:
        return redirect(url_for("pages.providers") + "?tab=email&error=invalid_service")
    if role not in _VALID_EMAIL_ROLES:
        return redirect(url_for("pages.providers") + "?tab=email&error=invalid_role")

    config_path = _app._config_path
    if not config_path or not config_path.exists():
        return redirect(url_for("pages.providers") + "?tab=email&error=no_config")

    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        providers = raw.setdefault("email", {}).setdefault("providers", [])
        new_entry: dict = {
            "id": str(_uuid.uuid4()),
            "service": service,
            "role": role,
            "enabled": True,
        }
        if address:
            new_entry["address"] = address
        providers.append(new_entry)
        _save_config_yaml(raw)
    except Exception as exc:
        log.error(f"Failed to add email account: {exc}")
        return redirect(url_for("pages.providers") + "?tab=email&error=save_failed")

    return redirect(url_for("pages.providers") + "?tab=email&saved=1")


@connections_bp.route("/api/email/accounts/<account_id>/remove", methods=["POST"])
def remove_email_account(account_id: str):
    """Remove an email account from config.yaml and wipe its credentials."""
    config_path = _app._config_path
    if not config_path or not config_path.exists():
        return redirect(url_for("pages.providers") + "?tab=email&error=no_config")

    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        providers = raw.get("email", {}).get("providers", [])
        updated = [p for p in providers if p.get("id") != account_id]
        if len(updated) == len(providers):
            return redirect(url_for("pages.providers") + "?tab=email&error=account_not_found")
        raw.setdefault("email", {})["providers"] = updated
        _save_config_yaml(raw)
    except Exception as exc:
        log.error(f"Failed to remove email account: {exc}")
        return redirect(url_for("pages.providers") + "?tab=email&error=save_failed")

    # Wipe credentials for this account
    try:
        from postmule.core.credentials import (
            _derive_key, _SALT_LEN, load_master_password,
            decrypt_credentials, CredentialsError,
        )
        from cryptography.fernet import Fernet
        import yaml as _yaml

        master_pw = load_master_password()
        if master_pw:
            try:
                creds = decrypt_credentials(_app._enc_path, master_pw)
            except (CredentialsError, FileNotFoundError, OSError):
                creds = {}
            creds.get("accounts", {}).pop(account_id, None)
            plaintext = _yaml.dump(creds, allow_unicode=True).encode("utf-8")
            salt = os.urandom(_SALT_LEN)
            key = _derive_key(master_pw, salt)
            token = Fernet(key).encrypt(plaintext)
            _app._enc_path.write_bytes(salt + token)
    except Exception as exc:
        log.warning(f"Could not wipe credentials for account {account_id}: {exc}")

    return redirect(url_for("pages.providers") + "?tab=email&saved=1")


@connections_bp.route("/api/email/accounts/<account_id>/enable", methods=["POST"])
def enable_email_account(account_id: str):
    """Enable an email account in config.yaml."""
    return _set_email_account_enabled(account_id, True)


@connections_bp.route("/api/email/accounts/<account_id>/disable", methods=["POST"])
def disable_email_account(account_id: str):
    """Disable an email account in config.yaml."""
    return _set_email_account_enabled(account_id, False)


def _set_email_account_enabled(account_id: str, enabled: bool):
    config_path = _app._config_path
    if not config_path or not config_path.exists():
        return redirect(url_for("pages.providers") + "?tab=email&error=no_config")
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        providers = raw.get("email", {}).get("providers", [])
        target = next((p for p in providers if p.get("id") == account_id), None)
        if target is None:
            return redirect(url_for("pages.providers") + "?tab=email&error=account_not_found")
        target["enabled"] = enabled
        _save_config_yaml(raw)
    except Exception as exc:
        log.error(f"Failed to set email account enabled={enabled}: {exc}")
        return redirect(url_for("pages.providers") + "?tab=email&error=save_failed")
    return redirect(url_for("pages.providers") + "?tab=email&saved=1")


@connections_bp.route("/api/credential", methods=["POST"])
def save_credential():
    """Save a credential field to credentials.enc without writing plaintext to disk.

    For email accounts, pass account_id to store under accounts.<uuid>.<field>.
    Otherwise stores under creds[provider][field].
    """
    provider = request.form.get("provider", "").strip()
    field = request.form.get("field", "").strip()
    value = request.form.get("value", "").strip()
    tab = request.form.get("tab", "")
    account_id = request.form.get("account_id", "").strip() or None

    if not field:
        return redirect(url_for("pages.providers") + f"?tab={tab}&error=missing_fields")
    if not account_id and not provider:
        return redirect(url_for("pages.providers") + f"?tab={tab}&error=missing_fields")
    if not value:
        return redirect(url_for("pages.providers") + f"?tab={tab}&error=empty_value")

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
            return redirect(url_for("pages.providers") + f"?tab={tab}&error=no_master_password")

        try:
            creds: dict = decrypt_credentials(enc_path, master_pw)
        except (CredentialsError, FileNotFoundError, OSError):
            creds = {}

        if account_id:
            accounts = creds.setdefault("accounts", {})
            if account_id not in accounts or not isinstance(accounts[account_id], dict):
                accounts[account_id] = {}
            accounts[account_id][field] = value
        else:
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
        return redirect(url_for("pages.providers") + f"?tab={tab}&error=cred_save_failed")

    return redirect(url_for("pages.providers") + f"?tab={tab}&saved=1")
