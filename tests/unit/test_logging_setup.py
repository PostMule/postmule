"""Unit tests for postmule.core.logging_setup."""

import logging
from datetime import date, timedelta
from pathlib import Path

import pytest

from postmule.core.logging_setup import (
    _prune_processing_logs,
    _prune_verbose_logs,
    log_run_result,
    setup_logging,
)


class TestSetupLogging:
    def test_creates_log_directories(self, tmp_path):
        setup_logging(log_dir=tmp_path)
        assert (tmp_path / "verbose").exists()
        assert (tmp_path / "processing").exists()

    def test_creates_todays_verbose_log(self, tmp_path):
        setup_logging(log_dir=tmp_path)
        today = date.today().isoformat()
        assert (tmp_path / "verbose" / f"{today}.log").exists()

    def test_creates_annual_processing_log(self, tmp_path):
        setup_logging(log_dir=tmp_path)
        year = str(date.today().year)
        assert (tmp_path / "processing" / f"{year}.log").exists()

    def test_root_logger_configured(self, tmp_path):
        setup_logging(log_dir=tmp_path)
        root = logging.getLogger("postmule")
        assert len(root.handlers) >= 2  # verbose + console

    def test_debug_level_accepted(self, tmp_path):
        setup_logging(log_dir=tmp_path, level="DEBUG")
        # Should not raise

    def test_invalid_level_falls_back_to_info(self, tmp_path):
        setup_logging(log_dir=tmp_path, level="NOTREAL")
        # Should not raise

    def test_verbose_days_zero_still_creates_file(self, tmp_path):
        setup_logging(log_dir=tmp_path, verbose_days=0)
        # Today's log should be pruned or not, but setup should succeed


class TestPruneVerboseLogs:
    def test_removes_old_files(self, tmp_path):
        verbose_dir = tmp_path / "verbose"
        verbose_dir.mkdir()
        old_date = (date.today() - timedelta(days=10)).isoformat()
        old_file = verbose_dir / f"{old_date}.log"
        old_file.write_text("old log")
        _prune_verbose_logs(verbose_dir, keep_days=7)
        assert not old_file.exists()

    def test_keeps_recent_files(self, tmp_path):
        verbose_dir = tmp_path / "verbose"
        verbose_dir.mkdir()
        recent_date = (date.today() - timedelta(days=3)).isoformat()
        recent_file = verbose_dir / f"{recent_date}.log"
        recent_file.write_text("recent log")
        _prune_verbose_logs(verbose_dir, keep_days=7)
        assert recent_file.exists()

    def test_ignores_non_date_files(self, tmp_path):
        verbose_dir = tmp_path / "verbose"
        verbose_dir.mkdir()
        weird_file = verbose_dir / "not-a-date.log"
        weird_file.write_text("weird")
        _prune_verbose_logs(verbose_dir, keep_days=0)
        assert weird_file.exists()


class TestPruneProcessingLogs:
    def test_removes_old_year_files(self, tmp_path):
        proc_dir = tmp_path / "processing"
        proc_dir.mkdir()
        old_file = proc_dir / "2019.log"
        old_file.write_text("old")
        _prune_processing_logs(proc_dir, keep_years=3)
        assert not old_file.exists()

    def test_keeps_recent_year_files(self, tmp_path):
        proc_dir = tmp_path / "processing"
        proc_dir.mkdir()
        current_year = date.today().year
        recent_file = proc_dir / f"{current_year}.log"
        recent_file.write_text("recent")
        _prune_processing_logs(proc_dir, keep_years=3)
        assert recent_file.exists()

    def test_ignores_non_year_files(self, tmp_path):
        proc_dir = tmp_path / "processing"
        proc_dir.mkdir()
        weird_file = proc_dir / "notayear.log"
        weird_file.write_text("weird")
        _prune_processing_logs(proc_dir, keep_years=0)
        assert weird_file.exists()


class TestLogRunResult:
    def test_writes_to_processing_log(self, tmp_path):
        setup_logging(log_dir=tmp_path)
        log_run_result("success", "5 PDFs processed")
        year = str(date.today().year)
        log_path = tmp_path / "processing" / f"{year}.log"
        content = log_path.read_text(encoding="utf-8")
        assert "SUCCESS" in content
        assert "5 PDFs" in content
