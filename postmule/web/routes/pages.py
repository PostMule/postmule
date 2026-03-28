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
from postmule.data.entities import find_entity_by_account, mask_account_number
from postmule.data import owners as owners_data

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
    initial_tab = request.args.get("tab", "all")
    year = date.today().year
    all_bills = [b for b in bills_data.load_bills(_app._data_dir, year) if not b.get("filed", False)]
    all_notices = [n for n in notices_data.load_notices(_app._data_dir, year) if not n.get("filed", False)]
    all_ftm = [f for f in ftm_data.load_forward_to_me(_app._data_dir) if not f.get("filed", False)]

    last_run = run_log_data.get_last_run(_app._data_dir)
    pending_ftm_count = len([f for f in all_ftm if f.get("forwarding_status") == "pending"])
    pending_bills_count = len([b for b in all_bills if b.get("status") == "pending"])

    all_pending_matches = entity_data.load_pending_matches(_app._data_dir)
    pending_matches = [m for m in all_pending_matches if m.get("status") == "pending"]
    pending_by_sender = {m.get("proposed_name", "").lower(): m for m in pending_matches}

    items = (
        [{"_type": b.get("category_override", "Bill"), **b} for b in all_bills]
        + [{"_type": n.get("category_override", "Notice"), **n} for n in all_notices]
        + [{"_type": f.get("category_override", "ForwardToMe"), **f} for f in all_ftm]
    )
    items.sort(key=lambda x: x.get("date_received", ""), reverse=True)
    all_entities = entity_data.load_entities(_app._data_dir)
    return render_template(
        "page.html",
        page="mail",
        title="Mail",
        items=items,
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


@pages_bp.route("/reports")
def reports():
    from postmule.data.search import search_mail

    types_raw = request.args.getlist("type")
    entity_id = request.args.get("entity_id") or None
    owner_id = request.args.get("owner_id") or None
    lifecycle = request.args.get("lifecycle", "all")
    q = request.args.get("q") or None
    date_from = request.args.get("date_from") or None
    date_to = request.args.get("date_to") or None

    results = search_mail(
        _app._data_dir,
        types=types_raw or None,
        entity_id=entity_id,
        owner_id=owner_id,
        lifecycle=lifecycle,
        q=q,
        date_from=date_from,
        date_to=date_to,
    )
    all_entities = entity_data.load_entities(_app._data_dir)
    all_owners = owners_data.load_owners(_app._data_dir)

    return render_template(
        "page.html",
        page="reports",
        title="Reports",
        items=results,
        entities=all_entities,
        owners=all_owners,
        f_types=types_raw,
        f_entity_id=entity_id or "",
        f_owner_id=owner_id or "",
        f_lifecycle=lifecycle,
        f_q=q or "",
        f_date_from=date_from or "",
        f_date_to=date_to or "",
        today=date.today().isoformat(),
    )


def _last_payment_display(date_str: str, amount) -> str:
    """Format '2026-03-18' + 94.0 as 'Mar 18 · $94.00'."""
    import calendar as _cal
    try:
        parts = date_str.split("-")
        abbr = _cal.month_abbr[int(parts[1])]
        return f"{abbr} {int(parts[2])} · ${float(amount):.2f}"
    except Exception:
        return ""


def _compute_last_payments(data_dir, entities: list) -> dict:
    """Return dict[entity_id -> display_str] for the most recent matched bill per entity."""
    recent: dict = {}  # entity_id -> (date_str, amount)
    for year in recent_years(2):
        for bill in bills_data.load_bills(data_dir, year):
            if bill.get("status") != "matched":
                continue
            eid = bill.get("entity_override_id")
            if not eid and bill.get("account_number"):
                match = find_entity_by_account(entities, bill["account_number"])
                if match:
                    eid = match["id"]
            if not eid:
                continue
            date_str = bill.get("date_received", "")
            amount = bill.get("amount_due")
            if amount is None:
                continue
            prev = recent.get(eid)
            if not prev or date_str > prev[0]:
                recent[eid] = (date_str, amount)
    return {eid: _last_payment_display(d, a) for eid, (d, a) in recent.items()}


@pages_bp.route("/entities")
def entities():
    all_entities = entity_data.load_entities(_app._data_dir)
    last_payments = _compute_last_payments(_app._data_dir, all_entities)
    for e in all_entities:
        e["_masked_account"] = mask_account_number(e.get("account_number") or "")
        e["_last_payment"] = last_payments.get(e["id"], "")
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


@pages_bp.route("/help")
def help_overview():
    return render_template(
        "page.html",
        page="help",
        title="Help",
        today=date.today().isoformat(),
        help_section="overview",
    )


@pages_bp.route("/help/installation")
def help_installation():
    return render_template(
        "page.html",
        page="help",
        title="Help — Installation",
        today=date.today().isoformat(),
        help_section="installation",
    )


@pages_bp.route("/help/configuration")
def help_configuration():
    return render_template(
        "page.html",
        page="help",
        title="Help — Configuration",
        today=date.today().isoformat(),
        help_section="configuration",
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
    ep0 = email_providers[0] if email_providers else {}
    if email_providers:
        ep = email_providers[0]
        email_type = ep.get("service", "")
        email_address = ep.get("address", "") or ep.get("username", "")
    imap_creds_ok = bool(_cred_get("imap", "username")) and bool(_cred_get("imap", "password"))
    proton_creds_ok = bool(_cred_get("proton", "username")) and bool(_cred_get("proton", "password"))
    outlook_365_token = _cred_get("outlook_365", "access_token")
    outlook_com_token = _cred_get("outlook_com", "access_token")

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
    ollama_host = (llm_providers[0].get("host", "http://localhost:11434") if llm_providers else "http://localhost:11434")

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
            "label_name": ep0.get("label_name", "PostMule"),
            # IMAP
            "imap_creds_ok": imap_creds_ok,
            "imap_host": ep0.get("host", "") if email_type == "imap" else "",
            "imap_port": ep0.get("port", 993) if email_type == "imap" else 993,
            "imap_ssl": ep0.get("use_ssl", True) if email_type == "imap" else True,
            "imap_processed_folder": ep0.get("processed_folder", "PostMule") if email_type == "imap" else "PostMule",
            # Proton
            "proton_creds_ok": proton_creds_ok,
            "proton_bridge_host": ep0.get("bridge_host", "127.0.0.1") if email_type == "proton" else "127.0.0.1",
            "proton_bridge_port": ep0.get("bridge_port", 1143) if email_type == "proton" else 1143,
            # Outlook
            "outlook_365_token": outlook_365_token,
            "outlook_com_token": outlook_com_token,
            "outlook_processed_category": ep0.get("processed_category", "PostMule"),
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
            "ollama_host": ollama_host,
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
