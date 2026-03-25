"""
Unit tests for postmule/agents/backup.py
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from postmule.agents.backup import (
    _create_zip,
    _extract_zip,
    _prune_old_backups,
    _update_backup_log,
    get_last_backup,
    list_backups,
    run_backup,
    run_restore,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_drive_mock(files=None):
    """Return a minimal DriveProvider mock."""
    drive = MagicMock()
    drive._get_or_create_folder.return_value = "folder-id-123"
    drive.list_folder.return_value = files or []
    drive.upload_bytes.return_value = "file-id-abc"
    return drive


def _make_cfg_mock(retention_days=180):
    cfg = MagicMock()
    cfg.get.side_effect = lambda *args, **kw: kw.get("default")
    # Specifically handle backup_retention_days
    def _cfg_get(section, key=None, default=None):
        if section == "data_protection" and key == "backup_retention_days":
            return retention_days
        if section == "storage":
            return [{"root_folder": "PostMule"}]
        return default
    cfg.get.side_effect = _cfg_get
    return cfg


# ---------------------------------------------------------------------------
# _create_zip
# ---------------------------------------------------------------------------

class TestCreateZip:
    def test_includes_json_files(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "bills_2025.json").write_text('{"a": 1}')
        (data_dir / "notices_2025.json").write_text('{"b": 2}')

        zip_bytes, file_list = _create_zip(data_dir, None, None)

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = set(zf.namelist())
        assert "data/bills_2025.json" in names
        assert "data/notices_2025.json" in names
        assert "data/bills_2025.json" in file_list

    def test_includes_config_yaml(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        config_path = tmp_path / "config.yaml"
        config_path.write_text("app:\n  dry_run: false\n")

        zip_bytes, file_list = _create_zip(data_dir, config_path, None)

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            assert "config.yaml" in zf.namelist()
        assert "config.yaml" in file_list

    def test_includes_credentials_enc(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        enc_path = tmp_path / "credentials.enc"
        enc_path.write_bytes(b"encrypted-data")

        zip_bytes, file_list = _create_zip(data_dir, None, enc_path)

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            assert "credentials.enc" in zf.namelist()
        assert "credentials.enc" in file_list

    def test_includes_nested_json(self, tmp_path):
        data_dir = tmp_path / "data"
        pending = data_dir / "pending"
        pending.mkdir(parents=True)
        (pending / "bill_matches.json").write_text("[]")

        zip_bytes, _ = _create_zip(data_dir, None, None)

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            assert "data/pending/bill_matches.json" in zf.namelist()

    def test_empty_data_dir(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        zip_bytes, file_list = _create_zip(data_dir, None, None)

        assert isinstance(zip_bytes, bytes)
        assert file_list == []

    def test_missing_data_dir(self, tmp_path):
        data_dir = tmp_path / "nonexistent"

        zip_bytes, file_list = _create_zip(data_dir, None, None)

        assert isinstance(zip_bytes, bytes)
        assert file_list == []


# ---------------------------------------------------------------------------
# _extract_zip
# ---------------------------------------------------------------------------

class TestExtractZip:
    def _make_zip(self, files: dict[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def test_restores_data_files(self, tmp_path):
        restore_dir = tmp_path / "data"
        restore_dir.mkdir()
        zip_bytes = self._make_zip({"data/bills_2025.json": b'{"test":1}'})

        restored = _extract_zip(zip_bytes, restore_dir)

        target = restore_dir / "bills_2025.json"
        assert target.exists()
        assert target.read_bytes() == b'{"test":1}'
        assert str(target) in restored

    def test_restores_credentials_enc(self, tmp_path):
        restore_dir = tmp_path / "data"
        restore_dir.mkdir()
        zip_bytes = self._make_zip({"credentials.enc": b"secret"})

        restored = _extract_zip(zip_bytes, restore_dir)

        dest = tmp_path / "credentials.enc"
        assert dest.exists()
        assert dest.read_bytes() == b"secret"

    def test_creates_parent_dirs(self, tmp_path):
        restore_dir = tmp_path / "data"
        restore_dir.mkdir()
        zip_bytes = self._make_zip({"data/pending/bill_matches.json": b"[]"})

        _extract_zip(zip_bytes, restore_dir)

        assert (restore_dir / "pending" / "bill_matches.json").exists()

    def test_skips_directory_entries(self, tmp_path):
        restore_dir = tmp_path / "data"
        restore_dir.mkdir()
        zip_bytes = self._make_zip({"data/": b""})

        restored = _extract_zip(zip_bytes, restore_dir)

        assert restored == []


# ---------------------------------------------------------------------------
# _prune_old_backups
# ---------------------------------------------------------------------------

class TestPruneOldBackups:
    def test_deletes_old_backups(self):
        drive = _make_drive_mock(files=[
            {"id": "old1", "name": "backup-2020-01-01-020000.zip"},
            {"id": "old2", "name": "backup-2019-06-15-020000.zip"},
            {"id": "new1", "name": "backup-2026-03-20-020000.zip"},
        ])

        count = _prune_old_backups(drive, "folder-id", retention_days=180)

        assert count == 2
        assert drive.delete_file.call_count == 2

    def test_keeps_recent_backups(self):
        drive = _make_drive_mock(files=[
            {"id": "new1", "name": "backup-2026-03-22-020000.zip"},
            {"id": "new2", "name": "backup-2026-03-21-020000.zip"},
        ])

        count = _prune_old_backups(drive, "folder-id", retention_days=180)

        assert count == 0
        drive.delete_file.assert_not_called()

    def test_skips_zero_retention(self):
        drive = _make_drive_mock(files=[
            {"id": "old1", "name": "backup-2020-01-01-020000.zip"},
        ])

        count = _prune_old_backups(drive, "folder-id", retention_days=0)

        assert count == 0
        drive.delete_file.assert_not_called()

    def test_ignores_non_backup_files(self):
        drive = _make_drive_mock(files=[
            {"id": "x1", "name": "some-other-file.txt"},
            {"id": "x2", "name": "data.json"},
        ])

        count = _prune_old_backups(drive, "folder-id", retention_days=180)

        assert count == 0

    def test_handles_malformed_filename(self):
        drive = _make_drive_mock(files=[
            {"id": "x1", "name": "backup-not-a-date.zip"},
        ])

        count = _prune_old_backups(drive, "folder-id", retention_days=1)

        assert count == 0

    def test_handles_delete_error_gracefully(self):
        drive = _make_drive_mock(files=[
            {"id": "old1", "name": "backup-2020-01-01-020000.zip"},
        ])
        drive.delete_file.side_effect = Exception("Drive error")

        count = _prune_old_backups(drive, "folder-id", retention_days=180)

        assert count == 0  # error caught, not raised


# ---------------------------------------------------------------------------
# _update_backup_log / get_last_backup
# ---------------------------------------------------------------------------

class TestBackupLog:
    def test_creates_log_file(self, tmp_path):
        now = datetime(2026, 3, 23, 2, 0, 0, tzinfo=timezone.utc)
        _update_backup_log(tmp_path, "backup-2026-03-23-020000.zip", now, 12345, 10)

        log_path = tmp_path / "backup_log.json"
        assert log_path.exists()
        records = json.loads(log_path.read_text())
        assert len(records) == 1
        assert records[0]["backup_name"] == "backup-2026-03-23-020000.zip"
        assert records[0]["size_bytes"] == 12345
        assert records[0]["file_count"] == 10

    def test_appends_to_existing_log(self, tmp_path):
        now = datetime(2026, 3, 23, 2, 0, 0, tzinfo=timezone.utc)
        _update_backup_log(tmp_path, "backup-2026-03-22-020000.zip", now, 100, 5)
        _update_backup_log(tmp_path, "backup-2026-03-23-020000.zip", now, 200, 7)

        log_path = tmp_path / "backup_log.json"
        records = json.loads(log_path.read_text())
        assert len(records) == 2
        assert records[-1]["backup_name"] == "backup-2026-03-23-020000.zip"

    def test_get_last_backup_returns_last_record(self, tmp_path):
        now = datetime(2026, 3, 23, 2, 0, 0, tzinfo=timezone.utc)
        _update_backup_log(tmp_path, "backup-2026-03-22-020000.zip", now, 100, 5)
        _update_backup_log(tmp_path, "backup-2026-03-23-020000.zip", now, 200, 7)

        last = get_last_backup(tmp_path)

        assert last["backup_name"] == "backup-2026-03-23-020000.zip"

    def test_get_last_backup_returns_none_when_no_log(self, tmp_path):
        assert get_last_backup(tmp_path) is None

    def test_get_last_backup_handles_corrupt_log(self, tmp_path):
        (tmp_path / "backup_log.json").write_text("not valid json{{")
        assert get_last_backup(tmp_path) is None

    def test_log_trims_to_365_records(self, tmp_path):
        now = datetime(2026, 3, 23, 2, 0, 0, tzinfo=timezone.utc)
        for i in range(370):
            _update_backup_log(tmp_path, f"backup-2026-01-{i:04d}-020000.zip", now, 100, 5)

        log_path = tmp_path / "backup_log.json"
        records = json.loads(log_path.read_text())
        assert len(records) == 365


# ---------------------------------------------------------------------------
# run_backup (integration-style with mocked drive)
# ---------------------------------------------------------------------------

class TestRunBackup:
    def test_successful_backup(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "bills_2026.json").write_text("[]")

        cfg = _make_cfg_mock()
        drive = _make_drive_mock()

        with patch("postmule.agents.backup._build_drive", return_value=drive):
            result = run_backup(cfg, {}, data_dir, None, None, dry_run=False)

        assert result["status"] == "ok"
        assert result["backup_name"].startswith("backup-")
        assert result["backup_name"].endswith(".zip")
        assert result["bytes_uploaded"] > 0
        assert "data/bills_2026.json" in result["files_included"]
        drive.upload_bytes.assert_called_once()

    def test_dry_run_skips_upload(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        cfg = _make_cfg_mock()
        drive = _make_drive_mock()

        with patch("postmule.agents.backup._build_drive", return_value=drive):
            result = run_backup(cfg, {}, data_dir, None, None, dry_run=True)

        assert result["status"] == "ok"
        drive.upload_bytes.assert_not_called()
        assert result["pruned_count"] == 0

    def test_drive_connection_failure(self, tmp_path):
        cfg = _make_cfg_mock()

        with patch("postmule.agents.backup._build_drive", side_effect=Exception("auth failed")):
            result = run_backup(cfg, {}, tmp_path / "data", None, None)

        assert result["status"] == "error"
        assert "auth failed" in result["error"]

    def test_upload_failure_returns_error(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        cfg = _make_cfg_mock()
        drive = _make_drive_mock()
        drive.upload_bytes.side_effect = Exception("quota exceeded")

        with patch("postmule.agents.backup._build_drive", return_value=drive):
            result = run_backup(cfg, {}, data_dir, None, None)

        assert result["status"] == "error"
        assert "quota exceeded" in result["error"]


# ---------------------------------------------------------------------------
# run_restore
# ---------------------------------------------------------------------------

class TestRunRestore:
    def _make_backup_zip(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("data/bills_2026.json", "[]")
        return buf.getvalue()

    def test_restore_latest(self, tmp_path):
        cfg = _make_cfg_mock()
        zip_bytes = self._make_backup_zip()
        drive = _make_drive_mock(files=[
            {"id": "f1", "name": "backup-2026-03-22-020000.zip", "size": "1000"},
            {"id": "f2", "name": "backup-2026-03-23-020000.zip", "size": "1200"},
        ])
        drive.download_file.return_value = zip_bytes
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        with patch("postmule.agents.backup._build_drive", return_value=drive):
            result = run_restore(cfg, {}, "latest", data_dir)

        assert result["status"] == "ok"
        assert result["backup_name"] == "backup-2026-03-23-020000.zip"
        assert len(result["files_restored"]) > 0

    def test_restore_specific_backup(self, tmp_path):
        cfg = _make_cfg_mock()
        zip_bytes = self._make_backup_zip()
        drive = _make_drive_mock(files=[
            {"id": "f1", "name": "backup-2026-03-22-020000.zip", "size": "1000"},
        ])
        drive.download_file.return_value = zip_bytes
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        with patch("postmule.agents.backup._build_drive", return_value=drive):
            result = run_restore(cfg, {}, "backup-2026-03-22-020000.zip", data_dir)

        assert result["status"] == "ok"
        assert result["backup_name"] == "backup-2026-03-22-020000.zip"

    def test_restore_backup_not_found(self, tmp_path):
        cfg = _make_cfg_mock()
        drive = _make_drive_mock(files=[
            {"id": "f1", "name": "backup-2026-03-22-020000.zip", "size": "1000"},
        ])

        with patch("postmule.agents.backup._build_drive", return_value=drive):
            result = run_restore(cfg, {}, "backup-2026-01-01-020000.zip", tmp_path / "data")

        assert result["status"] == "error"
        assert "not found" in result["error"]

    def test_restore_no_backups_in_cloud(self, tmp_path):
        cfg = _make_cfg_mock()
        drive = _make_drive_mock(files=[])

        with patch("postmule.agents.backup._build_drive", return_value=drive):
            result = run_restore(cfg, {}, "latest", tmp_path / "data")

        assert result["status"] == "error"
        assert "No backups found" in result["error"]

    def test_restore_dry_run_skips_extraction(self, tmp_path):
        cfg = _make_cfg_mock()
        drive = _make_drive_mock(files=[
            {"id": "f1", "name": "backup-2026-03-23-020000.zip", "size": "1000"},
        ])
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        with patch("postmule.agents.backup._build_drive", return_value=drive):
            result = run_restore(cfg, {}, "latest", data_dir, dry_run=True)

        assert result["status"] == "ok"
        assert result["files_restored"] == []
        drive.download_file.assert_not_called()


# ---------------------------------------------------------------------------
# list_backups
# ---------------------------------------------------------------------------

class TestListBackups:
    def test_returns_sorted_list(self):
        cfg = _make_cfg_mock()
        drive = _make_drive_mock(files=[
            {"id": "f1", "name": "backup-2026-03-21-020000.zip", "size": "1000"},
            {"id": "f2", "name": "backup-2026-03-23-020000.zip", "size": "1200"},
            {"id": "f3", "name": "backup-2026-03-22-020000.zip", "size": "1100"},
        ])

        with patch("postmule.agents.backup._build_drive", return_value=drive):
            result = list_backups(cfg, {})

        assert len(result) == 3
        assert result[0]["name"] == "backup-2026-03-23-020000.zip"
        assert result[-1]["name"] == "backup-2026-03-21-020000.zip"

    def test_filters_non_backup_files(self):
        cfg = _make_cfg_mock()
        drive = _make_drive_mock(files=[
            {"id": "f1", "name": "backup-2026-03-23-020000.zip", "size": "1000"},
            {"id": "f2", "name": "other-file.json", "size": "100"},
        ])

        with patch("postmule.agents.backup._build_drive", return_value=drive):
            result = list_backups(cfg, {})

        assert len(result) == 1
        assert result[0]["name"] == "backup-2026-03-23-020000.zip"

    def test_returns_empty_on_drive_error(self):
        cfg = _make_cfg_mock()

        with patch("postmule.agents.backup._build_drive", side_effect=Exception("no creds")):
            result = list_backups(cfg, {})

        assert result == []

    def test_size_bytes_field(self):
        cfg = _make_cfg_mock()
        drive = _make_drive_mock(files=[
            {"id": "f1", "name": "backup-2026-03-23-020000.zip", "size": "98765"},
        ])

        with patch("postmule.agents.backup._build_drive", return_value=drive):
            result = list_backups(cfg, {})

        assert result[0]["size_bytes"] == 98765
