"""
Gap Detector — finds date gaps in email processing history (weekly run).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

from postmule.data.run_log import load_run_log

log = logging.getLogger("postmule.integrity.gap_detector")


def find_processing_gaps(
    data_dir: Path,
    lookback_days: int = 30,
) -> list[str]:
    """
    Find dates in the last N days where no run was recorded.

    Returns:
        List of date strings (YYYY-MM-DD) with no recorded run.
    """
    run_log = load_run_log(data_dir)
    processed_dates = set()

    for run in run_log:
        start = run.get("start_time", "")
        if start and len(start) >= 10:
            processed_dates.add(start[:10])

    today = date.today()
    gaps = []
    for i in range(1, lookback_days + 1):
        check_date = (today - timedelta(days=i)).isoformat()
        if check_date not in processed_dates:
            gaps.append(check_date)

    if gaps:
        log.warning(
            f"Gap detector found {len(gaps)} day(s) with no run in the last {lookback_days} days.\n"
            f"Missing dates: {', '.join(gaps[:10])}{'...' if len(gaps) > 10 else ''}\n"
            "Run 'postmule retroactive' to reprocess missing days."
        )
    else:
        log.info(f"Gap detector: no gaps found in the last {lookback_days} days.")

    return gaps
