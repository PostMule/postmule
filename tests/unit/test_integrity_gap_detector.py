"""Unit tests for postmule.agents.integrity.gap_detector."""

from datetime import date, timedelta

import pytest

from postmule.agents.integrity.gap_detector import find_processing_gaps
from postmule.data.run_log import append_run


class TestFindProcessingGaps:
    def test_all_gaps_when_no_runs(self, tmp_path):
        gaps = find_processing_gaps(tmp_path, lookback_days=7)
        assert len(gaps) == 7

    def test_no_gaps_when_all_days_covered(self, tmp_path):
        today = date.today()
        for i in range(1, 8):
            day = (today - timedelta(days=i)).isoformat()
            append_run(tmp_path, {"start_time": f"{day}T02:00:00", "status": "success"})
        gaps = find_processing_gaps(tmp_path, lookback_days=7)
        assert gaps == []

    def test_detects_specific_missing_day(self, tmp_path):
        today = date.today()
        # Cover all days except 3 days ago
        for i in [1, 2, 4, 5]:
            day = (today - timedelta(days=i)).isoformat()
            append_run(tmp_path, {"start_time": f"{day}T02:00:00", "status": "success"})
        gaps = find_processing_gaps(tmp_path, lookback_days=5)
        assert (today - timedelta(days=3)).isoformat() in gaps

    def test_lookback_days_respected(self, tmp_path):
        gaps = find_processing_gaps(tmp_path, lookback_days=3)
        assert len(gaps) == 3

    def test_today_not_included_in_gaps(self, tmp_path):
        today = date.today().isoformat()
        gaps = find_processing_gaps(tmp_path, lookback_days=7)
        assert today not in gaps
