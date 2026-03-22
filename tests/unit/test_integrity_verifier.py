"""Unit tests for postmule.agents.integrity.integrity_verifier."""

from unittest.mock import MagicMock

import pytest

from postmule.agents.integrity.integrity_verifier import run_integrity_check
from postmule.data import bills as bills_data
from postmule.data import notices as notices_data


def _make_drive(files_per_folder=None):
    drive = MagicMock()
    if files_per_folder is not None:
        drive.list_folder.return_value = files_per_folder
    return drive


class TestRunIntegrityCheck:
    def test_ok_when_counts_match(self, tmp_path):
        # 1 bill in JSON, 1 file in Drive — use current year so load_bills finds it
        from datetime import date
        today = date.today().isoformat()
        bills_data.add_bill(tmp_path, {
            "date_received": today,
            "sender": "ATT",
            "amount_due": 94.0,
            "due_date": today,
            "status": "pending",
        })
        drive = _make_drive([{"id": "f1", "name": "bill.pdf", "mimeType": "application/pdf"}])
        result = run_integrity_check(
            drive=drive,
            folder_ids={"bills": "folder-bills"},
            data_dir=tmp_path,
        )
        assert result["ok"] is True
        assert result["details"]["bills"]["ok"] is True
        assert result["details"]["bills"]["drive_count"] == 1
        assert result["details"]["bills"]["json_count"] == 1

    def test_not_ok_when_counts_mismatch(self, tmp_path):
        # 0 bills in JSON, 1 file in Drive
        drive = _make_drive([{"id": "f1", "name": "bill.pdf", "mimeType": "application/pdf"}])
        result = run_integrity_check(
            drive=drive,
            folder_ids={"bills": "folder-bills"},
            data_dir=tmp_path,
        )
        assert result["ok"] is False
        assert result["details"]["bills"]["ok"] is False

    def test_skips_unconfigured_folder(self, tmp_path):
        drive = _make_drive([])
        result = run_integrity_check(
            drive=drive,
            folder_ids={},  # no folder IDs configured
            data_dir=tmp_path,
        )
        assert result["ok"] is True
        for val in result["details"].values():
            assert val.get("note") == "folder not configured"

    def test_drive_error_caught(self, tmp_path):
        drive = MagicMock()
        drive.list_folder.side_effect = Exception("API error")
        result = run_integrity_check(
            drive=drive,
            folder_ids={"bills": "folder-bills"},
            data_dir=tmp_path,
        )
        assert result["ok"] is False
        assert "error" in result["details"]["bills"]

    def test_folders_subfolder_excluded_from_count(self, tmp_path):
        # Drive returns a folder (should not be counted as a file)
        drive = _make_drive([
            {"id": "f1", "name": "bill.pdf", "mimeType": "application/pdf"},
            {"id": "sub", "name": "subfolder", "mimeType": "application/vnd.google-apps.folder"},
        ])
        bills_data.add_bill(tmp_path, {
            "date_received": "2025-01-01",
            "sender": "ATT",
            "amount_due": 10.0,
        })
        result = run_integrity_check(
            drive=drive,
            folder_ids={"bills": "folder-bills"},
            data_dir=tmp_path,
        )
        # 1 file (folder excluded) vs 1 JSON record
        assert result["details"]["bills"]["drive_count"] == 1
