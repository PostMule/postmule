"""
Backup agent — on-demand snapshot of all PostMule data to cloud storage.

Backup format: a single ZIP file uploaded to `_System/backups/` in the
configured storage provider.  Each backup is named:
    backup-YYYY-MM-DD-HHMMSS.zip

ZIP contents:
    data/                     ← all JSON files from local data_dir
        bills_YYYY.json
        notices_YYYY.json
        forward_to_me.json
        entities.json
        run_log.json
        pending/
            entity_matches.json
            bill_matches.json
    credentials.enc           ← encrypted credential store (safe to back up)
    config.yaml               ← non-secret configuration

Restore: download the ZIP from Drive and extract back to the same layout.
Pruning: delete backups older than `backup_retention_days` (default 180).
"""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("postmule.backup")

_BACKUP_FOLDER = "backups"
_SYSTEM_FOLDER = "_System"
_BACKUP_PREFIX = "backup-"
_BACKUP_LOG_FILE = "backup_log.json"


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def run_backup(
    cfg: Any,
    credentials: dict,
    data_dir: Path,
    config_path: Path | None,
    enc_path: Path | None,
    dry_run: bool = False,
) -> dict:
    """
    Create a ZIP snapshot of all PostMule data and upload to cloud storage.

    Returns a result dict:
        {
            "status": "ok" | "error",
            "backup_name": "backup-YYYY-MM-DD-HHMMSS.zip",
            "bytes_uploaded": int,
            "files_included": [str, ...],
            "pruned_count": int,
            "error": str | None,
        }
    """
    now = datetime.now(tz=timezone.utc)
    timestamp = now.strftime("%Y-%m-%d-%H%M%S")
    backup_name = f"{_BACKUP_PREFIX}{timestamp}.zip"

    try:
        drive = _build_drive(cfg, credentials)
    except Exception as exc:
        log.error(f"Backup: could not connect to storage — {exc}")
        return {"status": "error", "error": str(exc), "backup_name": backup_name, "bytes_uploaded": 0, "files_included": [], "pruned_count": 0}

    try:
        backup_folder_id = _ensure_backup_folder(drive)
        zip_bytes, file_list = _create_zip(data_dir, config_path, enc_path)

        log.info(f"Backup: {len(zip_bytes):,} bytes, {len(file_list)} files -> {backup_name}")

        if not dry_run:
            drive.upload_bytes(zip_bytes, backup_name, backup_folder_id, "application/zip")
            retention_days = cfg.get("data_protection", "backup_retention_days", default=180)
            pruned = _prune_old_backups(drive, backup_folder_id, retention_days)
            _update_backup_log(data_dir, backup_name, now, len(zip_bytes), len(file_list))
        else:
            log.info("[DRY RUN] backup upload skipped")
            pruned = 0

        return {
            "status": "ok",
            "backup_name": backup_name,
            "bytes_uploaded": len(zip_bytes),
            "files_included": file_list,
            "pruned_count": pruned,
            "error": None,
        }
    except Exception as exc:
        log.error(f"Backup failed: {exc}", exc_info=True)
        return {"status": "error", "error": str(exc), "backup_name": backup_name, "bytes_uploaded": 0, "files_included": [], "pruned_count": 0}


def run_restore(
    cfg: Any,
    credentials: dict,
    backup_name: str,
    data_dir: Path,
    dry_run: bool = False,
) -> dict:
    """
    Download a backup ZIP from cloud storage and restore it locally.

    Args:
        backup_name: Exact ZIP name (e.g. "backup-2026-03-23-020400.zip")
                     or "latest" to restore the most recent backup.

    Returns a result dict:
        {
            "status": "ok" | "error",
            "backup_name": str,
            "files_restored": [str, ...],
            "error": str | None,
        }
    """
    try:
        drive = _build_drive(cfg, credentials)
    except Exception as exc:
        log.error(f"Restore: could not connect to storage — {exc}")
        return {"status": "error", "error": str(exc), "backup_name": backup_name, "files_restored": []}

    try:
        backup_folder_id = _ensure_backup_folder(drive)
        files = drive.list_folder(backup_folder_id)
        backup_files = [f for f in files if f.get("name", "").startswith(_BACKUP_PREFIX) and f["name"].endswith(".zip")]

        if not backup_files:
            return {"status": "error", "error": "No backups found in cloud storage.", "backup_name": backup_name, "files_restored": []}

        if backup_name == "latest":
            backup_files.sort(key=lambda f: f["name"], reverse=True)
            target = backup_files[0]
        else:
            target = next((f for f in backup_files if f["name"] == backup_name), None)
            if not target:
                available = [f["name"] for f in backup_files]
                return {"status": "error", "error": f"Backup '{backup_name}' not found. Available: {available}", "backup_name": backup_name, "files_restored": []}

        resolved_name = target["name"]
        log.info(f"Restore: downloading {resolved_name} ({target.get('size', '?')} bytes)")

        if not dry_run:
            zip_bytes = drive.download_file(target["id"])
            restored = _extract_zip(zip_bytes, data_dir)
        else:
            log.info("[DRY RUN] restore extraction skipped")
            restored = []

        return {
            "status": "ok",
            "backup_name": resolved_name,
            "files_restored": restored,
            "error": None,
        }
    except Exception as exc:
        log.error(f"Restore failed: {exc}", exc_info=True)
        return {"status": "error", "error": str(exc), "backup_name": backup_name, "files_restored": []}


