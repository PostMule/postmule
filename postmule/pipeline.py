"""
Main daily pipeline orchestrator.

Runs all agents in sequence for the daily 2am run.
Each step is wrapped in error handling — a failure in one step
doesn't prevent subsequent steps from running.
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from postmule.agents import bill_email_intake
from postmule.agents import classification as classify_agent
from postmule.agents import email_ingestion
from postmule.agents import mailbox_ingestion
from postmule.agents import entity_discovery
from postmule.agents.integrity import duplicate_detector, run_monitor
from postmule.core.config import Config
from postmule.data import bills as bills_data
from postmule.data import entities as entity_data
from postmule.data import forward_to_me as ftm_data
from postmule.data import notices as notices_data
from postmule.data import run_log

log = logging.getLogger("postmule.pipeline")

# Map lowercase Drive folder names to config.yaml folder keys (which use underscores)
_FOLDER_KEY_OVERRIDES = {
    "forwardtome": "forward_to_me",
    "needsreview": "needs_review",
}


def _to_folder_key(name: str) -> str:
    """Normalize a category or Drive folder name to its config.yaml folder key."""
    k = name.lower()
    return _FOLDER_KEY_OVERRIDES.get(k, k)


@dataclass
class Providers:
    drive: Any
    sheets: Any
    llm: Any
    safety_agent: Any
    folder_ids: dict = field(default_factory=dict)
    vpm: Any = None  # VpmProvider — set when VPM credentials are configured
    mailbox_notification_providers: list = field(default_factory=list)  # EmailProvider(s) with role: mailbox_notifications
    bill_intake_providers: list = field(default_factory=list)  # EmailProvider(s) with role: bill_intake


def run_daily_pipeline(
    cfg: Config,
    credentials: dict[str, Any],
    data_dir: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Execute the full daily PostMule pipeline.

    Args:
        cfg:         Loaded Config object.
        credentials: Decrypted credentials dict.
        data_dir:    Path to JSON data directory.
        dry_run:     If True, no writes to Drive, Gmail, or JSON.

    Returns:
        Run summary dict (also appended to run_log.json).
    """
    run_id = str(uuid.uuid4())
    start_time = datetime.now(tz=timezone.utc).isoformat()
    errors: list[str] = []

    stats: dict[str, Any] = {
        "run_id": run_id,
        "start_time": start_time,
        "end_time": "",
        "status": "success",
        "emails_found": 0,
        "pdfs_processed": 0,
        "bills": 0,
        "notices": 0,
        "forward_to_me": 0,
        "personal": 0,
        "junk": 0,
        "needs_review": 0,
        "errors": errors,
        "api_usage": {},
    }

    log.info(f"=== PostMule daily run starting (run_id={run_id[:8]}) ===")
    if dry_run:
        log.info("[DRY RUN] No data will be written.")

    # ------------------------------------------------------------------
    # Build providers
    # ------------------------------------------------------------------
    try:
        providers = _build_providers(cfg, credentials, data_dir)
    except Exception as exc:
        log.error(f"Failed to initialise providers: {exc}")
        stats["status"] = "failed"
        stats["errors"].append(str(exc))
        stats["end_time"] = datetime.now(tz=timezone.utc).isoformat()
        if not dry_run:
            run_log.append_run(data_dir, stats)
        return stats

    known_names = entity_data.get_all_known_names(data_dir)
    confidence_threshold = cfg.confidence_threshold
    max_files = cfg.max_files_per_run

    # ------------------------------------------------------------------
    # Step 1: Email ingestion
    # ------------------------------------------------------------------
    log.info("Step 1/7: Email ingestion")
    processed_pdfs = []
    forward_to_me_found: list[dict] = []
    classified_items: list[dict] = []
    try:
        mailbox_provider_cfg = (cfg.get("mailbox", "providers") or [{}])[0]
        with tempfile.TemporaryDirectory() as tmpdir:
            if providers.vpm is not None:
                log.info("Using VPM direct API for ingestion")
                ingestion = mailbox_ingestion.run_vpm_ingestion(
                    vpm=providers.vpm,
                    drive=providers.drive,
                    inbox_folder_id=providers.folder_ids.get("inbox", ""),
                    download_dir=Path(tmpdir),
                    dry_run=dry_run,
                )
                stats["emails_found"] = ingestion.emails_found
                errors.extend(ingestion.errors)
                processed_pdfs = ingestion.ingested
                if ingestion.errors:
                    stats["status"] = "partial"
            else:
                scan_sender = mailbox_provider_cfg.get("scan_sender", "noreply@virtualpostmail.com")
                scan_subject = mailbox_provider_cfg.get("scan_subject_prefix", "[Scan Request]")
                if not providers.mailbox_notification_providers:
                    log.warning("No mailbox notification email providers configured — skipping ingestion")
                for ep in providers.mailbox_notification_providers:
                    try:
                        ingestion = email_ingestion.run_ingestion(
                            gmail=ep,
                            drive=providers.drive,
                            inbox_folder_id=providers.folder_ids.get("inbox", ""),
                            download_dir=Path(tmpdir),
                            sender_filter=scan_sender,
                            subject_filter=scan_subject,
                            dry_run=dry_run,
                        )
                        stats["emails_found"] += ingestion.emails_found
                        errors.extend(ingestion.errors)
                        processed_pdfs = list(processed_pdfs) + ingestion.ingested
                        if ingestion.errors:
                            stats["status"] = "partial"
                    except Exception as exc:
                        msg = f"Mailbox notification ingestion failed: {exc}"
                        log.error(msg)
                        errors.append(msg)
                        stats["status"] = "partial"

            # ------------------------------------------------------------------
            # Step 1b: Bill email intake (bill_intake role providers)
            # ------------------------------------------------------------------
            if providers.bill_intake_providers:
                log.info(f"Step 1b: Bill email intake ({len(providers.bill_intake_providers)} provider(s))")
            for bp in providers.bill_intake_providers:
                try:
                    bi = bill_email_intake.run_intake(
                        email_provider=bp,
                        drive=providers.drive,
                        inbox_folder_id=providers.folder_ids.get("inbox", ""),
                        download_dir=Path(tmpdir),
                        dry_run=dry_run,
                    )
                    stats["emails_found"] += bi.emails_found
                    processed_pdfs = list(processed_pdfs) + bi.ingested
                    errors.extend(bi.errors)
                    if bi.errors:
                        stats["status"] = "partial"
                except Exception as exc:
                    msg = f"Bill email intake failed: {exc}"
                    log.error(msg)
                    errors.append(msg)
                    stats["status"] = "partial"

            # ------------------------------------------------------------------
            # Step 2: OCR + Classification (per PDF)
            # ------------------------------------------------------------------
            log.info(f"Step 2/7: Classifying {len(processed_pdfs)} PDFs")
            all_discovered_names: list[str] = []
            count = 0

            for ingested in processed_pdfs:
                if count >= max_files:
                    log.warning(
                        f"Safety cap reached: max {max_files} files per run. "
                        f"Remaining PDFs will be processed tomorrow."
                    )
                    break

                try:
                    result = classify_agent.classify_pdf(
                        pdf_path=ingested.local_path,
                        llm=providers.llm,
                        known_names=known_names,
                        confidence_threshold=confidence_threshold,
                        dry_run=dry_run,
                    )
                    count += 1
                    cat_key = _to_folder_key(result.category)
                    stats[cat_key] = stats.get(cat_key, 0) + 1
                    stats["pdfs_processed"] += 1

                    # Move file to correct Drive folder
                    if not dry_run and ingested.drive_file_id:
                        dest_folder_id = providers.folder_ids.get(
                            _to_folder_key(result.destination_folder),
                            providers.folder_ids.get("needs_review", "")
                        )
                        if dest_folder_id and dest_folder_id != providers.folder_ids.get("inbox"):
                            providers.drive.move_file(
                                ingested.drive_file_id,
                                dest_folder_id,
                                providers.folder_ids.get("inbox", ""),
                            )
                            providers.drive.rename_file(ingested.drive_file_id, result.suggested_filename)

                    # Store in JSON
                    if not dry_run:
                        _store_processed_mail(data_dir, result, ingested.drive_file_id,
                                              ingested.received_date)

                    # Collect for daily summary
                    classified_items.append({
                        "category": result.category,
                        "sender": result.sender,
                        "recipients": result.recipients,
                        "summary": result.summary,
                        "amount_due": result.amount_due,
                        "due_date": result.due_date,
                        "processed_date": result.processed_date,
                    })

                    # Collect ForwardToMe for urgent alert
                    if result.category == "ForwardToMe":
                        forward_to_me_found.append({
                            "sender": result.sender,
                            "summary": result.summary,
                            "date_received": ingested.received_date,
                        })

                    # Collect names for batch entity discovery (run once after loop)
                    names = (result.recipients or []) + ([result.sender] if result.sender else [])
                    all_discovered_names.extend(names)

                except Exception as exc:
                    msg = f"Error processing {ingested.filename}: {exc}"
                    log.error(msg)
                    errors.append(msg)
                    stats["status"] = "partial"

            # Run entity discovery once for all names collected this run
            if all_discovered_names:
                try:
                    entity_discovery.run_entity_discovery(
                        names_from_mail=all_discovered_names,
                        data_dir=data_dir,
                        fuzzy_threshold=float(cfg.get("entities", "fuzzy_match_threshold", default=0.85)) * 100,
                        auto_approve_days=int(cfg.get("entities", "auto_approve_after_days", default=7)),
                    )
                except Exception as exc:
                    log.warning(f"Entity discovery failed (non-fatal): {exc}")

    except Exception as exc:
        msg = f"Email ingestion failed: {exc}"
        log.error(msg)
        errors.append(msg)
        stats["status"] = "partial"

    # ------------------------------------------------------------------
    # Step 3: Duplicate detection
    # ------------------------------------------------------------------
    log.info("Step 3/7: Duplicate detection")
    try:
        dup_result = duplicate_detector.run_duplicate_detection(
            drive=providers.drive, folder_ids=providers.folder_ids, data_dir=data_dir, dry_run=dry_run
        )
        if dup_result.get("duplicates_found", 0) > 0:
            log.info(f"Moved {dup_result['moved']} duplicates to /Duplicates")
    except Exception as exc:
        log.warning(f"Duplicate detection failed (non-fatal): {exc}")

    # ------------------------------------------------------------------
    # Step 4: Bill matching (Simplifi)
    # ------------------------------------------------------------------
    log.info("Step 4/7: Bill matching")
    try:
        _run_bill_matching(cfg, credentials, data_dir, dry_run)
    except Exception as exc:
        log.warning(f"Bill matching failed (non-fatal): {exc}")

    # ------------------------------------------------------------------
    # Step 5: Update Google Sheets
    # ------------------------------------------------------------------
    log.info("Step 5/7: Updating Google Sheets")
    if not dry_run:
        try:
            _update_sheets(providers.sheets, data_dir)
        except Exception as exc:
            log.warning(f"Sheets update failed (non-fatal): {exc}")

    # ------------------------------------------------------------------
    # Step 6: Alerts (urgent ForwardToMe + proactive bill due)
    # ------------------------------------------------------------------
    log.info("Step 6/7: Alerts")
    smtp_cfg = credentials.get("smtp", {})
    _recipients = cfg.alert_recipients
    if forward_to_me_found:
        try:
            from postmule.agents.summary import send_urgent_alert
            for _addr in _recipients:
                send_urgent_alert(smtp_cfg, _addr, forward_to_me_found)
        except Exception as exc:
            log.warning(f"Urgent alert failed: {exc}")

    bill_due_alert_days = int(cfg.get("notifications", "bill_due_alert_days") or 7)
    try:
        from postmule.agents.summary import send_bill_due_alert
        _cur_year = datetime.now(tz=timezone.utc).year
        all_bills = (bills_data.load_bills(data_dir, _cur_year) +
                     bills_data.load_bills(data_dir, _cur_year - 1))
        for _addr in _recipients:
            send_bill_due_alert(smtp_cfg, _addr, all_bills, bill_due_alert_days, dry_run=dry_run, data_dir=data_dir)
    except Exception as exc:
        log.warning(f"Bill due alert failed (non-fatal): {exc}")

    # ------------------------------------------------------------------
    # Step 7: Daily summary email
    # ------------------------------------------------------------------
    log.info("Step 7/7: Daily summary")
    stats["end_time"] = datetime.now(tz=timezone.utc).isoformat()
    try:
        from postmule.agents.summary import send_daily_summary
        _cur_year = datetime.now(tz=timezone.utc).year
        _all_bills = (bills_data.load_bills(data_dir, _cur_year) +
                      bills_data.load_bills(data_dir, _cur_year - 1))
        pending_bills = [b for b in _all_bills if b.get("status") == "pending"]
        smtp_cfg = credentials.get("smtp", {})
        for _addr in _recipients:
          send_daily_summary(
            smtp_config=smtp_cfg,
            alert_email=_addr,
            run_stats=stats,
            processed_items=classified_items,
            pending_bills=pending_bills,
            api_usage=providers.safety_agent.summary() if providers.safety_agent else {},
            dry_run=dry_run,
        )
    except Exception as exc:
        log.warning(f"Daily summary email failed: {exc}")

    # Save API usage
    if providers.safety_agent:
        stats["api_usage"] = providers.safety_agent.summary()

    # Record run
    if not dry_run:
        run_log.append_run(data_dir, stats)

    log.info(
        f"=== Run complete: {stats['pdfs_processed']} PDFs, "
        f"{len(errors)} errors, status={stats['status']} ==="
    )
    return stats


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _instantiate_email_provider(ep_cfg: dict, credentials: dict, get_google_creds) -> Any:
    """Instantiate an email provider from a config entry. Returns None if creds missing."""
    service = ep_cfg.get("service", "gmail")
    account_id = ep_cfg.get("id", "")
    # Credentials for this account are stored under accounts.<id>
    acct_creds = credentials.get("accounts", {}).get(account_id, {}) if account_id else {}

    if service == "gmail":
        from postmule.providers.email.gmail import GmailProvider
        label = ep_cfg.get("label", "PostMule")
        return GmailProvider(get_google_creds(), label_name=label)

    if service == "imap":
        username = acct_creds.get("username", "")
        password = acct_creds.get("password", "")
        if not username or not password:
            log.warning(f"IMAP account {account_id!r} credentials not configured — skipping")
            return None
        from postmule.providers.email.imap import ImapProvider
        return ImapProvider(
            host=ep_cfg.get("host", ""),
            port=int(ep_cfg.get("port", 993)),
            username=username,
            password=password,
            use_ssl=str(ep_cfg.get("use_ssl", "true")).lower() not in ("false", "0", "no"),
            processed_folder=ep_cfg.get("processed_folder", "PostMule"),
        )

    if service == "proton":
        username = acct_creds.get("username", "")
        password = acct_creds.get("password", "")
        if not username or not password:
            log.warning(f"ProtonMail account {account_id!r} credentials not configured — skipping")
            return None
        from postmule.providers.email.proton import ProtonMailProvider
        return ProtonMailProvider(
            username=username,
            password=password,
            bridge_host=ep_cfg.get("bridge_host", "127.0.0.1"),
            bridge_port=int(ep_cfg.get("bridge_port", 1143)),
            processed_folder=ep_cfg.get("processed_folder", "PostMule"),
        )

    if service == "outlook_365":
        token = acct_creds.get("access_token", "")
        if not token:
            log.warning(f"Outlook 365 account {account_id!r} token not configured — skipping")
            return None
        from postmule.providers.email.outlook_365 import Outlook365Provider
        return Outlook365Provider(
            access_token=token,
            processed_category=ep_cfg.get("processed_category", "PostMule"),
        )

    if service == "outlook_com":
        token = acct_creds.get("access_token", "")
        if not token:
            log.warning(f"Outlook.com account {account_id!r} token not configured — skipping")
            return None
        from postmule.providers.email.outlook_com import OutlookComProvider
        return OutlookComProvider(
            access_token=token,
            processed_category=ep_cfg.get("processed_category", "PostMule"),
        )

    log.warning(f"Email service '{service}' is not supported — skipping account {account_id!r}")
    return None


