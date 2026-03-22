"""
Run Monitor — verifies the daily run completed and alerts if missed.

Checks the run_log.json to ensure a run occurred within the expected window.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

from postmule.data.run_log import get_last_run

log = logging.getLogger("postmule.integrity.run_monitor")


def check_run_completed(data_dir: Path, max_hours_late: int = 4) -> dict:
    """
    Check if the most recent run completed successfully within the expected window.

    Args:
        data_dir:      Path to JSON data directory.
        max_hours_late: Alert if last run was more than this many hours ago.

    Returns:
        Dict with 'ok': bool, 'message': str.
    """
    from datetime import datetime, timezone

    last = get_last_run(data_dir)

    if not last:
        return {
            "ok": False,
            "message": (
                "No runs found in run_log.json.\n"
                "PostMule may not have run yet, or the data directory is wrong."
            ),
        }

    end_time_str = last.get("end_time", "")
    if not end_time_str:
        return {
            "ok": False,
            "message": f"Last run (ID {last.get('run_id','?')}) has no end_time — it may have crashed.",
        }

    try:
        end_time = datetime.fromisoformat(end_time_str)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
    except ValueError:
        return {"ok": False, "message": f"Unparseable end_time in run log: {end_time_str}"}

    now = datetime.now(tz=timezone.utc)
    hours_ago = (now - end_time).total_seconds() / 3600

    if last.get("status") == "failed":
        return {
            "ok": False,
            "message": (
                f"Last run FAILED at {end_time_str}.\n"
                f"Errors: {'; '.join(last.get('errors', []))}"
            ),
        }

    if hours_ago > max_hours_late:
        return {
            "ok": False,
            "message": (
                f"Last successful run was {hours_ago:.1f} hours ago (at {end_time_str}).\n"
                f"Expected at most {max_hours_late} hours ago.\n"
                "Check Windows Task Scheduler to see if the task ran."
            ),
        }

    log.debug(f"Run monitor OK: last run {hours_ago:.1f}h ago, status={last.get('status')}")
    return {"ok": True, "message": f"Last run {hours_ago:.1f}h ago — {last.get('status')}"}
