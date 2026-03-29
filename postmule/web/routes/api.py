"""API blueprint — HTMX/JSON endpoints."""

from __future__ import annotations

import csv
import io
import json
import logging
import threading
from typing import Any

import yaml

from flask import Blueprint, Response, jsonify, redirect, request, url_for

from postmule.core.config import load_config
from postmule.data import bills as bills_data
from postmule.data import entity_corrections as corrections_data
from postmule.data import entities as entity_data
from postmule.data import forward_to_me as ftm_data
from postmule.data import notices as notices_data
from postmule.data import owners as owners_data
from postmule.data import tags as tags_data

import postmule.web.app as _app

log = logging.getLogger("postmule.web")

api_bp = Blueprint("api", __name__)


@api_bp.route("/api/approve", methods=["POST"])
def api_approve():
    match_id = request.form.get("match_id")
    if not match_id:
        return jsonify({"error": "match_id required"}), 400

    # Optional override: assign alias to a different entity than the proposed one
    override_entity_id = request.form.get("entity_id", "").strip() or None

    pending = entity_data.load_pending_matches(_app._data_dir)
    entities = entity_data.load_entities(_app._data_dir)

    for match in pending:
        if match["id"] == match_id and match["status"] == "pending":
            match["status"] = "approved"
            target_entity_id = override_entity_id or match["match_entity_id"]
            for entity in entities:
                if entity["id"] == target_entity_id:
                    if match["proposed_name"] not in entity["aliases"]:
                        entity["aliases"].append(match["proposed_name"])
                    break
            entity_data.save_pending_matches(_app._data_dir, pending)
            entity_data.save_entities(_app._data_dir, entities)
            return ("", 200)

    return jsonify({"error": "match not found"}), 404


@api_bp.route("/api/deny", methods=["POST"])
def api_deny():
    match_id = request.form.get("match_id")
    if not match_id:
        return jsonify({"error": "match_id required"}), 400

    pending = entity_data.load_pending_matches(_app._data_dir)
    for match in pending:
        if match["id"] == match_id:
            match["status"] = "denied"
            entity_data.save_pending_matches(_app._data_dir, pending)
            return ("", 200)

    return jsonify({"error": "match not found"}), 404


@api_bp.route("/api/run", methods=["POST"])
def api_run():
    if _app._config is None:
        return jsonify({"error": "No config loaded"}), 500

    with _app._pipeline_lock:
        if _app._pipeline_running:
            return jsonify({"error": "Pipeline is already running"}), 409
        _app._pipeline_running = True

    dry_run = request.form.get("dry_run", "false").lower() == "true"

    def _run():
        from postmule.core.credentials import CredentialsError, load_credentials
        from postmule.pipeline import run_daily_pipeline
        try:
            creds = load_credentials(_app._enc_path)
            run_daily_pipeline(_app._config, creds, _app._data_dir, dry_run=dry_run)
        except CredentialsError as exc:
            log.error(f"Pipeline aborted — credentials error: {exc}")
        except Exception as exc:
            log.error(f"Pipeline run failed: {exc}")
        finally:
            with _app._pipeline_lock:
                _app._pipeline_running = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "message": "Run started"})


@api_bp.route("/api/run/status", methods=["GET"])
def api_run_status():
    return jsonify({"running": _app._pipeline_running})


