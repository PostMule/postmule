"""Unit tests for postmule.agents.summary."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from postmule.agents.summary import (
    _build_summary_html,
    _days_until,
    _pending_bills_section,
    send_daily_summary,
    send_urgent_alert,
)


class TestDaysUntil:
    def test_returns_none_for_empty_string(self):
        assert _days_until("") is None

    def test_returns_none_for_invalid_date(self):
        assert _days_until("not-a-date") is None

    def test_returns_correct_days_future(self):
        future = (date.today() + timedelta(days=10)).isoformat()
        result = _days_until(future)
        assert result == 10

    def test_returns_negative_for_past(self):
        past = (date.today() - timedelta(days=5)).isoformat()
        result = _days_until(past)
        assert result == -5

    def test_returns_zero_for_today(self):
        assert _days_until(date.today().isoformat()) == 0


class TestBuildSummaryHtml:
    def test_returns_string(self):
        html = _build_summary_html(
            today="2025-01-01",
            stats={"status": "success", "pdfs_processed": 3, "bills": 1, "notices": 2},
            items=[],
            pending_bills=[],
            api_usage={"requests": 10, "request_limit": 1400, "tokens": 5000, "token_limit": 900000},
        )
        assert isinstance(html, str)
        assert "PostMule" in html or "Post" in html

    def test_includes_stat_counts(self):
        html = _build_summary_html(
            today="2025-01-01",
            stats={"bills": 3, "notices": 7, "forward_to_me": 0, "junk": 2, "needs_review": 1},
            items=[],
            pending_bills=[],
            api_usage={},
        )
        assert "3" in html
        assert "7" in html

    def test_includes_mail_items(self):
        items = [{"category": "Bill", "sender": "ATT", "summary": "Monthly bill", "processed_date": "2025-01-01"}]
        html = _build_summary_html(
            today="2025-01-01",
            stats={},
            items=items,
            pending_bills=[],
            api_usage={},
        )
        assert "ATT" in html
        assert "Monthly bill" in html

    def test_includes_pending_bills(self):
        pending_bills = [{"sender": "Visa", "amount_due": 50.00, "due_date": "2025-04-01"}]
        html = _build_summary_html(
            today="2025-01-01",
            stats={},
            items=[],
            pending_bills=pending_bills,
            api_usage={},
        )
        assert "Visa" in html
        assert "50.00" in html

    def test_item_with_amount_and_due_date(self):
        items = [{
            "category": "Bill", "sender": "Gas", "summary": "Gas bill",
            "amount_due": 75.50, "due_date": "2025-04-15", "processed_date": "2025-01-01"
        }]
        html = _build_summary_html(
            today="2025-01-01",
            stats={},
            items=items,
            pending_bills=[],
            api_usage={},
        )
        assert "75.50" in html

    def test_api_usage_displayed(self):
        html = _build_summary_html(
            today="2025-01-01",
            stats={},
            items=[],
            pending_bills=[],
            api_usage={"requests": 42, "request_limit": 1400, "tokens": 1000, "token_limit": 900000, "estimated_cost_usd": 0.0},
        )
        assert "42" in html
        assert "1400" in html


class TestPendingBillsSection:
    def test_contains_rows_html(self):
        rows = "<tr><td>Test</td></tr>"
        result = _pending_bills_section(rows)
        assert "Test" in result
        assert "Pending Bills" in result


class TestSendDailySummaryDryRun:
    def test_dry_run_does_not_send(self):
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_daily_summary(
                smtp_config={},
                alert_email="test@example.com",
                run_stats={},
                processed_items=[],
                pending_bills=[],
                api_usage={},
                dry_run=True,
            )
            mock_send.assert_not_called()

    def test_send_calls_send_email(self):
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_daily_summary(
                smtp_config={"host": "smtp.gmail.com"},
                alert_email="test@example.com",
                run_stats={"status": "success"},
                processed_items=[],
                pending_bills=[],
                api_usage={},
                dry_run=False,
            )
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            assert "test@example.com" in call_args[0]


class TestSendUrgentAlert:
    def test_does_nothing_for_empty_items(self):
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_urgent_alert({}, "test@example.com", [])
            mock_send.assert_not_called()

    def test_sends_for_forward_to_me_items(self):
        with patch("postmule.agents.summary._send_email") as mock_send:
            items = [{"sender": "Visa", "summary": "Credit card", "date_received": "2025-01-01"}]
            send_urgent_alert({}, "alert@example.com", items)
            mock_send.assert_called_once()
            subject = mock_send.call_args[0][2]
            assert "URGENT" in subject
            html = mock_send.call_args[0][3]
            assert "Visa" in html
