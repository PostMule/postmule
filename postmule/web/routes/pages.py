"""Pages blueprint — all GET page routes and PDF viewer."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import Blueprint, redirect, render_template, request, url_for

from postmule.data import bills as bills_data
from postmule.data import entities as entity_data
from postmule.data import entity_corrections as corrections_data
from postmule.data import forward_to_me as ftm_data
from postmule.data import notices as notices_data
from postmule.data import run_log as run_log_data
from postmule.data._io import recent_years

import postmule.web.app as _app

pages_bp = Blueprint("pages", __name__)


@pages_bp.app_context_processor
def inject_nav():
    from postmule import __version__
    update_check_enabled = _app._config_raw.get("deployment", {}).get("update_check_enabled", True)
    return {
        "nav_items": _app._NAV_ITEMS,
        "app_version": __version__,
        "update_check_enabled": update_check_enabled,
    }


@pages_bp.route("/home")
def home():
    return redirect(url_for("pages.mail"))


@pages_bp.route("/")
@pages_bp.route("/mail")
def mail():
    year = request.args.get("year", date.today().year, type=int)
    initial_tab = request.args.get("tab", "all")
    all_bills = bills_data.load_bills(_app._data_dir, year)
    all_notices = notices_data.load_notices(_app._data_dir, year)
    all_ftm = ftm_data.load_forward_to_me(_app._data_dir)

    last_run = run_log_data.get_last_run(_app._data_dir)
    pending_ftm_count = len([f for f in all_ftm if f.get("forwarding_status") == "pending"])
    pending_bills_count = len([b for b in all_bills if b.get("status") == "pending"])

    all_pending_matches = entity_data.load_pending_matches(_app._data_dir)
    pending_matches = [m for m in all_pending_matches if m.get("status") == "pending"]
    pending_by_sender = {m.get("proposed_name", "").lower(): m for m in pending_matches}

    items = (
        [{"_type": "Bill", **b} for b in all_bills]
        + [{"_type": "Notice", **n} for n in all_notices]
        + [{"_type": "ForwardToMe", **f} for f in all_ftm]
    )
    items.sort(key=lambda x: x.get("date_received", ""), reverse=True)
    all_entities = entity_data.load_entities(_app._data_dir)
    return render_template(
        "page.html",
        page="mail",
        title="Mail",
        items=items,
        year=year,
        entities=all_entities,
        last_run=last_run,
        pending_ftm_count=pending_ftm_count,
        pending_bills_count=pending_bills_count,
        pending_matches=pending_matches,
        pending_by_sender=pending_by_sender,
        initial_tab=initial_tab,
        today=date.today().isoformat(),
    )


@pages_bp.route("/bills")
def bills():
    return redirect(url_for("pages.mail", tab="bills"))


@pages_bp.route("/forward")
def forward():
    return redirect(url_for("pages.mail", tab="forward"))


@pages_bp.route("/pending")
def pending():
    return redirect(url_for("pages.mail", tab="unassigned"))


@pages_bp.route("/entities")
def entities():
    all_entities = entity_data.load_entities(_app._data_dir)
    return render_template(
        "page.html",
        page="entities",
        title="Entities",
        entities=all_entities,
        entity_categories=entity_data.CATEGORIES,
        today=date.today().isoformat(),
    )


@pages_bp.route("/corrections")
def corrections():
    from flask import redirect as _redirect, url_for as _url_for
    return _redirect(_url_for("pages.logs"))


@pages_bp.route("/logs")
def logs():
    lines = _read_log_tail(50)
    correction_summary = corrections_data.correction_summary(_app._data_dir)
    return render_template(
        "page.html",
        page="logs",
        title="Logs",
        log_lines=lines,
        correction_summary=correction_summary,
        today=date.today().isoformat(),
    )


@pages_bp.route("/settings")
def settings():
    saved = request.args.get("saved") == "1"
    cfg = _app._config_raw
    finance_by_type = {p.get("service", ""): p for p in cfg.get("finance", {}).get("providers", [])}
    email_by_role = {p.get("role", ""): p for p in cfg.get("email", {}).get("providers", [])}
    storage_providers = cfg.get("storage", {}).get("providers", [{}])
    sheet_providers = cfg.get("spreadsheet", {}).get("providers", [{}])
    llm_providers = cfg.get("llm", {}).get("providers", [{}])
    mbox_providers = cfg.get("mailbox", {}).get("providers", [{}])
    from postmule.agents.backup import get_last_backup
    last_backup = get_last_backup(_app._data_dir) if _app._data_dir else None
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
        config_missing=(_app._config_path is None),
        today=date.today().isoformat(),
        last_backup=last_backup,
    )


@pages_bp.route("/providers")
def providers():
    status = _connection_status()
    return render_template(
        "page.html",
        page="providers",
        title="Providers",
        today=date.today().isoformat(),
        conn=status,
    )


@pages_bp.route("/connections")
def connections_redirect():
    return redirect(url_for("pages.providers"), code=301)


@pages_bp.route("/setup")
def setup():
    return redirect(url_for("pages.providers"))


@pages_bp.route("/pdf/<mail_id>")
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

def _cred_get(*keys: str) -> str | None:
    """Read a nested key from credentials.enc; returns None on any error."""
    try:
        from postmule.core.credentials import load_credentials
        creds = load_credentials(_app._enc_path)
        node = creds
        for k in keys:
            if not isinstance(node, dict):
                return None
            node = node.get(k)
        return str(node) if node else None
    except Exception:
        return None


def _connection_status() -> dict:
    """Return live connection status for each service category."""
    from postmule.core.credentials import google_credentials_available
    google_ok = google_credentials_available()
    cfg = _app._config_raw

    # mailbox
    mbox_providers = cfg.get("mailbox", {}).get("providers", [])
    mbox_type = mbox_providers[0].get("service", "") if mbox_providers else ""
    vpm_creds_ok = (
        bool(_cred_get("vpm", "username")) and bool(_cred_get("vpm", "password"))
    ) if mbox_type == "vpm" else False

    # email
    email_providers = cfg.get("email", {}).get("providers", [])
    email_type = ""
    email_address = ""
    if email_providers:
        ep = email_providers[0]
        email_type = ep.get("service", "")
        email_address = ep.get("address", "") or ep.get("username", "")

    # storage
    storage_providers = cfg.get("storage", {}).get("providers", [])
    storage_type = ""
    storage_root = ""
    if storage_providers:
        sp = storage_providers[0]
        storage_type = sp.get("service", "")
        storage_root = sp.get("root_folder", "") or sp.get("bucket", "")

    # spreadsheet
    sheet_providers = cfg.get("spreadsheet", {}).get("providers", [])
    sheet_type = ""
    sheet_name = ""
    if sheet_providers:
        shp = sheet_providers[0]
        sheet_type = shp.get("service", "")
        sheet_name = shp.get("workbook_name", "") or shp.get("spreadsheet_name", "")

    # LLM
    llm_providers = cfg.get("llm", {}).get("providers", [])
    llm_type = ""
    llm_model = ""
    if llm_providers:
        lp = llm_providers[0]
        llm_type = lp.get("service", "")
        llm_model = lp.get("model", "")
    anthropic_key = _cred_get("anthropic", "api_key")
    openai_key = _cred_get("openai", "api_key")

    # finance
    finance_providers = cfg.get("finance", {}).get("providers", [])
    finance_type = finance_providers[0].get("service", "") if finance_providers else ""
    ynab_token = _cred_get("ynab", "access_token")
    ynab_budget = _cred_get("ynab", "budget_id")

    # notifications
    alert_email = cfg.get("notifications", {}).get("alert_email", "")
    alert_email_secondary = cfg.get("notifications", {}).get("alert_email_secondary", "")

    return {
        # Legacy flat keys kept for backward compat
        "google": google_ok,
        "vpm": mbox_type == "vpm",
        "anthropic": llm_type == "anthropic",
        "mbox_type": mbox_type,
        "llm_type": llm_type,
        # Per-category dicts
        "email": {
            "type": email_type,
            "address": email_address,
            "enabled": bool(email_type),
        },
        "storage": {
            "type": storage_type,
            "root_folder": storage_root,
        },
        "spreadsheet": {
            "type": sheet_type,
            "workbook_name": sheet_name,
        },
        "mailbox": {
            "type": mbox_type,
            "enabled": bool(mbox_type),
            "creds_ok": vpm_creds_ok if mbox_type == "vpm" else bool(mbox_type),
        },
        "llm": {
            "type": llm_type,
            "model": llm_model,
            "anthropic_key": anthropic_key,
            "openai_key": openai_key,
        },
        "finance": {
            "type": finance_type,
            "ynab_ok": bool(ynab_token) and bool(ynab_budget),
            "ynab_token": ynab_token,
            "ynab_budget": ynab_budget,
        },
        "notifications": {
            "alert_email": alert_email,
            "alert_email_secondary": alert_email_secondary,
        },
    }


def _find_mail_item(mail_id: str) -> dict | None:
    """Find any mail item by ID across bills, notices, and forward-to-me records."""
    for year in recent_years():
        for bill in bills_data.load_bills(_app._data_dir, year):
            if bill.get("id") == mail_id:
                return bill
        for notice in notices_data.load_notices(_app._data_dir, year):
            if notice.get("id") == mail_id:
                return notice
    for ftm in ftm_data.load_forward_to_me(_app._data_dir):
        if ftm.get("id") == mail_id:
            return ftm
    return None


def _read_log_tail(lines: int) -> list[str]:
    today = date.today().isoformat()
    candidates = [
        _app._data_dir.parent / "logs" / "verbose" / f"{today}.log",
        Path("logs") / "verbose" / f"{today}.log",
    ]
    for path in candidates:
        if path.exists():
            with path.open("r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            return [line.rstrip() for line in all_lines[-lines:]]
    return [f"No log file found for {today}"]