def _build_providers(cfg: Config, credentials: dict, data_dir: Path):
    """Instantiate all providers from config + credentials."""
    from postmule.core.api_safety import build_safety_agent

    storage_provider_cfg = (cfg.get("storage", "providers") or [{}])[0]
    spreadsheet_provider_cfg = (cfg.get("spreadsheet", "providers") or [{}])[0]
    llm_provider_cfg = (cfg.get("llm", "providers") or [{}])[0]
    llm_provider_name = llm_provider_cfg.get("service", "gemini")

    # Lazy Google credentials — only loaded when a Google provider is actually configured
    _google_creds_cache: list = []

    def _get_google_creds():
        if not _google_creds_cache:
            from postmule.core.credentials import build_google_credentials
            _google_creds_cache.append(build_google_credentials())
        return _google_creds_cache[0]

    drive = _build_storage_provider(storage_provider_cfg, credentials, _get_google_creds)
    sheets = _build_spreadsheet_provider(spreadsheet_provider_cfg, credentials, data_dir, _get_google_creds)

    safety_agent = build_safety_agent(cfg, llm_provider_name, data_dir)
    llm = _build_llm_provider(llm_provider_cfg, credentials, safety_agent)

    # Ensure storage folders exist
    folders_cfg = storage_provider_cfg.get("folders") or {}
    folder_ids = drive.ensure_folder_structure(folders_cfg)

    # Build email providers by role
    mailbox_notification_providers = []
    bill_intake_providers = []
    for ep_cfg in cfg.get("email", "providers") or []:
        if not ep_cfg.get("enabled", True):
            continue
        role = ep_cfg.get("role", "mailbox_notifications")
        provider = _instantiate_email_provider(ep_cfg, credentials, _get_google_creds)
        if provider is None:
            continue
        service = ep_cfg.get("service", "gmail")
        account_id = ep_cfg.get("id", "")
        if role == "mailbox_notifications":
            mailbox_notification_providers.append(provider)
            log.info(f"Mailbox notification provider: {service} (id={account_id})")
        elif role == "bill_intake":
            bill_intake_providers.append(provider)
            log.info(f"Bill intake provider: {service} (id={account_id})")

    # Build VPM provider if credentials are available
    vpm = None
    mailbox_provider_cfg = (cfg.get("mailbox", "providers") or [{}])[0]
    if mailbox_provider_cfg.get("service") == "vpm" and mailbox_provider_cfg.get("enabled", True):
        vpm_creds = credentials.get("vpm", {})
        vpm_username = vpm_creds.get("username", "")
        vpm_password = vpm_creds.get("password", "")
        if vpm_username and vpm_password:
            from postmule.providers.mailbox.vpm import VpmProvider
            vpm = VpmProvider(vpm_username, vpm_password)
            log.info("VPM direct API provider configured")
        else:
            log.debug("VPM credentials not set — ingestion will use email fallback")

    return Providers(
        drive=drive,
        sheets=sheets,
        llm=llm,
        safety_agent=safety_agent,
        folder_ids=folder_ids,
        vpm=vpm,
        mailbox_notification_providers=mailbox_notification_providers,
        bill_intake_providers=bill_intake_providers,
    )


