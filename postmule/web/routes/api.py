"""API blueprint — HTMX/JSON endpoints."""

from __future__ import annotations

import logging
import threading
from typing import Any

import yaml

from flask import Blueprint, jsonify, redirect, request, url_for

from postmule.core.config import load_config
from postmule.data import bills as bills_data
from postmule.data import entity_corrections as corrections_data
from postmule.data import entities as entity_data
from postmule.data import forward_to_me as ftm_data
from postmule.data import notices as notices_data

import postmule.web.app as _app

log = logging.getLogger("postmule.web")

api_bp = Blueprint("api", __name__)


@api_bp.route("/api/approve", methods=["POST"])
def api_approve():
    match_id = request.form.get("match_id")
    if not match_id:
        return jsonify({"error": "match_id required"}), 400

    pending = entity_data.load_pending_matches(_app._data_dir)
    entities = entity_data.load_entities(_app._data_dir)

    for match in pending:
        if match["id"] == match_id and match["status"] == "pending":
            match["status"] = "approved"
            for entity in entities:
                if entity["id"] == match["match_entity_id"]:
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

    if field == "account_numbers":
        parsed_value: Any = [v.strip() for v in value.split(",") if v.strip()]
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


@api_bp.route("/api/entity/<entity_id>/add-account", methods=["POST"])
def api_entity_add_account(entity_id: str):
    """Append a single account number to an entity."""
    account = request.form.get("account", "").strip()
    if not account:
        return "account is required", 400
    entities = entity_data.load_entities(_app._data_dir)
    for e in entities:
        if e["id"] == entity_id:
            if account not in e["account_numbers"]:
                e["account_numbers"].append(account)
            entity_data.save_entities(_app._data_dir, entities)
            return ("", 200)
    return "Entity not found", 404