@api_bp.route("/api/settings", methods=["POST"])
def api_settings():
    if _app._config_path is None:
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

    existing = _app._config_raw
    existing_finance_by_type = {
        p.get("service", ""): p for p in existing.get("finance", {}).get("providers", [])
    }

    def _finance_provider(ptype: str, extras: dict | None = None) -> dict:
        base = dict(existing_finance_by_type.get(ptype, {}))
        base["service"] = ptype
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
                "providers", [{"service": "email", "enabled": True}]
            ),
            "alert_email": form.get("notifications_alert_email", ""),
            "alert_email_secondary": form.get("notifications_alert_email_secondary", ""),
            "forward_to_me_urgent": cb("notifications_forward_to_me_urgent"),
            "bill_due_alert_days": intv("notifications_bill_due_alert_days", 7),
        },
        "mailbox": {
            "providers": [
                {
                    "service": form.get("mailbox_type", "vpm"),
                    "enabled": cb("mailbox_enabled"),
                    "scan_sender": form.get("mailbox_scan_sender", ""),
                    "scan_subject_prefix": form.get("mailbox_scan_subject_prefix", ""),
                }
            ]
        },
        "email": {
            "providers": existing.get("email", {}).get("providers", []),
        },
        "storage": {
            "providers": [
                {
                    "service": form.get("storage_type", "google_drive"),
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
                    "service": form.get("spreadsheet_type", "google_sheets"),
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
                    "service": form.get("llm_type", "gemini"),
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
            "update_check_enabled": cb("dep_update_check"),
        },
    }

    _app._config_raw = new_config
    with open(_app._config_path, "w", encoding="utf-8") as f:
        yaml.dump(new_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    try:
        _app._config = load_config(_app._config_path)
    except Exception:
        pass

    return redirect(url_for("pages.settings") + "?saved=1")


@api_bp.route("/api/entity/<entity_id>", methods=["POST"])
def api_entity_update(entity_id: str):
    """Update a single field on an entity (user edit — marks field as user_verified)."""
    field = request.form.get("field")
    value = request.form.get("value", "")
    if not field:
        return "field is required", 400

    if field == "friendly_name":
        friendly = (value or "").strip()
        if not friendly:
            return "friendly_name cannot be empty", 400
        entities = entity_data.load_entities(_app._data_dir)
        if not entity_data.validate_friendly_name_unique(entities, friendly, exclude_id=entity_id):
            return jsonify({"error": "friendly_name_taken",
                            "message": f"'{friendly}' is already used by another entity."}), 409
        parsed_value: Any = friendly
    elif field == "address":
        parsed_value = {
            k.removeprefix("address_"): request.form.get(k, "") or None
            for k in request.form if k.startswith("address_")
        }
    else:
        parsed_value = value or None

    updated = entity_data.update_entity_field(_app._data_dir, entity_id, field, parsed_value)
    if updated is None:
        return "Entity not found", 404
    return ("", 200)


@api_bp.route("/api/mail/<mail_id>/entity", methods=["POST"])
def api_mail_entity_override(mail_id: str):
    """Override the entity association for a mail item and log the correction."""
    entity_id = request.form.get("entity_id", "").strip()
    add_alias = request.form.get("add_alias", "false").lower() == "true"
    if not entity_id:
        return jsonify({"error": "entity_id required"}), 400

    # Locate the mail item and determine its type
    mail_item = None
    mail_type = None
    from postmule.data._io import recent_years
    for year in recent_years():
        for bill in bills_data.load_bills(_app._data_dir, year):
            if bill.get("id") == mail_id:
                mail_item = bill
                mail_type = "Bill"
                break
        if mail_item:
            break
        for notice in notices_data.load_notices(_app._data_dir, year):
            if notice.get("id") == mail_id:
                mail_item = notice
                mail_type = "Notice"
                break
        if mail_item:
            break
    if not mail_item:
        for ftm in ftm_data.load_forward_to_me(_app._data_dir):
            if ftm.get("id") == mail_id:
                mail_item = ftm
                mail_type = "ForwardToMe"
                break

    if not mail_item or not mail_type:
        return jsonify({"error": "Mail item not found"}), 404

    # Locate the target entity
    entities = entity_data.load_entities(_app._data_dir)
    target_entity = next((e for e in entities if e["id"] == entity_id), None)
    if not target_entity:
        return jsonify({"error": "Entity not found"}), 404

    original_sender = mail_item.get("sender", "")

    # Apply the override to the record
    if mail_type == "Bill":
        bills_data.set_entity_override(_app._data_dir, mail_id, entity_id)
    elif mail_type == "Notice":
        notices_data.set_entity_override(_app._data_dir, mail_id, entity_id)
    else:
        ftm_data.set_entity_override(_app._data_dir, mail_id, entity_id)

    # Optionally add original sender as an alias on the target entity
    if add_alias and original_sender:
        if original_sender not in target_entity["aliases"]:
            target_entity["aliases"].append(original_sender)
            entity_data.save_entities(_app._data_dir, entities)

    # Log the correction for developer review
    corrections_data.log_correction(
        _app._data_dir,
        mail_id=mail_id,
        mail_type=mail_type,
        original_sender=original_sender,
        corrected_entity_id=entity_id,
        corrected_entity_name=target_entity["canonical_name"],
        added_alias=add_alias and bool(original_sender),
    )

    return ("", 200)


def _find_mail_type(mail_id: str, data_dir) -> str | None:
    """Return 'bill', 'notice', or 'ftm' for the given mail_id, or None if not found."""
    from postmule.data._io import recent_years
    for year in recent_years():
        for bill in bills_data.load_bills(data_dir, year):
            if bill.get("id") == mail_id:
                return "bill"
        for notice in notices_data.load_notices(data_dir, year):
            if notice.get("id") == mail_id:
                return "notice"
    for ftm in ftm_data.load_forward_to_me(data_dir):
        if ftm.get("id") == mail_id:
            return "ftm"
    return None


def _set_filed(mail_id: str, data_dir, filed: bool) -> bool:
    """Set filed state on whichever mail type owns mail_id. Returns True if found."""
    mail_type = _find_mail_type(mail_id, data_dir)
    if mail_type == "bill":
        return bills_data.set_filed(data_dir, mail_id, filed)
    if mail_type == "notice":
        return notices_data.set_filed(data_dir, mail_id, filed)
    if mail_type == "ftm":
        return ftm_data.set_filed(data_dir, mail_id, filed)
    return False


@api_bp.route("/api/mail/<mail_id>/file", methods=["POST"])
def api_mail_file(mail_id: str):
    """Mark a mail item as filed (hidden from main mail view)."""
    if _app._config and _app._config.get("app", {}).get("dry_run"):
        return jsonify({"ok": True, "dry_run": True})
    if _set_filed(mail_id, _app._data_dir, True):
        return ("", 200)
    return jsonify({"error": "Mail item not found"}), 404


@api_bp.route("/api/mail/<mail_id>/unfile", methods=["POST"])
def api_mail_unfile(mail_id: str):
    """Return a filed mail item to Open (visible in main mail view)."""
    if _app._config and _app._config.get("app", {}).get("dry_run"):
        return jsonify({"ok": True, "dry_run": True})
    if _set_filed(mail_id, _app._data_dir, False):
        return ("", 200)
    return jsonify({"error": "Mail item not found"}), 404


_VALID_CATEGORIES = {"Bill", "Notice", "ForwardToMe", "Personal", "Junk", "NeedsReview"}


@api_bp.route("/api/mail/<mail_id>/category", methods=["POST"])
def api_mail_category(mail_id: str):
    """Override the category (type) of a mail item."""
    if _app._config and _app._config.get("app", {}).get("dry_run"):
        return jsonify({"ok": True, "dry_run": True})

    category = request.form.get("category", "").strip()
    if category not in _VALID_CATEGORIES:
        return jsonify({"error": f"Invalid category; must be one of {sorted(_VALID_CATEGORIES)}"}), 400

    from postmule.data._io import recent_years
    for year in recent_years():
        for bill in bills_data.load_bills(_app._data_dir, year):
            if bill.get("id") == mail_id:
                bills_data.set_category_override(_app._data_dir, mail_id, category)
                return ("", 200)
        for notice in notices_data.load_notices(_app._data_dir, year):
            if notice.get("id") == mail_id:
                notices_data.set_category_override(_app._data_dir, mail_id, category)
                return ("", 200)
    for ftm in ftm_data.load_forward_to_me(_app._data_dir):
        if ftm.get("id") == mail_id:
            ftm_data.set_category_override(_app._data_dir, mail_id, category)
            return ("", 200)

    return jsonify({"error": "Mail item not found"}), 404


@api_bp.route("/api/tags", methods=["GET"])
def api_tags():
    """Return all known tags from the registry."""
    return jsonify(tags_data.load_tags(_app._data_dir))


@api_bp.route("/api/mail/<mail_id>/tag", methods=["POST"])
def api_mail_tag(mail_id: str):
    """Add or remove a tag on a mail item."""
    action = request.form.get("action", "").strip()
    tag = request.form.get("value", "").strip()
    if action not in ("add", "remove") or not tag:
        return jsonify({"error": "action (add|remove) and value are required"}), 400

    found = (
        bills_data.update_tags(_app._data_dir, mail_id, tag, action)
        or notices_data.update_tags(_app._data_dir, mail_id, tag, action)
        or ftm_data.update_tags(_app._data_dir, mail_id, tag, action)
    )
    if not found:
        return jsonify({"error": "Mail item not found"}), 404

    if action == "add":
        tags_data.add_to_registry(_app._data_dir, tag)

    return ("", 200)


@api_bp.route("/api/entity/<entity_id>/add-account", methods=["POST"])
def api_entity_add_account(entity_id: str):
    """Set the account number on an entity (one per entity)."""
    account = request.form.get("account", "").strip()
    if not account:
        return "account is required", 400
    updated = entity_data.update_entity_field(_app._data_dir, entity_id, "account_number", account)
    if updated is None:
        return "Entity not found", 404
    return ("", 200)


@api_bp.route("/api/entity/<entity_id>/save", methods=["POST"])
def api_entity_save(entity_id: str):
    """Batch save editable fields on an entity from the detail panel."""
    entities = entity_data.load_entities(_app._data_dir)
    entity = next((e for e in entities if e["id"] == entity_id), None)
    if entity is None:
        return jsonify({"error": "not_found"}), 404

    friendly = request.form.get("friendly_name", "").strip()
    if not friendly:
        return jsonify({"error": "empty_friendly_name", "message": "Friendly name cannot be empty."}), 400
    if not entity_data.validate_friendly_name_unique(entities, friendly, exclude_id=entity_id):
        return jsonify({"error": "friendly_name_taken",
                        "message": f"'{friendly}' is already used by another entity."}), 409

    entity["friendly_name"] = friendly
    for field in ("account_number", "category", "phone", "website", "payment_address"):
        val = request.form.get(field)
        if val is not None:
            entity[field] = val.strip() or None
            verified = entity.setdefault("user_verified_fields", [])
            if field not in verified:
                verified.append(field)

    verified = entity.setdefault("user_verified_fields", [])
    if "friendly_name" not in verified:
        verified.append("friendly_name")

    entity_data.save_entities(_app._data_dir, entities)
    return jsonify({"ok": True})


@api_bp.route("/api/entity/create", methods=["POST"])
def api_entity_create():
    """Create a new entity inline (typically pre-filled from OCR data on a mail item)."""
    name = (request.form.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    category = (request.form.get("category") or "biller").strip()
    friendly_name = (request.form.get("friendly_name") or name).strip()
    account_number = (request.form.get("account_number") or "").strip() or None

    entities = entity_data.load_entities(_app._data_dir)
    if not entity_data.validate_friendly_name_unique(entities, friendly_name):
        return jsonify({"error": "friendly_name_taken",
                        "message": f"'{friendly_name}' is already used by another entity."}), 409

    entity = entity_data.add_entity(
        _app._data_dir, name, category,
        friendly_name=friendly_name, account_number=account_number,
    )
    return jsonify({"id": entity["id"], "canonical_name": entity["canonical_name"],
                    "friendly_name": entity["friendly_name"]})


@api_bp.route("/api/entity/<entity_id>/alias", methods=["POST"])
def api_entity_alias(entity_id: str):
    """Add or remove an alias on an entity."""
    action = request.form.get("action")
    value = (request.form.get("value") or "").strip()
    if action not in ("add", "remove") or not value:
        return "action and value are required", 400
    entities = entity_data.load_entities(_app._data_dir)
    entity = next((e for e in entities if e["id"] == entity_id), None)
    if entity is None:
        return "Entity not found", 404
    aliases = entity.setdefault("aliases", [])
    if action == "add" and value not in aliases:
        aliases.append(value)
    elif action == "remove" and value in aliases:
        aliases.remove(value)
    entity_data.save_entities(_app._data_dir, entities)
    return ("", 200)


@api_bp.route("/api/backup", methods=["POST"])
def api_backup():
    """Trigger an on-demand backup upload to cloud storage."""
    if _app._config is None:
        return jsonify({"error": "No config loaded"}), 500

    dry_run = request.form.get("dry_run", "false").lower() == "true"

    from postmule.agents.backup import run_backup
    from postmule.core.credentials import CredentialsError, load_credentials

    try:
        credentials = load_credentials(_app._enc_path)
    except CredentialsError:
        credentials = {}

    config_path = _app._config_path
    enc_path = _app._enc_path

    result = run_backup(
        _app._config,
        credentials,
        _app._data_dir,
        config_path,
        enc_path,
        dry_run=dry_run,
    )
    status_code = 200 if result["status"] == "ok" else 500
    return jsonify(result), status_code


@api_bp.route("/api/backups", methods=["GET"])
def api_list_backups():
    """List available backups in cloud storage."""
    if _app._config is None:
        return jsonify({"error": "No config loaded"}), 500

    from postmule.agents.backup import get_last_backup, list_backups
    from postmule.core.credentials import CredentialsError, load_credentials

    try:
        credentials = load_credentials(_app._enc_path)
    except CredentialsError:
        credentials = {}

    backups = list_backups(_app._config, credentials)
    last = get_last_backup(_app._data_dir)
    return jsonify({"backups": backups, "last_backup": last})


@api_bp.route("/api/export", methods=["GET"])
def api_export():
    """Export PostMule data as CSV or JSON.

    Query params:
        format:    "csv" or "json" (default: "json")
        type:      "bills", "notices", "entities", or "all" (default: "all")
        from_date: YYYY-MM-DD — only include records on/after this date (optional)
        to_date:   YYYY-MM-DD — only include records on/before this date (optional)
    """
    from postmule.data._io import recent_years

    fmt = request.args.get("format", "json").lower()
    data_type = request.args.get("type", "all").lower()
    from_date = request.args.get("from_date", "")
    to_date = request.args.get("to_date", "")

    if fmt not in ("csv", "json"):
        return jsonify({"error": "format must be csv or json"}), 400
    if data_type not in ("bills", "notices", "entities", "all"):
        return jsonify({"error": "type must be bills, notices, entities, or all"}), 400

    def _date_filter(records: list[dict], date_key: str) -> list[dict]:
        out = records
        if from_date:
            out = [r for r in out if r.get(date_key, "") >= from_date]
        if to_date:
            out = [r for r in out if r.get(date_key, "") <= to_date]
        return out

    # Collect requested data
    payload: dict[str, list] = {}

    if data_type in ("bills", "all"):
        rows: list = []
        for year in recent_years():
            rows.extend(bills_data.load_bills(_app._data_dir, year))
        payload["bills"] = _date_filter(rows, "date_received")

    if data_type in ("notices", "all"):
        rows = []
        for year in recent_years():
            rows.extend(notices_data.load_notices(_app._data_dir, year))
        payload["notices"] = _date_filter(rows, "date_received")

    if data_type in ("entities", "all"):
        payload["entities"] = entity_data.load_entities(_app._data_dir)

    if fmt == "json":
        body = json.dumps(payload if data_type == "all" else list(payload.values())[0],
                          indent=2, default=str)
        filename = f"postmule_{data_type}.json"
        return Response(
            body,
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    # CSV — only single-type exports make sense; "all" exports bills as default
    export_key = data_type if data_type != "all" else "bills"
    records = payload.get(export_key, [])

    buf = io.StringIO()
    if records:
        writer = csv.DictWriter(buf, fieldnames=list(records[0].keys()), extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            writer.writerow({k: (", ".join(v) if isinstance(v, list) else v)
                             for k, v in rec.items()})
    else:
        buf.write("")

    filename = f"postmule_{export_key}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@api_bp.route("/api/export/config", methods=["GET"])
def api_export_config():
    """Export config.yaml with all sensitive values redacted.

    Safe to share — no API keys, passwords, or personal data in the output.
    """
    import copy
    cfg = copy.deepcopy(_app._config_raw)

    _REDACT_KEYS = {
        "api_key", "password", "token", "secret", "access_token", "client_secret",
        "username", "address", "alert_email", "alert_email_secondary",
    }

    def _redact(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: ("[REDACTED]" if k in _REDACT_KEYS else _redact(v))
                    for k, v in obj.items()}
        if isinstance(obj, list):
            return [_redact(i) for i in obj]
        return obj

    redacted = _redact(cfg)
    body = yaml.dump(redacted, default_flow_style=False, allow_unicode=True, sort_keys=False)
    header = (
        "# PostMule config.yaml — REDACTED EXPORT\n"
        "# Sensitive values have been replaced with [REDACTED].\n"
        "# Fill them in before using this file for a fresh install.\n\n"
    )
    return Response(
        header + body,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=postmule_config_redacted.yaml"},
    )


@api_bp.route("/api/export/connections-summary", methods=["GET"])
def api_export_connections_summary():
    """Export a plain-text reinstall checklist of all configured providers and required credentials."""
    from postmule.web.routes.pages import _connection_status
    conn = _connection_status()
    cfg = _app._config_raw

    lines: list[str] = [
        "PostMule — Connections & Credentials Reinstall Summary",
        "=" * 56,
        "",
        "Use this checklist when reinstalling PostMule on a new machine.",
        "It lists every configured provider and the credentials you will need to re-enter.",
        "Actual credential values are NOT included — only field names and connection status.",
        "",
    ]

    def _section(title: str, items: list[str]) -> None:
        lines.append(f"[ {title} ]")
        lines.extend(f"  {item}" for item in items)
        lines.append("")

    # Google / OAuth
    google_status = "Connected" if conn.get("google") else "NOT CONNECTED"
    _section("Google OAuth", [
        f"Status: {google_status}",
        "Required: Google OAuth token (re-run 'postmule --setup' or visit Connections page)",
    ])

    # Mailbox
    mbox = conn.get("mailbox", {})
    mbox_type = mbox.get("type", "not configured")
    _section("Physical Mailbox Provider", [
        f"Type: {mbox_type}",
        f"Status: {'Connected' if mbox.get('creds_ok') else 'NOT CONNECTED'}",
        "Required credentials: username, password (stored in credentials.enc)",
    ])

    # Email
    email = conn.get("email", {})
    _section("Email Provider", [
        f"Type: {email.get('type', 'not configured')}",
        f"Address: {email.get('address', 'not set')}",
        f"Status: {'Enabled' if email.get('enabled') else 'Not configured'}",
        "Required: Gmail/IMAP credentials or OAuth token",
    ])

    # Storage
    storage = conn.get("storage", {})
    _section("File Storage", [
        f"Type: {storage.get('type', 'not configured')}",
        f"Root folder: {storage.get('root_folder', 'not set')}",
        "Required: Google OAuth (for Drive) or provider-specific API key",
    ])

    # Spreadsheet
    sheet = conn.get("spreadsheet", {})
    _section("Spreadsheet", [
        f"Type: {sheet.get('type', 'not configured')}",
        f"Workbook: {sheet.get('workbook_name', 'not set')}",
        "Required: Google OAuth (for Sheets) or provider-specific credentials",
    ])

    # LLM
    llm = conn.get("llm", {})
    llm_type = llm.get("type", "not configured")
    key_fields = {
        "anthropic": "anthropic.api_key",
        "openai": "openai.api_key",
        "gemini": "gemini.api_key",
    }
    _section("AI / LLM Provider", [
        f"Type: {llm_type}",
        f"Model: {llm.get('model', 'not set')}",
        f"Required credential: {key_fields.get(llm_type, 'provider API key')}",
    ])

    # Finance
    finance = conn.get("finance", {})
    finance_type = finance.get("type", "not configured")
    finance_creds = {
        "ynab": ["ynab.access_token", "ynab.budget_id"],
        "plaid": ["plaid.client_id", "plaid.secret", "plaid.access_token"],
        "simplifi": ["simplifi.username", "simplifi.password"],
        "monarch": ["monarch.username", "monarch.password"],
    }
    _section("Finance Provider", [
        f"Type: {finance_type}",
        f"Status: {'Connected' if finance.get('ynab_ok') else 'Check credentials'}",
        f"Required credentials: {', '.join(finance_creds.get(finance_type, ['provider credentials']))}",
    ])

    # Notifications
    notif = conn.get("notifications", {})
    _section("Notifications", [
        f"Alert email: {notif.get('alert_email', 'not set')}",
        f"Secondary email: {notif.get('alert_email_secondary', 'not set')}",
        "Required: re-enter alert_email in config.yaml after reinstall",
    ])

    lines.append("---")
    lines.append("Generated by PostMule. For support: https://github.com/PostMule/app")

    body = "\n".join(lines)
    return Response(
        body,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=postmule_connections_summary.txt"},
    )


# ------------------------------------------------------------------
# Connections page — credential save + provider switch
# ------------------------------------------------------------------

@api_bp.route("/api/credential", methods=["POST"])
def api_save_credential():
    """Save a single credential field into credentials.enc.

    Form fields: provider, field, value, tab (optional, for redirect).
    Example: provider=vpm, field=password, value=secret123
    """
    if _app._enc_path is None:
        return "Credentials file path not configured", 500

    provider = (request.form.get("provider") or "").strip()
    field = (request.form.get("field") or "").strip()
    value = (request.form.get("value") or "").strip()
    tab = request.form.get("tab", "")

    if not provider or not field:
        return "provider and field are required", 400
    if not value:
        return redirect(url_for("pages.providers", tab=tab, error="value_empty"))

    try:
        from postmule.core.credentials import save_credential
        save_credential(_app._enc_path, provider, field, value)
    except Exception as exc:
        log.warning("Failed to save credential %s.%s: %s", provider, field, exc)
        return redirect(url_for("pages.providers", tab=tab, error="save_failed"))

    return redirect(url_for("pages.providers", tab=tab, saved="1"))


# Map each config category + type to the config.yaml structure
_PROVIDER_CATEGORY_KEY: dict[str, str] = {
    "email": "email",
    "storage": "storage",
    "spreadsheet": "spreadsheet",
    "mailbox": "mailbox",
    "llm": "llm",
    "finance": "finance",
}


@api_bp.route("/api/connection/provider", methods=["POST"])
def api_connection_provider():
    """Switch the active provider for a given category by rewriting config.yaml.

    Form fields: category, type, tab (optional, for redirect).
    """
    if _app._config_path is None:
        return "Config file not loaded", 500

    category = (request.form.get("category") or "").strip()
    provider_type = (request.form.get("type") or "").strip()
    tab = request.form.get("tab", "")

    config_key = _PROVIDER_CATEGORY_KEY.get(category)
    if not config_key or not provider_type:
        return redirect(url_for("pages.providers", tab=tab, error="invalid_params"))

    cfg = dict(_app._config_raw)
    section = dict(cfg.get(config_key, {}))
    providers = list(section.get("providers", []))

    if providers:
        # Keep existing settings, just change the type of the first provider
        first = dict(providers[0])
        first["type"] = provider_type
        providers[0] = first
    else:
        providers = [{"type": provider_type}]

    section["providers"] = providers
    cfg[config_key] = section

    try:
        with open(_app._config_path, "w", encoding="utf-8") as fh:
            yaml.dump(cfg, fh, allow_unicode=True, default_flow_style=False)
        # Reload config in memory
        _app._config_raw = cfg
    except Exception as exc:
        log.warning("Failed to update provider config: %s", exc)
        return redirect(url_for("pages.providers", tab=tab, error="save_failed"))

    return redirect(url_for("pages.providers", tab=tab, saved="1"))


@api_bp.route("/api/feedback", methods=["POST"])
def api_feedback():
    """Save in-app feedback locally and optionally submit as a GitHub issue."""
    import urllib.request
    import urllib.error
    import json as _json
    from postmule import __version__
    from postmule.data.feedback import append_feedback

    data = request.get_json(silent=True) or {}
    feedback_type = data.get("type", "general")  # bug | feature | general
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    steps = (data.get("steps") or "").strip()
    page = (data.get("page") or "").strip()
    version = (data.get("version") or str(__version__)).strip()

    if not title or not description:
        return jsonify({"error": "Title and description are required."}), 400

    # Always write to local log first (no PAT required)
    entry = {
        "type": feedback_type,
        "title": title,
        "description": description,
        "steps": steps or None,
        "page": page or None,
        "version": version,
    }
    try:
        append_feedback(_app._data_dir, entry)
    except Exception as exc:
        log.warning("Failed to write feedback to local log: %s", exc)

    # Optionally submit to GitHub if PAT is configured — no PII in issue body
    try:
        from postmule.core.credentials import load_credentials
        creds = load_credentials(_app._enc_path)
        github_pat = (creds or {}).get("github", {}).get("pat", "")
        target_repo = (creds or {}).get("github", {}).get("repo", "PostMule/app")
    except Exception:
        github_pat = ""
        target_repo = "PostMule/app"

    if not github_pat:
        return jsonify({"saved": True}), 200

    # Build issue body
    type_labels = {"bug": ["user-feedback", "bug"], "feature": ["user-feedback", "enhancement"]}
    labels = type_labels.get(feedback_type, ["user-feedback"])

    body_parts = [f"**Description**\n\n{description}"]
    if steps and feedback_type == "bug":
        body_parts.append(f"**Steps to reproduce**\n\n{steps}")
    body_parts.append(f"**App version:** {__version__}")
    if page:
        body_parts.append(f"**Page:** {page}")
    body_parts.append("---\n*Submitted via PostMule in-app feedback*")
    issue_body = "\n\n".join(body_parts)

    payload = _json.dumps({
        "title": title,
        "body": issue_body,
        "labels": labels,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"https://api.github.com/repos/{target_repo}/issues",
        data=payload,
        headers={
            "Authorization": f"token {github_pat}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": f"PostMule/{__version__}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = _json.loads(resp.read().decode("utf-8"))
        return jsonify({"saved": True, "url": result.get("html_url", ""), "number": result.get("number")}), 200
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        log.warning("GitHub feedback submission failed: %s", detail)
        return jsonify({"saved": True}), 200
    except Exception as exc:
        log.warning("GitHub feedback submission failed: %s", exc)
        return jsonify({"saved": True}), 200


# ------------------------------------------------------------------
# Owner registry
# ------------------------------------------------------------------

@api_bp.route("/api/owners", methods=["GET"])
def api_owners_list():
    """List owners. Active only by default; ?all=true includes inactive."""
    include_inactive = request.args.get("all", "false").lower() == "true"
    return jsonify(owners_data.load_owners(_app._data_dir, include_inactive=include_inactive))


@api_bp.route("/api/owners", methods=["POST"])
def api_owners_create():
    """Create a new owner. Form fields: name (required), type, short_name, color."""
    name = (request.form.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    owner = owners_data.add_owner(
        _app._data_dir,
        name,
        request.form.get("type", "person"),
        short_name=request.form.get("short_name") or None,
        color=request.form.get("color") or None,
    )
    return jsonify(owner), 201


@api_bp.route("/api/owners/<owner_id>", methods=["PATCH"])
def api_owners_update(owner_id: str):
    """Update writable fields on an owner. Form fields: name, type, short_name, color, active."""
    fields = {k: v for k, v in request.form.items()}
    updated = owners_data.update_owner(_app._data_dir, owner_id, fields)
    if updated is None:
        return jsonify({"error": "Owner not found"}), 404
    return jsonify(updated)


@api_bp.route("/api/owners/<owner_id>", methods=["DELETE"])
def api_owners_delete(owner_id: str):
    """Soft-delete an owner (sets active=False)."""
    if not owners_data.deactivate_owner(_app._data_dir, owner_id):
        return jsonify({"error": "Owner not found"}), 404
    return ("", 204)


@api_bp.route("/api/mail/<mail_id>/owners", methods=["PUT"])
def api_mail_set_owners(mail_id: str):
    """Set owner_ids on a mail item. Form field: owner_ids (JSON array of UUIDs)."""
    raw = request.form.get("owner_ids", "[]")
    try:
        owner_ids = json.loads(raw)
        if not isinstance(owner_ids, list):
            raise ValueError
    except (ValueError, json.JSONDecodeError):
        return jsonify({"error": "owner_ids must be a JSON array"}), 400

    from postmule.data._io import recent_years
    for year in recent_years():
        for bill in bills_data.load_bills(_app._data_dir, year):
            if bill.get("id") == mail_id:
                bills_data.set_owner_ids(_app._data_dir, mail_id, owner_ids)
                return ("", 200)
        for notice in notices_data.load_notices(_app._data_dir, year):
            if notice.get("id") == mail_id:
                notices_data.set_owner_ids(_app._data_dir, mail_id, owner_ids)
                return ("", 200)
    for ftm in ftm_data.load_forward_to_me(_app._data_dir):
        if ftm.get("id") == mail_id:
            ftm_data.set_owner_ids(_app._data_dir, mail_id, owner_ids)
            return ("", 200)

    return jsonify({"error": "Mail item not found"}), 404