def _build_storage_provider(cfg_entry: dict, credentials: dict, get_google_creds):
    """Instantiate the configured storage provider."""
    service = cfg_entry.get("service", "local")

    if service == "local":
        from postmule.providers.storage.local import LocalStorageProvider
        root_dir = cfg_entry.get("root_dir", "C:\\ProgramData\\PostMule\\files")
        return LocalStorageProvider(root_dir=root_dir)

    if service == "google_drive":
        from postmule.providers.storage.google_drive import DriveProvider
        return DriveProvider(
            get_google_creds(),
            root_folder=cfg_entry.get("root_folder", "PostMule"),
        )

    if service == "s3":
        from postmule.providers.storage.s3 import S3Provider
        creds = credentials.get("s3", {})
        return S3Provider(
            aws_access_key_id=creds.get("access_key_id", ""),
            aws_secret_access_key=creds.get("secret_access_key", ""),
            bucket_name=cfg_entry.get("bucket", ""),
            region=cfg_entry.get("region", "us-east-1"),
        )

    if service == "dropbox":
        from postmule.providers.storage.dropbox import DropboxProvider
        creds = credentials.get("dropbox", {})
        return DropboxProvider(access_token=creds.get("access_token", ""))

    if service == "onedrive":
        from postmule.providers.storage.onedrive import OneDriveProvider
        creds = credentials.get("onedrive", {})
        return OneDriveProvider(access_token=creds.get("access_token", ""))

    raise ValueError(f"Unknown storage provider: '{service}'. Supported: local, google_drive, s3, dropbox, onedrive")


