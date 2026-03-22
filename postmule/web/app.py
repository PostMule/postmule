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
  GET  /setup                        First-run setup wizard (single button: Connect Google Account)
  GET  /setup/oauth/google           Start Google OAuth flow (uses baked-in client credentials)
  GET  /setup/oauth/google/callback  OAuth callback — saves refresh token to system keychain
  POST /api/approve                 Approve a pending match
  POST /api/deny                    Deny a pending match
  POST /api/entity/<id>             Update a single entity field (marks user_verified)
  POST /api/entity/<id>/add-account Append an account number to an entity
  POST /api/run                     Trigger a manual run
  GET  /api/run/status              Check whether a run is in progress
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from postmule.core.config import ConfigError, load_config
from postmule.data import bills as bills_data
from postmule.data import entities as entity_data
from postmule.data import forward_to_me as ftm_data
from postmule.data import notices as notices_data
from postmule.data import run_log as run_log_data
from postmule.data._io import recent_years

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
    ("settings", "/settings", "Settings"),
    ("logs", "/logs", "Logs"),
    ("setup", "/setup", "Setup"),
]


@app.context_processor
def inject_nav():
    return {"nav_items": _NAV_ITEMS}


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
    return app


# ------------------------------------------------------------------
# Authentication
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


@app.before_request
def require_auth():
    if request.endpoint in ("login", "logout", "static", "setup_oauth_google_callback"):
        return
    pw = _dashboard_password()
    if not pw:
        return
    if not session.get("authenticated"):
        return redirect(url_for("login"))
    # Enforce session timeout
    if time.time() - session.get("auth_time", 0) > _SESSION_TIMEOUT:
        session.clear()
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        if _is_locked_out(ip):
            error = "Too many failed attempts. Try again in 15 minutes."
        else:
            pw = _dashboard_password()
            submitted = request.form.get("password", "")
            # Constant-time comparison to prevent timing attacks
            if pw and hmac.compare_digest(submitted.encode(), pw.encode()):
                _clear_attempts(ip)
                session["authenticated"] = True
                session["auth_time"] = time.time()
                return redirect(url_for("home"))
            _record_failed_attempt(ip)
            error = "Incorrect password"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------

@app.route("/")
def home():
    last_run = run_log_data.get_last_run(_data_dir)
    pending_ftm = ftm_data.get_pending_items(_data_dir)
    bills_this_year = bills_data.load_bills(_data_dir)
    pending_bills = [b for b in bills_this_year if b.get("status") == "pending"]

    return render_template(
        "page.html",
        page="home",
        title="Home",
        last_run=last_run,
        pending_ftm_count=len(pending_ftm),
        pending_bills_count=len(pending_bills),
        today=date.today().isoformat(),
    )


@app.route("/mail")
def mail():
    year = request.args.get("year", date.today().year, type=int)
    all_bills = bills_data.load_bills(_data_dir, year)
    all_notices = notices_data.load_notices(_data_dir, year)
    all_ftm = ftm_data.load_forward_to_me(_data_dir)

    items = (
        [{"_type": "Bill", **b} for b in all_bills]
        + [{"_type": "Notice", **n} for n in all_notices]
        + [{"_type": "ForwardToMe", **f} for f in all_ftm]
    )
    items.sort(key=lambda x: x.get("date_received", ""), reverse=True)

    return render_template(
        "page.html",
        page="mail",
        title="Mail",
        items=items,
        year=year,
        today=date.today().isoformat(),
    )


@app.route("/bills")
def bills():
    year = request.args.get("year", date.today().year, type=int)
    all_bills = bills_data.load_bills(_data_dir, year)
    pending = [b for b in all_bills if b.get("status") == "pending"]
    return render_template(
        "page.html",
        page="bills",
        title="Bills",
        bills=all_bills,
        pending_bills=pending,
        year=year,
        today=date.today().isoformat(),
    )


@app.route("/forward")
def forward():
    items = ftm_data.load_forward_to_me(_data_dir)
    pending = [i for i in items if i.get("forwarding_status") == "pending"]
    return render_template(
        "page.html",
        page="forward",
        title="Forward To Me",
        items=items,
        pending=pending,
        today=date.today().isoformat(),
    )


