"""
Duplicate Detector — finds duplicate PDFs using SHA-256 hashing.

Compares all files in Drive against a local hash database.
Moves duplicates to the /Duplicates folder.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("postmule.integrity.duplicate_detector")

_HASHES_FILE = "hashes.json"


def load_hashes(data_dir: Path) -> dict[str, str]:
    """Load existing hash -> drive_file_id map."""
    path = data_dir / _HASHES_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_hashes(data_dir: Path, hashes: dict[str, str]) -> None:
    path = data_dir / _HASHES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hashes, indent=2, ensure_ascii=False), encoding="utf-8")


def register_file_hash(data_dir: Path, sha256: str, drive_file_id: str) -> None:
    """Record that a file with this hash was uploaded."""
    hashes = load_hashes(data_dir)
    hashes[sha256] = drive_file_id
    save_hashes(data_dir, hashes)


def is_duplicate(data_dir: Path, sha256: str) -> tuple[bool, str | None]:
    """
    Check if a hash already exists in the database.

    Returns:
        (True, original_drive_id) if duplicate, (False, None) otherwise.
    """
    hashes = load_hashes(data_dir)
    if sha256 in hashes:
        return True, hashes[sha256]
    return False, None


def find_duplicates_in_folder(
    drive_files: list[dict[str, Any]],
    data_dir: Path,
) -> list[dict[str, Any]]:
    """
    Scan a list of Drive file metadata for duplicates.

    Args:
        drive_files: List of dicts with 'id', 'name', 'md5Checksum'.
        data_dir:    Path to JSON data directory (for hash storage).

    Returns:
        List of duplicate file dicts.
    """
    seen: dict[str, str] = {}  # md5 -> first file_id
    duplicates = []

    for f in drive_files:
        md5 = f.get("md5Checksum", "")
        if not md5:
            continue
        if md5 in seen:
            duplicates.append({**f, "original_id": seen[md5]})
            log.info(f"Duplicate found: {f['name']} (md5={md5[:8]}...)")
        else:
            seen[md5] = f["id"]

    return duplicates


def run_duplicate_detection(
    drive,           # DriveProvider
    folder_ids: dict[str, str],
    data_dir: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Scan all content folders for duplicates and move them to /Duplicates.

    Returns:
        Summary dict with counts.
    """
    scan_folders = {
        k: v for k, v in folder_ids.items()
        if k not in ("root", "system", "data", "duplicates", "archive")
    }

    all_files = []
    for folder_key, folder_id in scan_folders.items():
        files = drive.list_folder(folder_id)
        for f in files:
            f["_folder_key"] = folder_key
            f["_folder_id"] = folder_id
        all_files.extend(files)

    duplicates = find_duplicates_in_folder(all_files, data_dir)

    moved = 0
    errors = []
    for dup in duplicates:
        if dry_run:
            log.info(f"[DRY RUN] Would move duplicate: {dup['name']}")
            moved += 1
            continue
        try:
            drive.move_file(
                file_id=dup["id"],
                new_folder_id=folder_ids["duplicates"],
                old_folder_id=dup["_folder_id"],
            )
            moved += 1
            log.info(f"Moved duplicate to /Duplicates: {dup['name']}")
        except Exception as exc:
            msg = f"Failed to move duplicate {dup['name']}: {exc}"
            log.error(msg)
            errors.append(msg)

    return {
        "files_scanned": len(all_files),
        "duplicates_found": len(duplicates),
        "moved": moved,
        "errors": errors,
    }