def _build_spreadsheet_provider(cfg_entry: dict, credentials: dict, data_dir: Path, get_google_creds):
    """Instantiate the configured spreadsheet provider."""
    service = cfg_entry.get("service", "sqlite")

    if service == "sqlite":
        from postmule.providers.spreadsheet.sqlite import SqliteSpreadsheetProvider
        db_name = cfg_entry.get("db_name", "postmule.db")
        return SqliteSpreadsheetProvider(db_path=data_dir / db_name)

    if service == "none":
        from postmule.providers.spreadsheet.none import NoneSpreadsheetProvider
        return NoneSpreadsheetProvider()

    if service == "google_sheets":
        from postmule.providers.spreadsheet.google_sheets import SheetsProvider
        return SheetsProvider(
            get_google_creds(),
            workbook_name=cfg_entry.get("workbook_name", "PostMule"),
        )

    if service == "airtable":
        from postmule.providers.spreadsheet.airtable import AirtableProvider
        creds = credentials.get("airtable", {})
        return AirtableProvider(
            api_key=creds.get("api_key", ""),
            base_id=cfg_entry.get("base_id", ""),
        )

    if service == "excel_online":
        from postmule.providers.spreadsheet.excel_online import ExcelOnlineProvider
        creds = credentials.get("excel_online", {})
        return ExcelOnlineProvider(access_token=creds.get("access_token", ""))

    raise ValueError(f"Unknown spreadsheet provider: '{service}'. Supported: sqlite, none, google_sheets, airtable, excel_online")


