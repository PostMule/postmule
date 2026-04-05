"""
Unit tests for LocalStorageProvider.
All tests use a temporary directory — no real filesystem side effects.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from postmule.providers.storage.local import LocalStorageProvider


@pytest.fixture
def storage(tmp_path):
    return LocalStorageProvider(root_dir=tmp_path / "PostMule")


@pytest.fixture
def sample_pdf(tmp_path):
    p = tmp_path / "test.pdf"
    p.write_bytes(b"%PDF-1.4 test content")
    return p


class TestEnsureFolderStructure:
    def test_creates_subdirectories(self, storage, tmp_path):
        folders = {"inbox": "Inbox", "bills": "Bills"}
        result = storage.ensure_folder_structure(folders)
        assert Path(result["inbox"]).is_dir()
        assert Path(result["bills"]).is_dir()

    def test_returns_root_key(self, storage):
        result = storage.ensure_folder_structure({})
        assert "root" in result
        assert Path(result["root"]).is_dir()

    def test_idempotent(self, storage):
        folders = {"inbox": "Inbox"}
        storage.ensure_folder_structure(folders)
        result = storage.ensure_folder_structure(folders)
        assert Path(result["inbox"]).is_dir()


class TestUploadPdf:
    def test_copies_file_to_folder(self, storage, sample_pdf):
        folders = storage.ensure_folder_structure({"inbox": "Inbox"})
        file_id = storage.upload_pdf(sample_pdf, "test.pdf", folders["inbox"])
        assert Path(file_id).exists()
        assert Path(file_id).read_bytes() == sample_pdf.read_bytes()

    def test_verify_passes_for_valid_copy(self, storage, sample_pdf):
        folders = storage.ensure_folder_structure({"inbox": "Inbox"})
        file_id = storage.upload_pdf(sample_pdf, "test.pdf", folders["inbox"], verify=True)
        assert Path(file_id).name == "test.pdf"

    def test_returns_absolute_path_as_file_id(self, storage, sample_pdf):
        folders = storage.ensure_folder_structure({"inbox": "Inbox"})
        file_id = storage.upload_pdf(sample_pdf, "out.pdf", folders["inbox"])
        assert Path(file_id).is_absolute()


class TestUploadBytes:
    def test_writes_bytes_to_folder(self, storage):
        folders = storage.ensure_folder_structure({"system": "_System"})
        data = b'{"key": "value"}'
        file_id = storage.upload_bytes(data, "data.json", folders["system"])
        assert Path(file_id).read_bytes() == data


class TestMoveFile:
    def test_moves_file_between_folders(self, storage, sample_pdf):
        folders = storage.ensure_folder_structure({"inbox": "Inbox", "bills": "Bills"})
        file_id = storage.upload_pdf(sample_pdf, "bill.pdf", folders["inbox"])
        storage.move_file(file_id, folders["bills"], folders["inbox"])
        assert not Path(file_id).exists()
        assert (Path(folders["bills"]) / "bill.pdf").exists()

    def test_no_error_if_source_missing(self, storage, tmp_path):
        folders = storage.ensure_folder_structure({"bills": "Bills"})
        storage.move_file("/nonexistent/file.pdf", folders["bills"], folders["bills"])


class TestRenameFile:
    def test_renames_file(self, storage, sample_pdf):
        folders = storage.ensure_folder_structure({"inbox": "Inbox"})
        file_id = storage.upload_pdf(sample_pdf, "old.pdf", folders["inbox"])
        storage.rename_file(file_id, "new.pdf")
        assert not Path(file_id).exists()
        assert (Path(folders["inbox"]) / "new.pdf").exists()

    def test_no_error_if_file_missing(self, storage):
        storage.rename_file("/nonexistent/file.pdf", "renamed.pdf")


class TestListFolder:
    def test_lists_files(self, storage, sample_pdf):
        folders = storage.ensure_folder_structure({"inbox": "Inbox"})
        storage.upload_pdf(sample_pdf, "a.pdf", folders["inbox"])
        storage.upload_bytes(b"x", "b.json", folders["inbox"])
        items = storage.list_folder(folders["inbox"])
        names = {i["name"] for i in items}
        assert "a.pdf" in names
        assert "b.json" in names

    def test_empty_folder(self, storage):
        folders = storage.ensure_folder_structure({"inbox": "Inbox"})
        assert storage.list_folder(folders["inbox"]) == []

    def test_nonexistent_folder(self, storage):
        assert storage.list_folder("/does/not/exist") == []


class TestDeleteFile:
    def test_moves_to_trash(self, storage, sample_pdf):
        folders = storage.ensure_folder_structure({"inbox": "Inbox"})
        file_id = storage.upload_pdf(sample_pdf, "to_delete.pdf", folders["inbox"])
        storage.delete_file(file_id)
        assert not Path(file_id).exists()
        trash = storage.root_dir / "_Trash" / "to_delete.pdf"
        assert trash.exists()

    def test_no_error_if_file_missing(self, storage):
        storage.delete_file("/nonexistent/file.pdf")


class TestDownloadFile:
    def test_returns_file_bytes(self, storage, sample_pdf):
        folders = storage.ensure_folder_structure({"inbox": "Inbox"})
        file_id = storage.upload_pdf(sample_pdf, "dl.pdf", folders["inbox"])
        data = storage.download_file(file_id)
        assert data == sample_pdf.read_bytes()


class TestHealthCheck:
    def test_ok_when_root_exists(self, storage):
        result = storage.health_check()
        assert result.ok
        assert result.status == "ok"

    def test_ok_creates_root_if_missing(self, tmp_path):
        s = LocalStorageProvider(root_dir=tmp_path / "NewDir")
        result = s.health_check()
        assert result.ok