@app.route("/pending")
def pending():
    pending_matches = entity_data.load_pending_matches(_data_dir)
    pending_only = [m for m in pending_matches if m.get("status") == "pending"]
    return render_template(
        "page.html",
        page="pending",
        title="Pending Reviews",
        pending_matches=pending_only,
        today=date.today().isoformat(),
    )


@app.route("/entities")
def entities():
    all_entities = entity_data.load_entities(_data_dir)
    return render_template(
        "page.html",
        page="entities",
        title="Entities",
        entities=all_entities,
        entity_categories=entity_data.CATEGORIES,
        today=date.today().isoformat(),
    )


@app.route("/api/entity/<entity_id>", methods=["POST"])
def api_entity_update(entity_id: str):
    """Update a single field on an entity (user edit — marks field as user_verified)."""
    field = request.form.get("field")
    value = request.form.get("value", "")
    if not field:
        return "field is required", 400

    # Coerce types for specific fields
    if field == "account_numbers":
        parsed_value: Any = [v.strip() for v in value.split(",") if v.strip()]
    elif field == "address":
        # Expect sub-field as address_street, address_city, etc.
        parsed_value = {
            k.removeprefix("address_"): request.form.get(k, "") or None
            for k in request.form if k.startswith("address_")
        }
    else:
        parsed_value = value or None

    updated = entity_data.update_entity_field(_data_dir, entity_id, field, parsed_value)
    if updated is None:
        return "Entity not found", 404
    return ("", 200)


@app.route("/api/entity/<entity_id>/add-account", methods=["POST"])
def api_entity_add_account(entity_id: str):
    """Append a single account number to an entity."""
    account = request.form.get("account", "").strip()
    if not account:
        return "account is required", 400
    entities = entity_data.load_entities(_data_dir)
    for e in entities:
        if e["id"] == entity_id:
            if account not in e["account_numbers"]:
                e["account_numbers"].append(account)
            entity_data.save_entities(_data_dir, entities)
            return ("", 200)
    return "Entity not found", 404


@app.route("/logs")
def logs():
    lines = _read_log_tail(50)
    return render_template(
        "page.html",
        page="logs",
        title="Logs",
        log_lines=lines,
        today=date.today().isoformat(),
    )


@app.route("/setup")
def setup():
    google_ok = bool(session.get("setup_google_ok"))
    return render_template(
        "page.html",
        page="setup",
        title="Setup",
        today=date.today().isoformat(),
        google_ok=google_ok,
    )


# ------------------------------------------------------------------
# Setup wizard — Google OAuth flow
# ------------------------------------------------------------------

from postmule.core.constants import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_SCOPES


@app.route("/setup/oauth/google")
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
            "redirect_uris": [url_for("setup_oauth_google_callback", _external=True)],
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=GOOGLE_SCOPES,
        redirect_uri=url_for("setup_oauth_google_callback", _external=True),
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    session["setup_google_oauth_state"] = state
    return redirect(auth_url)


@app.route("/setup/oauth/google/callback")
def setup_oauth_google_callback():
    """Receive the authorization code from Google, exchange for tokens, save refresh token to keychain."""
    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore[import]
    except ImportError:
        return "google-auth-oauthlib not installed", 500

    state = session.get("setup_google_oauth_state")
    if not state:
        return redirect(url_for("setup") + "?error=session_expired")

    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [url_for("setup_oauth_google_callback", _external=True)],
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=GOOGLE_SCOPES,
        state=state,
        redirect_uri=url_for("setup_oauth_google_callback", _external=True),
    )

    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as exc:
        log.error(f"Google OAuth token exchange failed: {exc}")
        return redirect(url_for("setup") + "?error=oauth_failed")

    creds = flow.credentials
    if not creds.refresh_token:
        return redirect(url_for("setup") + "?error=no_refresh_token")

    try:
        from postmule.core.credentials import save_google_refresh_token
        save_google_refresh_token(creds.refresh_token)
    except Exception as exc:
        log.error(f"Failed to save Google refresh token: {exc}")
        return redirect(url_for("setup") + "?error=keychain_save_failed")

    log.info("Google OAuth refresh token saved to system keychain")
    session.pop("setup_google_oauth_state", None)

    return redirect(url_for("setup") + "?google_ok=1")