def _build_llm_provider(cfg_entry: dict, credentials: dict, safety_agent):
    """Instantiate the configured LLM provider."""
    service = cfg_entry.get("service", "gemini")
    llm_creds = credentials.get(service, {})

    if service == "gemini":
        from postmule.providers.llm.gemini import GeminiProvider
        return GeminiProvider(
            llm_creds.get("api_key", ""),
            safety_agent=safety_agent,
            model=cfg_entry.get("model", "gemini-1.5-flash"),
        )

    if service == "openai":
        from postmule.providers.llm.openai import OpenAIProvider
        return OpenAIProvider(
            api_key=llm_creds.get("api_key", ""),
            model=cfg_entry.get("model", "gpt-4o-mini"),
        )

    if service == "anthropic":
        from postmule.providers.llm.anthropic import AnthropicProvider
        return AnthropicProvider(
            api_key=llm_creds.get("api_key", ""),
            model=cfg_entry.get("model", "claude-haiku-4-5-20251001"),
        )

    if service == "ollama":
        from postmule.providers.llm.ollama import OllamaProvider
        return OllamaProvider(
            host=cfg_entry.get("host", "http://localhost:11434"),
            model=cfg_entry.get("model", "llama3.2"),
        )

    raise ValueError(f"Unknown LLM provider: '{service}'. Supported: gemini, openai, anthropic, ollama")


