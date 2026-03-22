"""
Logging setup for PostMule.

Two log streams:
  1. Verbose logs  — one file per day, rolling N-day window, DEBUG+ level.
                     Located at: <log_dir>/verbose/YYYY-MM-DD.log
  2. Processing log — one file per year, one line per run, INFO level.
                      Located at: <log_dir>/processing/YYYY.log

Human-readable error format:
  Every ERROR log includes:
    - Plain English title (what happened)
    - What the user should do
    - Technical detail (only in verbose log, not in processing log)
"""

from __future__ import annotations

import glob
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# Module-level logger for PostMule internals
log = logging.getLogger("postmule")


# ------------------------------------------------------------------
# Setup entry point
# ------------------------------------------------------------------

def setup_logging(
    log_dir: Path,
    verbose_days: int = 7,
    processing_years: int = 3,
    level: str = "INFO",
) -> None:
    """
    Configure all PostMule loggers. Call once at startup.

    Args:
        log_dir:          Root directory for log files (created if missing).
        verbose_days:     How many days of verbose logs to keep.
        processing_years: How many years of processing logs to keep.
        level:            Log level string: DEBUG | INFO | WARNING | ERROR.
    """
    log_dir = Path(log_dir)
    verbose_dir = log_dir / "verbose"
    processing_dir = log_dir / "processing"
    verbose_dir.mkdir(parents=True, exist_ok=True)
    processing_dir.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Root postmule logger
    root = logging.getLogger("postmule")
    root.setLevel(logging.DEBUG)  # handlers filter independently
    root.handlers.clear()

    # -- Verbose handler (daily file, DEBUG+) --
    today_str = date.today().isoformat()
    verbose_path = verbose_dir / f"{today_str}.log"
    verbose_handler = logging.FileHandler(verbose_path, encoding="utf-8")
    verbose_handler.setLevel(logging.DEBUG)
    verbose_handler.setFormatter(_verbose_formatter())
    root.addHandler(verbose_handler)

    # -- Console handler --
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(_console_formatter())
    root.addHandler(console_handler)

    # -- Processing log handler (separate logger, one line per run) --
    proc_logger = logging.getLogger("postmule.processing")
    proc_logger.propagate = False
    year_str = str(date.today().year)
    proc_path = processing_dir / f"{year_str}.log"
    proc_handler = logging.FileHandler(proc_path, encoding="utf-8")
    proc_handler.setLevel(logging.INFO)
    proc_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"))
    proc_logger.handlers.clear()
    proc_logger.addHandler(proc_handler)

    # Prune old files
    _prune_verbose_logs(verbose_dir, verbose_days)
    _prune_processing_logs(processing_dir, processing_years)


def log_run_result(status: str, summary: str) -> None:
    """Write a single line to the annual processing log."""
    proc_logger = logging.getLogger("postmule.processing")
    proc_logger.info(f"[{status.upper()}] {summary}")


# ------------------------------------------------------------------
# Formatters
# ------------------------------------------------------------------

def _verbose_formatter() -> logging.Formatter:
    return logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _console_formatter() -> logging.Formatter:
    return logging.Formatter(fmt="%(levelname)-8s %(message)s")


# ------------------------------------------------------------------
# Pruning
# ------------------------------------------------------------------

def _prune_verbose_logs(verbose_dir: Path, keep_days: int) -> None:
    cutoff = date.today() - timedelta(days=keep_days)
    for log_file in verbose_dir.glob("????-??-??.log"):
        try:
            file_date = date.fromisoformat(log_file.stem)
            if file_date < cutoff:
                log_file.unlink()
                log.debug(f"Pruned old verbose log: {log_file.name}")
        except ValueError:
            pass  # Non-standard filename — leave it alone


def _prune_processing_logs(processing_dir: Path, keep_years: int) -> None:
    cutoff_year = date.today().year - keep_years
    for log_file in processing_dir.glob("????.log"):
        try:
            file_year = int(log_file.stem)
            if file_year < cutoff_year:
                log_file.unlink()
                log.debug(f"Pruned old processing log: {log_file.name}")
        except ValueError:
            pass