@app.route("/settings")
def settings():
    saved = request.args.get("saved") == "1"
    cfg = _config_raw

    # Pre-flatten provider lists so the template stays simple
    finance_by_type = {p["type"]: p for p in cfg.get("finance", {}).get("providers", [])}
    email_by_role = {p.get("role", ""): p for p in cfg.get("email", {}).get("providers", [])}
    storage_providers = cfg.get("storage", {}).get("providers", [{}])
    sheet_providers = cfg.get("spreadsheet", {}).get("providers", [{}])
    llm_providers = cfg.get("llm", {}).get("providers", [{}])
    mbox_providers = cfg.get("mailbox", {}).get("providers", [{}])

    return render_template(
        "page.html",
        page="settings",
        title="Settings",
        cfg=cfg,
        finance_by_type=finance_by_type,
        email_by_role=email_by_role,
        storage_cfg=storage_providers[0] if storage_providers else {},
        sheet_cfg=sheet_providers[0] if sheet_providers else {},
        llm_cfg=llm_providers[0] if llm_providers else {},
        mbox_cfg=mbox_providers[0] if mbox_providers else {},
        saved=saved,
        config_missing=(_config_path is None),
        today=date.today().isoformat(),
    )


@app.route("/api/settings", methods=["POST"])
def api_settings():
    global _config_raw
    if _config_path is None:
        return jsonify({"error": "No config file loaded"}), 500

    form = request.form

    def cb(name: str) -> bool:
        return name in form and form[name] in ("on", "true", "1")

    def intv(name: str, default: int = 0) -> int:
        try:
            return int(form.get(name, default))
        except (ValueError, TypeError):
            return default

    def floatv(name: str, default: float = 0.0) -> float:
        try:
            return float(form.get(name, default))
        except (ValueError, TypeError):
            return default

    existing = _config_raw

    # Finance: preserve any extra fields (e.g. Plaid environment) from existing config
    existing_finance_by_type = {
        p["type"]: p for p in existing.get("finance", {}).get("providers", [])
    }

    def _finance_provider(ptype: str, extras: dict | None = None) -> dict:
        base = dict(existing_finance_by_type.get(ptype, {}))
        base["type"] = ptype
        base["enabled"] = cb(f"finance_{ptype}_enabled")
        if extras:
            base.update(extras)
        return base

    new_config = {
        "app": {
            **existing.get("app", {}),
            "dry_run": cb("app_dry_run"),
        },
        "schedule": {
            "run_time": form.get("schedule_run_time", "02:00"),
            "timezone": form.get("schedule_timezone", "America/Los_Angeles"),
        },
        "logging": {
            "verbose_days": intv("logging_verbose_days", 7),
            "processing_years": intv("logging_processing_years", 3),
            "level": form.get("logging_level", "INFO"),
        },
        "notifications": {
            "providers": existing.get("notifications", {}).get(
                "providers", [{"type": "email", "enabled": True}]
            ),
            "alert_email": form.get("notifications_alert_email", ""),
            "forward_to_me_urgent": cb("notifications_forward_to_me_urgent"),
            "bill_due_alert_days": intv("notifications_bill_due_alert_days", 7),
        },
        "mailbox": {
            "providers": [
                {
                    "type": form.get("mailbox_type", "vpm"),
                    "enabled": cb("mailbox_enabled"),
                    "scan_sender": form.get("mailbox_scan_sender", ""),
                    "scan_subject_prefix": form.get("mailbox_scan_subject_prefix", ""),
                }
            ]
        },
        "email": {
            "providers": [
                {
                    "type": form.get("email_mbox_type", "gmail"),
                    "enabled": cb("email_mbox_enabled"),
                    "role": "mailbox_notifications",
                    "address": form.get("email_mbox_address", ""),
                    "label": form.get("email_mbox_label", "PostMule"),
                },
                {
                    "type": form.get("email_bills_type", "gmail"),
                    "enabled": cb("email_bills_enabled"),
                    "role": "bill_intake",
                    "address": form.get("email_bills_address", ""),
                    "label": form.get("email_bills_label", "PostMule-Bills"),
                },
            ]
        },
        "storage": {
            "providers": [
                {
                    "type": form.get("storage_type", "google_drive"),
                    "enabled": True,
                    "root_folder": form.get("storage_root_folder", "PostMule"),
                    "folders": (
                        existing.get("storage", {}).get("providers", [{}])[0].get("folders", {})
                    ),
                }
            ]
        },
        "spreadsheet": {
            "providers": [
                {
                    "type": form.get("spreadsheet_type", "google_sheets"),
                    "enabled": True,
                    "workbook_name": form.get("spreadsheet_workbook_name", "PostMule"),
                    "sheets": (
                        existing.get("spreadsheet", {}).get("providers", [{}])[0].get("sheets", [])
                    ),
                }
            ]
        },
        "llm": {
            "providers": [
                {
                    "type": form.get("llm_type", "gemini"),
                    "enabled": True,
                    "model": form.get("llm_model", "gemini-1.5-flash"),
                }
            ],
            "classification_confidence_threshold": floatv("llm_confidence", 0.80),
        },
        "api_safety": {
            "daily_request_limit": intv("api_daily_req", 1400),
            "daily_token_limit": intv("api_daily_tok", 900000),
            "warn_at_percent": intv("api_warn_pct", 80),
            "monthly_cost_budget_usd": floatv("api_monthly_usd", 0.00),
        },
        "classification": {
            "categories": existing.get("classification", {}).get("categories", []),
            "forward_to_me_keywords": [
                kw.strip()
                for kw in form.get("classification_keywords", "").splitlines()
                if kw.strip()
            ],
        },
        "ocr": {
            "primary": form.get("ocr_primary", "pdfplumber"),
            "fallback": form.get("ocr_fallback", "tesseract"),
            "tesseract_dpi": intv("ocr_dpi", 300),
            "tesseract_lang": form.get("ocr_lang", "eng"),
        },
        "file_naming": {
            "date_format": form.get("fn_date_format", "%Y-%m-%d"),
            "max_sender_length": intv("fn_max_sender", 30),
            "max_recipient_length": intv("fn_max_recipient", 30),
        },
        "entities": {
            "known_names": existing.get("entities", {}).get("known_names", []),
            "fuzzy_match_threshold": floatv("ent_fuzzy", 0.85),
            "auto_approve_after_days": intv("ent_auto_approve", 7),
            "types": existing.get("entities", {}).get("types", []),
        },
        "finance": {
            "providers": [
                _finance_provider("ynab"),
                _finance_provider("plaid", {"environment": form.get("finance_plaid_env", "development")}),
                _finance_provider("simplifi"),
                _finance_provider("monarch"),
            ],
            "bill_matching": {
                "require_manual_approval": cb("finance_require_approval"),
                "amount_tolerance_cents": intv("finance_tolerance_cents", 0),
            },
        },
        "data_protection": {
            "soft_deletes_only": cb("dp_soft_deletes"),
            "trash_retention_days": intv("dp_trash_days", 90),
            "max_files_moved_per_run": intv("dp_max_files", 50),
            "write_verification": cb("dp_write_verify"),
        },
        "backups": {
            "enabled": cb("backups_enabled"),
            "retain_days": intv("backups_retain_days", 180),
            "destination": existing.get("backups", {}).get("destination", "google_drive"),
        },
        "integrity": {
            "run_monitor": cb("int_run_monitor"),
            "gap_detector": {
                "enabled": cb("int_gap_enabled"),
                "run_day": form.get("int_gap_day", "sunday"),
            },
            "integrity_verifier": {
                "enabled": cb("int_verifier_enabled"),
                "run_day": form.get("int_verifier_day", "sunday"),
            },
            "duplicate_detector": {
                "enabled": cb("int_dup_enabled"),
            },
        },
        "credentials": existing.get("credentials", {}),
        "deployment": {
            "dashboard_port": intv("dep_port", 5000),
            "tailscale_enabled": cb("dep_tailscale"),
            "task_scheduler_task_name": form.get("dep_task_name", "PostMule Daily Run"),
        },
    }

    _config_raw = new_config
    with open(_config_path, "w", encoding="utf-8") as f:
        yaml.dump(new_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # Reload parsed config so the live object reflects the saved changes
    try:
        _config = load_config(_config_path)
    except Exception:
        pass

    return redirect(url_for("settings") + "?saved=1")


# ------------------------------------------------------------------
# API endpoints (HTMX)
# ------------------------------------------------------------------

@app.route("/api/approve", methods=["POST"])
def api_approve():
    match_id = request.form.get("match_id")
    if not match_id:
        return jsonify({"error": "match_id required"}), 400

    pending = entity_data.load_pending_matches(_data_dir)
    entities = entity_data.load_entities(_data_dir)

    for match in pending:
        if match["id"] == match_id and match["status"] == "pending":
            match["status"] = "approved"
            for entity in entities:
                if entity["id"] == match["match_entity_id"]:
                    if match["proposed_name"] not in entity["aliases"]:
                        entity["aliases"].append(match["proposed_name"])
                    break
            entity_data.save_pending_matches(_data_dir, pending)
            entity_data.save_entities(_data_dir, entities)
            return ("", 200)

    return jsonify({"error": "match not found"}), 404


@app.route("/api/deny", methods=["POST"])
def api_deny():
    match_id = request.form.get("match_id")
    if not match_id:
        return jsonify({"error": "match_id required"}), 400

    pending = entity_data.load_pending_matches(_data_dir)
    for match in pending:
        if match["id"] == match_id:
            match["status"] = "denied"
            entity_data.save_pending_matches(_data_dir, pending)
            return ("", 200)

    return jsonify({"error": "match not found"}), 404


@app.route("/api/run", methods=["POST"])
def api_run():
    global _pipeline_running
    if _config is None:
        return jsonify({"error": "No config loaded"}), 500

    with _pipeline_lock:
        if _pipeline_running:
            return jsonify({"error": "Pipeline is already running"}), 409
        _pipeline_running = True

    dry_run = request.form.get("dry_run", "false").lower() == "true"

    def _run():
        global _pipeline_running
        from postmule.core.credentials import CredentialsError, load_credentials
        from postmule.pipeline import run_daily_pipeline
        try:
            creds = load_credentials(_enc_path)
            run_daily_pipeline(_config, creds, _data_dir, dry_run=dry_run)
        except CredentialsError as exc:
            log.error(f"Pipeline aborted — credentials error: {exc}")
        except Exception as exc:
            log.error(f"Pipeline run failed: {exc}")
        finally:
            with _pipeline_lock:
                _pipeline_running = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "message": "Run started"})