def _store_processed_mail(data_dir: Path, result, drive_file_id: str, received_date: str) -> None:
    base = {
        "date_received": received_date,
        "date_processed": result.processed_date,
        "sender": result.sender,
        "recipients": result.recipients,
        "summary": result.summary,
        "drive_file_id": drive_file_id,
        "filename": result.suggested_filename,
    }
    if result.category == "Bill":
        bills_data.add_bill(data_dir, {
            **base,
            "amount_due": result.amount_due,
            "due_date": result.due_date,
            "account_number": result.account_number,
            "statement_date": result.statement_date,
            "ach_descriptor": result.ach_descriptor,
            "status": "pending",
        })
    elif result.category == "Notice":
        notices_data.add_notice(data_dir, base)
    elif result.category == "ForwardToMe":
        ftm_data.add_item(data_dir, {**base, "forwarding_status": "pending"})


def _build_finance_provider(provider_type: str, cfg_entry: dict, credentials: dict):
    """Instantiate the configured finance provider. Returns None if type is unknown."""
    if provider_type == "simplifi":
        from postmule.providers.finance.simplifi import SimplifiProvider
        creds = credentials.get("simplifi", {})
        return SimplifiProvider(creds.get("username", ""), creds.get("password", ""))

    if provider_type == "ynab":
        from postmule.providers.finance.ynab import YnabProvider
        creds = credentials.get("ynab", {})
        return YnabProvider(
            access_token=creds.get("access_token", ""),
            budget_id=creds.get("budget_id", "last-used"),
        )

    if provider_type == "plaid":
        from postmule.providers.finance.plaid import PlaidProvider
        creds = credentials.get("plaid", {})
        return PlaidProvider(
            client_id=creds.get("client_id", ""),
            secret=creds.get("secret", ""),
            access_token=creds.get("access_token", ""),
            environment=cfg_entry.get("environment", "development"),
        )

    if provider_type == "monarch":
        from postmule.providers.finance.monarch import MonarchProvider
        creds = credentials.get("monarch", {})
        return MonarchProvider(creds.get("username", ""), creds.get("password", ""))

    return None


