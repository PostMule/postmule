"""
Integrity Verifier — verifies Drive file counts match JSON data counts (weekly run).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from postmule.data import bills as bills_data
from postmule.data import notices as notices_data
from postmule.data import forward_to_me as ftm_data

log = logging.getLogger("postmule.integrity.integrity_verifier")


def run_integrity_check(
    drive,
    folder_ids: dict[str, str],
    data_dir: Path,
) -> dict[str, Any]:
    """
    Compare Drive folder file counts against JSON record counts.

    Returns:
        Dict with per-folder comparison results and overall 'ok' flag.
    """
    results = {}
    overall_ok = True

    checks = [
        ("bills", "Bills", bills_data.load_bills(data_dir)),
        ("notices", "Notices", notices_data.load_notices(data_dir)),
        ("forward_to_me", "ForwardToMe", ftm_data.load_forward_to_me(data_dir)),
    ]

    for folder_key, label, json_records in checks:
        folder_id = folder_ids.get(folder_key)
        if not folder_id:
            results[folder_key] = {"ok": True, "note": "folder not configured"}
            continue

        try:
            drive_files = drive.list_folder(folder_id)
            drive_count = len([f for f in drive_files if f.get("mimeType") != "application/vnd.google-apps.folder"])
            json_count = len(json_records)

            ok = drive_count == json_count
            if not ok:
                overall_ok = False
                log.warning(
                    f"Integrity mismatch in {label}: "
                    f"Drive has {drive_count} files, JSON has {json_count} records."
                )
            else:
                log.debug(f"Integrity OK: {label} ({drive_count} files)")

            results[folder_key] = {
                "ok": ok,
                "drive_count": drive_count,
                "json_count": json_count,
            }
        except Exception as exc:
            results[folder_key] = {"ok": False, "error": str(exc)}
            overall_ok = False
            log.error(f"Integrity check failed for {label}: {exc}")

    return {"ok": overall_ok, "details": results}