def list_backups(cfg: Any, credentials: dict) -> list[dict]:
    """
    List available backups in cloud storage.

    Returns list of dicts:
        [{"name": str, "date": str, "size_bytes": int}, ...]
    """
    try:
        drive = _build_drive(cfg, credentials)
        backup_folder_id = _ensure_backup_folder(drive)
        files = drive.list_folder(backup_folder_id)
    except Exception as exc:
        log.warning(f"Could not list backups: {exc}")
        return []

    result = []
    for f in files:
        name = f.get("name", "")
        if not (name.startswith(_BACKUP_PREFIX) and name.endswith(".zip")):
            continue
        date_str = name.removeprefix(_BACKUP_PREFIX).removesuffix(".zip")
        result.append({
            "name": name,
            "date": date_str,
            "size_bytes": int(f.get("size", 0)),
        })

    result.sort(key=lambda x: x["date"], reverse=True)
    return result


def get_last_backup(data_dir: Path) -> dict | None:
    """Read the last backup record from the local backup log."""
    log_path = data_dir / _BACKUP_LOG_FILE
    if not log_path.exists():
        return None
    import json
    try:
        records = json.loads(log_path.read_text(encoding="utf-8"))
        if isinstance(records, list) and records:
            return records[-1]
    except Exception:
        pass
    return None


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _build_drive(cfg: Any, credentials: dict):
    """Build and return the configured storage provider (Drive)."""
    from postmule.core.credentials import build_google_credentials
    from postmule.providers.storage.google_drive import DriveProvider

    google_creds = build_google_credentials()
    storage_cfg = (cfg.get("storage", "providers") or [{}])[0]
    return DriveProvider(
        google_creds,
        root_folder=storage_cfg.get("root_folder", "PostMule"),
    )


def _ensure_backup_folder(drive) -> str:
    """Get or create _System/backups folder in Drive. Returns folder ID."""
    root_id = drive._get_or_create_folder(drive.root_folder, parent_id=None)
    system_id = drive._get_or_create_folder(_SYSTEM_FOLDER, parent_id=root_id)
    backup_id = drive._get_or_create_folder(_BACKUP_FOLDER, parent_id=system_id)
    return backup_id


def _create_zip(
    data_dir: Path,
    config_path: Path | None,
    enc_path: Path | None,
) -> tuple[bytes, list[str]]:
    """Build an in-memory ZIP of all backup files. Returns (bytes, file_list)."""
    buf = io.BytesIO()
    file_list: list[str] = []

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # All JSON files in data_dir (recursive)
        if data_dir.exists():
            for json_file in sorted(data_dir.glob("**/*.json")):
                arcname = "data/" + str(json_file.relative_to(data_dir)).replace("\\", "/")
                zf.write(json_file, arcname)
                file_list.append(arcname)

        # credentials.enc
        if enc_path and enc_path.exists():
            zf.write(enc_path, enc_path.name)
            file_list.append(enc_path.name)

        # config.yaml
        if config_path and config_path.exists():
            zf.write(config_path, config_path.name)
            file_list.append(config_path.name)

    return buf.getvalue(), file_list


def _extract_zip(zip_bytes: bytes, restore_dir: Path) -> list[str]:
    """Extract a backup ZIP to restore_dir. Returns list of restored paths."""
    restored: list[str] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for member in zf.namelist():
            # data/ prefix → data_dir
            if member.startswith("data/"):
                dest_rel = member[len("data/"):]
                dest = restore_dir / dest_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not member.endswith("/"):
                    dest.write_bytes(zf.read(member))
                    restored.append(str(dest))
            else:
                # credentials.enc / config.yaml — restore alongside data_dir
                dest = restore_dir.parent / member
                if not member.endswith("/"):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(member))
                    restored.append(str(dest))
    return restored


def _prune_old_backups(drive, backup_folder_id: str, retention_days: int) -> int:
    """Delete backups older than retention_days. Returns count deleted."""
    if retention_days <= 0:
        return 0

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=retention_days)
    files = drive.list_folder(backup_folder_id)
    deleted = 0

    for f in files:
        name = f.get("name", "")
        if not (name.startswith(_BACKUP_PREFIX) and name.endswith(".zip")):
            continue
        # Parse date from filename: backup-YYYY-MM-DD-HHMMSS.zip
        date_str = name.removeprefix(_BACKUP_PREFIX).removesuffix(".zip")
        try:
            file_dt = datetime.strptime(date_str, "%Y-%m-%d-%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if file_dt < cutoff:
            try:
                drive.delete_file(f["id"])
                log.info(f"Pruned old backup: {name}")
                deleted += 1
            except Exception as exc:
                log.warning(f"Could not prune {name}: {exc}")

    return deleted


def _update_backup_log(data_dir: Path, backup_name: str, timestamp: datetime, size_bytes: int, file_count: int) -> None:
    """Append a record to the local backup log."""
    import json
    from postmule.data._io import atomic_write

    log_path = data_dir / _BACKUP_LOG_FILE
    records: list[dict] = []
    if log_path.exists():
        try:
            records = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            records = []

    records.append({
        "backup_name": backup_name,
        "timestamp": timestamp.isoformat(),
        "size_bytes": size_bytes,
        "file_count": file_count,
    })

    # Keep only the last 365 records
    records = records[-365:]
    atomic_write(log_path, json.dumps(records, indent=2, default=str))
