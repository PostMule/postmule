"""
Unit tests for postmule/providers/notifications/email_notifier.py
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from postmule.providers.notifications.email_notifier import EmailNotifier


class TestEmailNotifierInit:
    def test_stores_smtp_config(self):
        config = {"host": "smtp.example.com", "port": 587}
        notifier = EmailNotifier(config)
        assert notifier.smtp_config is config

    def test_sets_default_from_address_when_not_in_config(self):
        config = {"host": "smtp.example.com"}
        notifier = EmailNotifier(config, from_address="noreply@example.com")
        assert notifier.smtp_config["from_address"] == "noreply@example.com"

    def test_does_not_override_from_address_already_in_config(self):
        config = {"host": "smtp.example.com", "from_address": "existing@example.com"}
        notifier = EmailNotifier(config, from_address="other@example.com")
        # setdefault only sets if key absent
        assert notifier.smtp_config["from_address"] == "existing@example.com"

    def test_default_from_address_is_empty_string_when_not_provided(self):
        config = {"host": "smtp.example.com"}
        notifier = EmailNotifier(config)
        assert notifier.smtp_config["from_address"] == ""


class TestEmailNotifierSend:
    def test_delegates_to_send_email(self):
        config = {"host": "smtp.example.com", "port": 587}
        notifier = EmailNotifier(config)

        # send() lazily imports _send_email from postmule.agents.summary
        with patch("postmule.agents.summary._send_email") as mock_send:
            notifier.send("to@example.com", "Subject", "<p>html</p>")
        mock_send.assert_called_once_with(config, "to@example.com", "Subject", "<p>html</p>")

    def test_send_logs_info_on_success(self, caplog):
        import logging
        config = {"host": "smtp.example.com"}
        notifier = EmailNotifier(config)

        with patch("postmule.agents.summary._send_email"):
            with caplog.at_level(logging.INFO, logger="postmule.notifications.email"):
                notifier.send("user@example.com", "Test Subject", "<p>body</p>")

        assert "user@example.com" in caplog.text
        assert "Test Subject" in caplog.text

    def test_send_propagates_exceptions_from_send_email(self):
        config = {"host": "smtp.example.com"}
        notifier = EmailNotifier(config)

        with patch("postmule.agents.summary._send_email", side_effect=OSError("SMTP failure")):
            with pytest.raises(OSError, match="SMTP failure"):
                notifier.send("to@example.com", "Subject", "<p>body</p>")
