"""Unit tests for postmule.agents.integrity.duplicate_detector."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from postmule.agents.integrity.duplicate_detector import (
    find_duplicates_in_folder,
    is_duplicate,
    load_hashes,
    register_file_hash,
    run_duplicate_detection,
    save_hashes,
)


class TestLoadAndSaveHashes:
    def test_empty_when_no_file(self, tmp_path):
        assert load_hashes(tmp_path) == {}

    def test_round_trip(self, tmp_path):
        data = {"abc123": "drive-id-1"}
        save_hashes(tmp_path, data)
        assert load_hashes(tmp_path) == data

    def test_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "sub" / "dir"
        save_hashes(nested, {"hash": "id"})
        assert (nested / "hashes.json").exists()


class TestRegisterFileHash:
    def test_registers_new_hash(self, tmp_path):
        register_file_hash(tmp_path, "sha256abc", "drive-id-x")
        hashes = load_hashes(tmp_path)
        assert hashes["sha256abc"] == "drive-id-x"

    def test_overwrites_existing_hash(self, tmp_path):
        register_file_hash(tmp_path, "sha256abc", "old-id")
        register_file_hash(tmp_path, "sha256abc", "new-id")
        hashes = load_hashes(tmp_path)
        assert hashes["sha256abc"] == "new-id"


class TestIsDuplicate:
    def test_not_duplicate_when_new(self, tmp_path):
        is_dup, original_id = is_duplicate(tmp_path, "newsha256")
        assert is_dup is False
        assert original_id is None

    def test_is_duplicate_when_known(self, tmp_path):
        register_file_hash(tmp_path, "knownhash", "drive-orig")
        is_dup, original_id = is_duplicate(tmp_path, "knownhash")
        assert is_dup is True
        assert original_id == "drive-orig"


class TestFindDuplicatesInFolder:
    def test_no_duplicates_in_unique_files(self, tmp_path):
        files = [
            {"id": "f1", "name": "a.pdf", "md5Checksum": "aaa"},
            {"id": "f2", "name": "b.pdf", "md5Checksum": "bbb"},
        ]
        dupes = find_duplicates_in_folder(files, tmp_path)
        assert dupes == []

    def test_finds_duplicate(self, tmp_path):
        files = [
            {"id": "f1", "name": "a.pdf", "md5Checksum": "same"},
            {"id": "f2", "name": "b.pdf", "md5Checksum": "same"},
        ]
        dupes = find_duplicates_in_folder(files, tmp_path)
        assert len(dupes) == 1
        assert dupes[0]["id"] == "f2"
        assert dupes[0]["original_id"] == "f1"

    def test_skips_files_without_md5(self, tmp_path):
        files = [
            {"id": "f1", "name": "a.pdf", "md5Checksum": ""},
            {"id": "f2", "name": "b.pdf", "md5Checksum": ""},
        ]
        dupes = find_duplicates_in_folder(files, tmp_path)
        assert dupes == []

    def test_multiple_duplicates_of_same_hash(self, tmp_path):
        files = [
            {"id": "f1", "name": "a.pdf", "md5Checksum": "same"},
            {"id": "f2", "name": "b.pdf", "md5Checksum": "same"},
            {"id": "f3", "name": "c.pdf", "md5Checksum": "same"},
        ]
        dupes = find_duplicates_in_folder(files, tmp_path)
        assert len(dupes) == 2


class TestRunDuplicateDetection:
    def test_no_duplicates_returns_zero_moved(self, tmp_path):
        drive = MagicMock()
        drive.list_folder.return_value = [
            {"id": "f1", "name": "a.pdf", "md5Checksum": "aaa"},
        ]
        result = run_duplicate_detection(
            drive=drive,
            folder_ids={"bills": "folder-bills", "duplicates": "folder-dupes"},
            data_dir=tmp_path,
        )
        assert result["duplicates_found"] == 0
        assert result["moved"] == 0
        drive.move_file.assert_not_called()

    def test_moves_duplicates(self, tmp_path):
        drive = MagicMock()
        drive.list_folder.return_value = [
            {"id": "f1", "name": "a.pdf", "md5Checksum": "same"},
            {"id": "f2", "name": "b.pdf", "md5Checksum": "same"},
        ]
        result = run_duplicate_detection(
            drive=drive,
            folder_ids={"bills": "folder-bills", "duplicates": "folder-dupes"},
            data_dir=tmp_path,
        )
        assert result["duplicates_found"] == 1
        assert result["moved"] == 1
        drive.move_file.assert_called_once()

    def test_dry_run_does_not_move(self, tmp_path):
        drive = MagicMock()
        drive.list_folder.return_value = [
            {"id": "f1", "name": "a.pdf", "md5Checksum": "x"},
            {"id": "f2", "name": "b.pdf", "md5Checksum": "x"},
        ]
        result = run_duplicate_detection(
            drive=drive,
            folder_ids={"bills": "folder-bills", "duplicates": "folder-dupes"},
            data_dir=tmp_path,
            dry_run=True,
        )
        assert result["moved"] == 1
        drive.move_file.assert_not_called()

    def test_move_error_recorded(self, tmp_path):
        drive = MagicMock()
        drive.list_folder.return_value = [
            {"id": "f1", "name": "a.pdf", "md5Checksum": "same"},
            {"id": "f2", "name": "b.pdf", "md5Checksum": "same"},
        ]
        drive.move_file.side_effect = RuntimeError("Drive error")
        result = run_duplicate_detection(
            drive=drive,
            folder_ids={"bills": "folder-bills", "duplicates": "folder-dupes"},
            data_dir=tmp_path,
        )
        assert len(result["errors"]) == 1
        assert "Drive error" in result["errors"][0]

    def test_excludes_system_folders(self, tmp_path):
        drive = MagicMock()
        drive.list_folder.return_value = []
        run_duplicate_detection(
            drive=drive,
            folder_ids={
                "bills": "b",
                "root": "r",
                "system": "s",
                "data": "d",
                "duplicates": "dup",
                "archive": "a",
            },
            data_dir=tmp_path,
        )
        # Only bills should be scanned (root/system/data/duplicates/archive excluded)
        assert drive.list_folder.call_count == 1
