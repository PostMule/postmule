"""Unit tests for postmule.agents.summary."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from postmule.agents.summary import (
    _build_email_context,
    _build_summary_html,
    _days_until,
    _html_to_text,
    _pending_bills_section,
    send_bill_due_alert,
    send_daily_summary,
    send_pipeline_failure_alert,
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
        assert "2025-01-01" in html  # processed_date shown in Bill detail

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
        assert "1,400" in html


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


class TestBuildEmailContext:
    def _ctx(self, stats=None, items=None, pending=None, api_usage=None, today=None):
        return _build_email_context(
            today=today or date.today().isoformat(),
            stats=stats or {},
            items=items or [],
            pending_bills=pending or [],
            api_usage=api_usage or {},
        )

    def test_is_quiet_when_nothing_present(self):
        ctx = self._ctx()
        assert ctx["is_quiet"] is True

    def test_is_quiet_false_when_items_present(self):
        ctx = self._ctx(items=[{"category": "Bill", "sender": "ATT", "processed_date": "2025-01-01"}])
        assert ctx["is_quiet"] is False

    def test_forward_to_me_in_action_items_with_urgent(self):
        items = [{"category": "ForwardToMe", "sender": "IRS", "summary": "Tax form", "processed_date": "2025-01-01"}]
        ctx = self._ctx(items=items)
        assert any(a["urgent"] for a in ctx["action_items"])
        senders = [a["sender"] for a in ctx["action_items"]]
        assert "IRS" in senders

    def test_overdue_pending_bill_in_action_items(self):
        past = (date.today() - timedelta(days=3)).isoformat()
        pending = [{"sender": "Visa", "due_date": past, "amount_due": 100.0}]
        ctx = self._ctx(pending=pending)
        assert any("overdue" in a["detail"].lower() for a in ctx["action_items"])

    def test_non_overdue_pending_bill_stays_in_pending_items(self):
        future = (date.today() + timedelta(days=5)).isoformat()
        pending = [{"sender": "Visa", "due_date": future, "amount_due": 100.0}]
        ctx = self._ctx(pending=pending)
        assert len(ctx["pending_items"]) == 1
        assert not ctx["action_items"]

    def test_bill_detail_due_today(self):
        today_str = date.today().isoformat()
        items = [{"category": "Bill", "sender": "ATT", "due_date": today_str, "processed_date": today_str}]
        ctx = self._ctx(items=items)
        details = [i["detail"] for i in ctx["new_items"]]
        assert any("Due today" in d for d in details)

    def test_bill_detail_due_tomorrow(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        items = [{"category": "Bill", "sender": "ATT", "due_date": tomorrow, "processed_date": date.today().isoformat()}]
        ctx = self._ctx(items=items)
        details = [i["detail"] for i in ctx["new_items"]]
        assert any("due tomorrow" in d for d in details)

    def test_bill_detail_days_remaining(self):
        future = (date.today() + timedelta(days=7)).isoformat()
        items = [{"category": "Bill", "sender": "ATT", "due_date": future, "processed_date": date.today().isoformat()}]
        ctx = self._ctx(items=items)
        details = [i["detail"] for i in ctx["new_items"]]
        assert any("7 days remaining" in d for d in details)

    def test_summary_sub_pluralization(self):
        ctx = self._ctx(stats={"bills": 1, "notices": 2})
        assert "1 bill" in ctx["summary_sub"]
        assert "2 notices" in ctx["summary_sub"]

    def test_api_summary_includes_key_fields(self):
        ctx = self._ctx(api_usage={
            "provider": "gemini",
            "requests": 5,
            "request_limit": 1400,
            "tokens": 500,
            "token_limit": 900000,
            "estimated_cost_usd": 0.0012,
        })
        s = ctx["api_summary"]
        assert "Gemini" in s
        assert "5" in s
        assert "500" in s


class TestHtmlToText:
    def test_br_becomes_newline(self):
        assert "\n" in _html_to_text("hello<br>world")

    def test_tags_stripped(self):
        result = _html_to_text("<b>bold</b> text")
        assert "<b>" not in result
        assert "bold" in result

    def test_html_entities_decoded(self):
        result = _html_to_text("a&mdash;b &bull; &amp; &nbsp;c")
        assert "—" in result
        assert "•" in result
        assert "&" in result

    def test_consecutive_blank_lines_collapsed(self):
        result = _html_to_text("a\n\n\n\nb")
        assert "\n\n\n" not in result


class TestSendBillDueAlert:
    def _future(self, days):
        return (date.today() + timedelta(days=days)).isoformat()

    def test_paid_bills_excluded(self):
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(
                smtp_config={},
                alert_email="a@b.com",
                all_bills=[{"sender": "X", "due_date": self._future(2), "amount_due": 10, "status": "paid"}],
                dry_run=True,
            )
        mock_send.assert_not_called()

    def test_matched_bills_excluded(self):
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(
                smtp_config={},
                alert_email="a@b.com",
                all_bills=[{"sender": "X", "due_date": self._future(2), "amount_due": 10, "status": "matched"}],
                dry_run=True,
            )
        mock_send.assert_not_called()

    def test_bills_outside_window_excluded(self):
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(
                smtp_config={},
                alert_email="a@b.com",
                all_bills=[{"sender": "X", "due_date": self._future(30), "amount_due": 10}],
                alert_days=7,
                dry_run=True,
            )
        mock_send.assert_not_called()

    def test_recently_alerted_bill_skipped(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(
                smtp_config={},
                alert_email="a@b.com",
                all_bills=[{
                    "sender": "X", "due_date": self._future(3), "amount_due": 10,
                    "alert_sent_date": yesterday,
                }],
                alert_interval_days=3,
                dry_run=True,
            )
        mock_send.assert_not_called()

    def test_dry_run_does_not_call_smtp(self):
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(
                smtp_config={},
                alert_email="a@b.com",
                all_bills=[{"sender": "X", "due_date": self._future(2), "amount_due": 10}],
                dry_run=True,
            )
        mock_send.assert_not_called()


class TestSendPipelineFailureAlert:
    def test_calls_send_email(self):
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_pipeline_failure_alert(
                smtp_config={"host": "smtp.gmail.com"},
                alert_email="alert@example.com",
                error_messages=["Provider init failed: no credentials"],
            )
        mock_send.assert_called_once()

    def test_subject_contains_failed(self):
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_pipeline_failure_alert(
                smtp_config={},
                alert_email="alert@example.com",
                error_messages=["some error"],
            )
        subject = mock_send.call_args[0][2]
        assert "failed" in subject.lower()

    def test_html_contains_error_message(self):
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_pipeline_failure_alert(
                smtp_config={},
                alert_email="alert@example.com",
                error_messages=["DriveProvider: invalid credentials"],
            )
        html = mock_send.call_args[0][3]
        assert "DriveProvider: invalid credentials" in html

    def test_html_contains_multiple_errors(self):
        errors = ["Error one", "Error two"]
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_pipeline_failure_alert(
                smtp_config={},
                alert_email="alert@example.com",
                error_messages=errors,
            )
        html = mock_send.call_args[0][3]
        assert "Error one" in html
        assert "Error two" in html

    def test_recipient_passed_correctly(self):
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_pipeline_failure_alert(
                smtp_config={"host": "smtp.gmail.com"},
                alert_email="dest@example.com",
                error_messages=["err"],
            )
        to_addr = mock_send.call_args[0][1]
        assert to_addr == "dest@example.com"
