"""
PostMule web dashboard — Flask + HTMX + Alpine.js.

Routes:
  GET  /              Home / status dashboard
  GET  /mail          All mail items (paginated)
  GET  /bills         Bills list + pending matches
  GET  /forward       ForwardToMe items
  GET  /pending        Pending entity matches + bill matches
  GET  /entities       Entity list
  GET  /settings       Config editor
  GET  /logs           Log viewer
  GET  /connections                  Service connection status and management
  GET  /corrections                  Entity correction log summary
  GET  /setup/oauth/google           Start Google OAuth flow (uses baked-in client credentials)
  GET  /setup/oauth/google/callback  OAuth callback — saves refresh token to system keychain
  POST /api/approve                 Approve a pending match
  POST /api/deny                    Deny a pending match
  POST /api/entity/<id>             Update a single entity field (marks user_verified)
  POST /api/entity/<id>/add-account Append an account number to an entity
  POST /api/mail/<id>/entity        Override entity association; optionally add alias
  POST /api/run                     Trigger a manual run
  GET  /api/run/status              Check whether a run is in progress
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import threading
import time
from collections import defaultdict
from pathlib import Path

import yaml

from flask import Flask

from postmule.core.config import ConfigError, load_config

log = logging.getLogger("postmule.web")

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

# Config and data dir are set at startup
_config = None
_config_raw: dict = {}
_config_path: Path | None = None
_data_dir: Path = Path("data")
_enc_path: Path = Path("credentials.enc")

# Pipeline concurrency guard
_pipeline_lock = threading.Lock()
_pipeline_running = False


_MAX_LOGIN_ATTEMPTS = 5
_LOCKOUT_SECONDS = 15 * 60  # 15 minutes
_SESSION_TIMEOUT = 8 * 3600  # 8 hours

# In-memory failed attempt tracking: {ip: [unix_timestamp, ...]}
_failed_attempts: dict[str, list[float]] = defaultdict(list)

_NAV_ITEMS = [
    ("home", "/", "Home"),
    ("mail", "/mail", "Mail"),
    ("bills", "/bills", "Bills"),
    ("forward", "/forward", "Forward To Me"),
    ("pending", "/pending", "Pending"),
    ("entities", "/entities", "Entities"),
    ("corrections", "/corrections", "Corrections"),
    ("settings", "/settings", "Settings"),
    ("logs", "/logs", "Logs"),
    ("connections", "/connections", "Connections"),
]


def create_app(
    config_path: Path | None = None,
    data_dir: Path | None = None,
    enc_path: Path | None = None,
) -> Flask:
    global _config, _config_raw, _config_path, _data_dir, _enc_path
    if config_path:
        _config_path = config_path
        try:
            _config = load_config(config_path)
            with open(config_path, encoding="utf-8") as f:
                _config_raw = yaml.safe_load(f) or {}
        except (ConfigError, Exception):
            pass
    if data_dir:
        _data_dir = data_dir
    if enc_path:
        _enc_path = enc_path
    app.secret_key = _derive_secret_key()

    # Register blueprints — deferred to avoid circular imports at module level.
    # Guard prevents double-registration when create_app() is called multiple times
    # (e.g., in tests).
    if "auth" not in app.blueprints:
        from postmule.web.routes import auth_bp, pages_bp, connections_bp, api_bp
        app.register_blueprint(auth_bp)
        app.register_blueprint(pages_bp)
        app.register_blueprint(connections_bp)
        app.register_blueprint(api_bp)

    return app


# ------------------------------------------------------------------
# Authentication helpers
# ------------------------------------------------------------------

def _dashboard_password() -> str | None:
    """Return configured dashboard password, or None if auth is disabled."""
    return _config and _config.get("dashboard", "password") or None


def _derive_secret_key() -> bytes:
    """Derive a stable Flask secret key from the configured password.

    Using a password-derived key means sessions survive app restarts and
    invalidate automatically when the password changes — both correct behaviors.
    Falls back to a random key when no password is configured (auth disabled).
    """
    pw = _dashboard_password()
    if pw:
        return hashlib.sha256(f"postmule-dashboard:{pw}".encode()).digest()
    return os.urandom(24)


def _is_locked_out(ip: str) -> bool:
    """Return True if the IP has exceeded the failed-attempt limit."""
    now = time.time()
    recent = [t for t in _failed_attempts[ip] if now - t < _LOCKOUT_SECONDS]
    _failed_attempts[ip] = recent
    return len(recent) >= _MAX_LOGIN_ATTEMPTS


def _record_failed_attempt(ip: str) -> None:
    _failed_attempts[ip].append(time.time())


def _clear_attempts(ip: str) -> None:
    _failed_attempts.pop(ip, None)