@app.route("/api/run/status", methods=["GET"])
def api_run_status():
    return jsonify({"running": _pipeline_running})


# ------------------------------------------------------------------
# PDF viewer
# ------------------------------------------------------------------

def _find_mail_item(mail_id: str) -> dict | None:
    """Find any mail item by ID across bills, notices, and forward-to-me records."""
    for year in recent_years():
        for bill in bills_data.load_bills(_data_dir, year):
            if bill.get("id") == mail_id:
                return bill
        for notice in notices_data.load_notices(_data_dir, year):
            if notice.get("id") == mail_id:
                return notice
    for ftm in ftm_data.load_forward_to_me(_data_dir):
        if ftm.get("id") == mail_id:
            return ftm
    return None


@app.route("/pdf/<mail_id>")
def view_pdf(mail_id: str):
    item = _find_mail_item(mail_id)
    if not item:
        return "Mail item not found", 404
    drive_file_id = item.get("drive_file_id")
    if not drive_file_id:
        return "No PDF stored for this item", 404
    return redirect(f"https://drive.google.com/file/d/{drive_file_id}/view")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _read_log_tail(lines: int) -> list[str]:
    today = date.today().isoformat()
    candidates = [
        _data_dir.parent / "logs" / "verbose" / f"{today}.log",
        Path("logs") / "verbose" / f"{today}.log",
    ]
    for path in candidates:
        if path.exists():
            with path.open("r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            return [l.rstrip() for l in all_lines[-lines:]]
    return [f"No log file found for {today}"]


