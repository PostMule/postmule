"""Unit tests for postmule.agents.integrity.run_monitor."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from postmule.agents.integrity.run_monitor import check_run_completed
from postmule.data.run_log import append_run


def _write_run(data_dir, end_time_str, status="success"):
    entry = {
        "run_id": "test-run",
        "start_time": end_time_str,
        "end_time": end_time_str,
        "status": status,
        "errors": [],
    }
    append_run(data_dir, entry)


class TestCheckRunCompleted:
    def test_no_runs_returns_not_ok(self, tmp_path):
        result = check_run_completed(tmp_path)
        assert result["ok"] is False
        assert "No runs" in result["message"]

    def test_recent_success_returns_ok(self, tmp_path):
        now_str = datetime.now(tz=timezone.utc).isoformat()
        _write_run(tmp_path, now_str, status="success")
        result = check_run_completed(tmp_path, max_hours_late=4)
        assert result["ok"] is True

    def test_old_run_returns_not_ok(self, tmp_path):
        old = (datetime.now(tz=timezone.utc) - timedelta(hours=10)).isoformat()
        _write_run(tmp_path, old, status="success")
        result = check_run_completed(tmp_path, max_hours_late=4)
        assert result["ok"] is False
        assert "hours ago" in result["message"]

    def test_failed_run_returns_not_ok(self, tmp_path):
        now_str = datetime.now(tz=timezone.utc).isoformat()
        _write_run(tmp_path, now_str, status="failed")
        result = check_run_completed(tmp_path)
        assert result["ok"] is False
        assert "FAILED" in result["message"]

    def test_missing_end_time_returns_not_ok(self, tmp_path):
        entry = {"run_id": "x", "start_time": "2025-01-01T00:00:00", "status": "success"}
        append_run(tmp_path, entry)
        result = check_run_completed(tmp_path)
        assert result["ok"] is False
        assert "no end_time" in result["message"].lower() or "end_time" in result["message"]

    def test_unparseable_end_time_returns_not_ok(self, tmp_path):
        entry = {
            "run_id": "x",
            "start_time": "2025-01-01T00:00:00",
            "end_time": "not-a-date",
            "status": "success",
        }
        append_run(tmp_path, entry)
        result = check_run_completed(tmp_path)
        assert result["ok"] is False