def _run_bill_matching(cfg: Config, credentials: dict, data_dir: Path, dry_run: bool) -> None:
    finance_providers = cfg.get("finance", "providers") or []
    enabled = [p for p in finance_providers if p.get("enabled")]
    if not enabled:
        log.debug("No finance provider enabled — skipping bill matching.")
        return

    cfg_entry = enabled[0]
    provider_type = cfg_entry.get("type", "")
    provider = _build_finance_provider(provider_type, cfg_entry, credentials)
    if provider is None:
        log.debug(f"Finance provider '{provider_type}' not yet implemented.")
        return

    from postmule.providers.finance.base import match_bills_to_transactions
    transactions = provider.get_recent_transactions(days=30)
    from datetime import date as _d
    _cy = _d.today().year
    _all = bills_data.load_bills(data_dir, _cy) + bills_data.load_bills(data_dir, _cy - 1)
    pending_bills = [b for b in _all if b.get("status") == "pending"]
    matches = match_bills_to_transactions(pending_bills, transactions)
    log.info(f"Bill matching: {len(matches)} potential matches (require manual approval)")
    if matches and not dry_run:
        _save_bill_matches(data_dir, matches)


def _save_bill_matches(data_dir: Path, matches: list) -> None:
    """Persist bill match candidates to pending/bill_matches.json for dashboard review."""
    import json
    pending_dir = data_dir / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / "bill_matches.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    existing_keys = {(m.get("bill_id"), m.get("transaction_id")) for m in existing}
    for m in matches:
        record = {
            "bill_id": m.bill_id,
            "transaction_id": m.transaction_id,
            "bill_amount": m.amount,
            "transaction_date": m.date,
            "confidence": m.confidence,
            "status": "pending",
        }
        if (record["bill_id"], record["transaction_id"]) not in existing_keys:
            existing.append(record)
    text = json.dumps(existing, indent=2, ensure_ascii=False)
    fd, tmp = tempfile.mkstemp(dir=pending_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    log.info(f"Saved {len(matches)} bill match candidate(s) to pending/bill_matches.json")


def _update_sheets(sheets, data_dir: Path) -> None:
    from postmule.data import bills as bd, notices as nd, forward_to_me as fd, run_log as rl
    sheets.get_or_create_workbook()
    sheets.write_sheet("Bills", bd.to_sheet_rows(bd.load_bills(data_dir)))
    sheets.write_sheet("Notices", nd.to_sheet_rows(nd.load_notices(data_dir)))
    sheets.write_sheet("ForwardToMe", fd.to_sheet_rows(fd.load_forward_to_me(data_dir)))
    sheets.write_sheet("RunLog", rl.to_sheet_rows(rl.load_run_log(data_dir)))
