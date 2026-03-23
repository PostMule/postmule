"""Pages blueprint — all GET page routes and PDF viewer."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import Blueprint, redirect, render_template, request, url_for

from postmule.data import bills as bills_data
from postmule.data import entities as entity_data
from postmule.data import forward_to_me as ftm_data
from postmule.data import notices as notices_data
from postmule.data import run_log as run_log_data
from postmule.data._io import recent_years

import postmule.web.app as _app

pages_bp = Blueprint("pages", __name__)


@pages_bp.app_context_processor
def inject_nav():
    return {"nav_items": _app._NAV_ITEMS}


@pages_bp.route("/")
def home():
    last_run = run_log_data.get_last_run(_app._data_dir)
    pending_ftm = ftm_data.get_pending_items(_app._data_dir)
    bills_this_year = bills_data.load_bills(_app._data_dir)
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


@pages_bp.route("/mail")
def mail():
    year = request.args.get("year", date.today().year, type=int)
    all_bills = bills_data.load_bills(_app._data_dir, year)
    all_notices = notices_data.load_notices(_app._data_dir, year)
    all_ftm = ftm_data.load_forward_to_me(_app._data_dir)
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


@pages_bp.route("/bills")
def bills():
    year = request.args.get("year", date.today().year, type=int)
    all_bills = bills_data.load_bills(_app._data_dir, year)
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


@pages_bp.route("/forward")
def forward():
    items = ftm_data.load_forward_to_me(_app._data_dir)
    pending = [i for i in items if i.get("forwarding_status") == "pending"]
    return render_template(
        "page.html",
        page="forward",
        title="Forward To Me",
        items=items,
        pending=pending,
        today=date.today().isoformat(),
    )


@pages_bp.route("/pending")
def pending():
    pending_matches = entity_data.load_pending_matches(_app._data_dir)
    pending_only = [m for m in pending_matches if m.get("status") == "pending"]
    return render_template(
        "page.html",
        page="pending",
        title="Pending Reviews",
        pending_matches=pending_only,
        today=date.today().isoformat(),
    )


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


@pages_bp.route("/logs")
def logs():
    lines = _read_log_tail(50)
    return render_template(
        "page.html",
        page="logs",
        title="Logs",
        log_lines=lines,
        today=date.today().isoformat(),
    )


@pages_bp.route("/settings")
def settings():
    saved = request.args.get("saved") == "1"
    cfg = _app._config_raw
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
        config_missing=(_app._config_path is None),
        today=date.today().isoformat(),
    )


@pages_bp.route("/connections")
def connections():
    status = _connection_status()
    return render_template(
        "page.html",
        page="connections",
        title="Connections",
        today=date.today().isoformat(),
        conn=status,
    )


@pages_bp.route("/setup")
def setup():
    return redirect(url_for("pages.connections"))


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

def _connection_status() -> dict:
    """Return live connection status for each service category."""
    from postmule.core.credentials import google_credentials_available
    google_ok = google_credentials_available()
    cfg = _app._config_raw
    mbox_type = ""
    mbox_providers = cfg.get("mailbox", {}).get("providers", [])
    if mbox_providers:
        mbox_type = mbox_providers[0].get("type", "")
    llm_type = ""
    llm_providers = cfg.get("llm", {}).get("providers", [])
    if llm_providers:
        llm_type = llm_providers[0].get("type", "")
    return {
        "google": google_ok,
        "vpm": mbox_type == "vpm",
        "anthropic": llm_type == "anthropic",
        "mbox_type": mbox_type,
        "llm_type": llm_type,
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
