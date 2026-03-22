"""
Extended unit tests for postmule/agents/summary.py

Covers: send_bill_due_alert, _html_to_text, _send_email
"""

from __future__ import annotations

import smtplib
import ssl
from datetime import date, timedelta
from unittest.mock import MagicMock, call, patch

import pytest

from postmule.agents.summary import (
    _html_to_text,
    _send_email,
    send_bill_due_alert,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bill(
    bill_id: str = "bill-1",
    sender: str = "Acme Corp",
    amount: float = 100.0,
    due_days_from_now: int = 5,
    status: str = "pending",
    alert_sent_date: str | None = None,
) -> dict:
    due_date = (date.today() + timedelta(days=due_days_from_now)).isoformat()
    bill = {
        "id": bill_id,
        "sender": sender,
        "amount_due": amount,
        "due_date": due_date,
        "status": status,
    }
    if alert_sent_date is not None:
        bill["alert_sent_date"] = alert_sent_date
    return bill


_SMTP_CONFIG = {
    "host": "smtp.gmail.com",
    "port": 587,
    "username": "user@example.com",
    "password": "pw",
    "from_address": "noreply@example.com",
}
_ALERT_EMAIL = "user@example.com"


# ---------------------------------------------------------------------------
# send_bill_due_alert — filtering
# ---------------------------------------------------------------------------

class TestSendBillDueAlertFiltering:
    def test_skips_paid_bills(self):
        bill = _make_bill(status="paid", due_days_from_now=2)
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(_SMTP_CONFIG, _ALERT_EMAIL, [bill])
        mock_send.assert_not_called()

    def test_skips_matched_bills(self):
        bill = _make_bill(status="matched", due_days_from_now=2)
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(_SMTP_CONFIG, _ALERT_EMAIL, [bill])
        mock_send.assert_not_called()

    def test_skips_bills_outside_alert_window(self):
        bill = _make_bill(due_days_from_now=15, status="pending")
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(_SMTP_CONFIG, _ALERT_EMAIL, [bill], alert_days=7)
        mock_send.assert_not_called()

    def test_skips_past_due_bills(self):
        bill = _make_bill(due_days_from_now=-1, status="pending")
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(_SMTP_CONFIG, _ALERT_EMAIL, [bill])
        mock_send.assert_not_called()

    def test_includes_bill_due_today(self):
        bill = _make_bill(due_days_from_now=0, status="pending")
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(_SMTP_CONFIG, _ALERT_EMAIL, [bill])
        mock_send.assert_called_once()

    def test_includes_bill_at_exact_alert_boundary(self):
        bill = _make_bill(due_days_from_now=7, status="pending")
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(_SMTP_CONFIG, _ALERT_EMAIL, [bill], alert_days=7)
        mock_send.assert_called_once()

    def test_skips_recently_alerted_bill(self):
        """Bill alerted 1 day ago with interval=3 should be skipped."""
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        bill = _make_bill(due_days_from_now=3, status="pending", alert_sent_date=yesterday)
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(_SMTP_CONFIG, _ALERT_EMAIL, [bill], alert_interval_days=3)
        mock_send.assert_not_called()

    def test_includes_bill_alerted_long_ago(self):
        """Bill alerted 5 days ago with interval=3 should be included again."""
        old_date = (date.today() - timedelta(days=5)).isoformat()
        bill = _make_bill(due_days_from_now=3, status="pending", alert_sent_date=old_date)
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(_SMTP_CONFIG, _ALERT_EMAIL, [bill], alert_interval_days=3)
        mock_send.assert_called_once()

    def test_handles_invalid_alert_sent_date_gracefully(self):
        """Invalid alert_sent_date should not prevent re-alerting."""
        bill = _make_bill(due_days_from_now=3, status="pending")
        bill["alert_sent_date"] = "not-a-date"
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(_SMTP_CONFIG, _ALERT_EMAIL, [bill])
        mock_send.assert_called_once()

    def test_returns_immediately_when_no_upcoming_bills(self):
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(_SMTP_CONFIG, _ALERT_EMAIL, [])
        mock_send.assert_not_called()


# ---------------------------------------------------------------------------
# send_bill_due_alert — dry_run
# ---------------------------------------------------------------------------

class TestSendBillDueAlertDryRun:
    def test_dry_run_does_not_call_send_email(self):
        bill = _make_bill(due_days_from_now=3)
        with patch("postmule.agents.summary._send_email") as mock_send:
            send_bill_due_alert(_SMTP_CONFIG, _ALERT_EMAIL, [bill], dry_run=True)
        mock_send.assert_not_called()

    def test_dry_run_logs_info(self, caplog):
        import logging
        bill = _make_bill(due_days_from_now=3)
        with caplog.at_level(logging.INFO, logger="postmule.agents.summary"):
            send_bill_due_alert(_SMTP_CONFIG, _ALERT_EMAIL, [bill], dry_run=True)
        assert "DRY RUN" in caplog.text


# ---------------------------------------------------------------------------
# send_bill_due_alert — marks alerted
# ---------------------------------------------------------------------------

class TestSendBillDueAlertMarkAlerted:
    def test_marks_bill_alerted_after_send(self, tmp_path):
        bill = _make_bill(bill_id="bill-99", due_days_from_now=2)

        with patch("postmule.agents.summary._send_email"), \
             patch("postmule.data.bills.mark_bill_alerted") as mock_mark:
            send_bill_due_alert(
                _SMTP_CONFIG, _ALERT_EMAIL, [bill],
                data_dir=tmp_path,
            )
            mock_mark.assert_called_once_with(tmp_path, "bill-99")

    def test_does_not_mark_alerted_when_no_data_dir(self):
        bill = _make_bill(due_days_from_now=2)
        with patch("postmule.agents.summary._send_email"):
            # Should not raise even without data_dir
            send_bill_due_alert(_SMTP_CONFIG, _ALERT_EMAIL, [bill], data_dir=None)


# ---------------------------------------------------------------------------
# send_bill_due_alert — email content
# ---------------------------------------------------------------------------

class TestSendBillDueAlertEmailContent:
    def test_subject_contains_bill_count_and_days(self):
        bill1 = _make_bill(due_days_from_now=2)
        bill2 = _make_bill(bill_id="bill-2", due_days_from_now=4)
        captured = {}

        def capture_send(smtp_config, to, subject, html):
            captured["subject"] = subject
            captured["html"] = html

        with patch("postmule.agents.summary._send_email", side_effect=capture_send):
            send_bill_due_alert(_SMTP_CONFIG, _ALERT_EMAIL, [bill1, bill2], alert_days=7)

        assert "2" in captured["subject"]
        assert "7" in captured["subject"]

    def test_html_contains_bill_sender_and_amount(self):
        bill = _make_bill(sender="Big Bank", amount=250.50, due_days_from_now=5)
        captured = {}

        def capture_send(smtp_config, to, subject, html):
            captured["html"] = html

        with patch("postmule.agents.summary._send_email", side_effect=capture_send):
            send_bill_due_alert(_SMTP_CONFIG, _ALERT_EMAIL, [bill])

        assert "Big Bank" in captured["html"]
        assert "250.50" in captured["html"]


# ---------------------------------------------------------------------------
# _html_to_text
# ---------------------------------------------------------------------------

class TestHtmlToText:
    def test_converts_br_to_newline(self):
        result = _html_to_text("line1<br>line2")
        assert "line1\nline2" in result

    def test_converts_br_self_closing_to_newline(self):
        result = _html_to_text("line1<br/>line2")
        assert "line1\nline2" in result

    def test_converts_br_with_space_to_newline(self):
        result = _html_to_text("line1<br />line2")
        assert "line1\nline2" in result

    def test_strips_html_tags(self):
        result = _html_to_text("<p>Hello <b>world</b></p>")
        assert result == "Hello world"

    def test_converts_mdash_entity(self):
        result = _html_to_text("foo &mdash; bar")
        assert "—" in result

    def test_converts_bull_entity(self):
        result = _html_to_text("&bull; item")
        assert "•" in result

    def test_converts_nbsp_entity(self):
        result = _html_to_text("Hello&nbsp;World")
        assert "Hello World" in result

    def test_converts_amp_entity(self):
        result = _html_to_text("A &amp; B")
        assert "A & B" in result

    def test_collapses_excessive_newlines(self):
        result = _html_to_text("a\n\n\n\nb")
        assert "\n\n\n" not in result

    def test_strips_leading_and_trailing_whitespace(self):
        result = _html_to_text("  <p>text</p>  ")
        assert result == "text"

    def test_empty_string_returns_empty(self):
        assert _html_to_text("") == ""

    def test_br_case_insensitive(self):
        result = _html_to_text("line1<BR>line2")
        assert "line1\nline2" in result


# ---------------------------------------------------------------------------
# _send_email
# ---------------------------------------------------------------------------

class TestSendEmail:
    def _make_mock_server(self):
        mock_server = MagicMock()
        mock_server.__enter__ = MagicMock(return_value=mock_server)
        mock_server.__exit__ = MagicMock(return_value=False)
        return mock_server

    def test_calls_ehlo_starttls_login_sendmail(self):
        mock_server = self._make_mock_server()

        with patch("smtplib.SMTP", return_value=mock_server), \
             patch("ssl.create_default_context", return_value=MagicMock()):
            _send_email(_SMTP_CONFIG, "to@example.com", "Subject", "<p>body</p>")

        mock_server.ehlo.assert_called_once()
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@example.com", "pw")
        mock_server.sendmail.assert_called_once()

    def test_connects_to_configured_host_and_port(self):
        mock_server = self._make_mock_server()

        with patch("smtplib.SMTP", return_value=mock_server) as mock_smtp, \
             patch("ssl.create_default_context", return_value=MagicMock()):
            _send_email(_SMTP_CONFIG, "to@example.com", "Subject", "<p>body</p>")

        mock_smtp.assert_called_once_with("smtp.gmail.com", 587)

    def test_sendmail_uses_from_address(self):
        mock_server = self._make_mock_server()

        with patch("smtplib.SMTP", return_value=mock_server), \
             patch("ssl.create_default_context", return_value=MagicMock()):
            _send_email(_SMTP_CONFIG, "to@example.com", "Subject", "<p>body</p>")

        call_args = mock_server.sendmail.call_args[0]
        assert call_args[0] == "noreply@example.com"
        assert call_args[1] == ["to@example.com"]

    def test_falls_back_to_to_address_when_no_from_in_config(self):
        config = {"host": "smtp.gmail.com", "port": 587, "username": "u", "password": "p"}
        mock_server = self._make_mock_server()

        with patch("smtplib.SMTP", return_value=mock_server), \
             patch("ssl.create_default_context", return_value=MagicMock()):
            _send_email(config, "to@example.com", "My Subject", "<p>body</p>")

        call_args = mock_server.sendmail.call_args[0]
        assert call_args[0] == "to@example.com"  # falls back to to_address

    def test_message_contains_both_plain_and_html_parts(self):
        mock_server = self._make_mock_server()
        sent_messages = []

        def capture_sendmail(from_addr, to_list, msg_str):
            sent_messages.append(msg_str)

        mock_server.sendmail.side_effect = capture_sendmail

        with patch("smtplib.SMTP", return_value=mock_server), \
             patch("ssl.create_default_context", return_value=MagicMock()):
            _send_email(_SMTP_CONFIG, "to@example.com", "Subject", "<p>Hello</p>")

        assert sent_messages
        msg_str = sent_messages[0]
        assert "text/plain" in msg_str
        assert "text/html" in msg_str

    def test_propagates_smtp_exception(self):
        mock_server = self._make_mock_server()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"auth failed")

        with patch("smtplib.SMTP", return_value=mock_server), \
             patch("ssl.create_default_context", return_value=MagicMock()):
            with pytest.raises(smtplib.SMTPAuthenticationError):
                _send_email(_SMTP_CONFIG, "to@example.com", "Subject", "<p>body</p>")
