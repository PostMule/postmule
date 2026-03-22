"""Unit tests for postmule.providers.storage.google_drive."""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from postmule.providers.storage.google_drive import DriveProvider, _sha256_file


class TestSha256File:
    def test_computes_correct_hash(self, tmp_path):
        f = tmp_path / "test.bin"
        data = b"hello world"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert _sha256_file(f) == expected

    def test_larger_file(self, tmp_path):
        f = tmp_path / "large.bin"
        data = b"x" * 200000
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert _sha256_file(f) == expected


class TestDriveProviderInit:
    def test_stores_credentials_and_root_folder(self):
        creds = {"refresh_token": "tok"}
        provider = DriveProvider(creds, root_folder="TestFolder")
        assert provider.credentials == creds
        assert provider.root_folder == "TestFolder"

    def test_default_root_folder(self):
        provider = DriveProvider({})
        assert provider.root_folder == "PostMule"

    def test_service_lazy_loaded(self):
        provider = DriveProvider({})
        assert provider._service is None


class TestGetOrCreateFolder:
    def _make_provider(self):
        provider = DriveProvider({"refresh_token": "tok", "client_id": "cid", "client_secret": "cs"})
        svc = MagicMock()
        provider._service = svc
        return provider, svc

    def test_returns_existing_folder(self):
        provider, svc = self._make_provider()
        svc.files().list().execute.return_value = {
            "files": [{"id": "existing-folder-id", "name": "TestFolder"}]
        }
        result = provider._get_or_create_folder("TestFolder", parent_id="parent-1")
        assert result == "existing-folder-id"
        svc.files().create.assert_not_called()

    def test_creates_folder_when_not_found(self):
        provider, svc = self._make_provider()
        svc.files().list().execute.return_value = {"files": []}
        svc.files().create().execute.return_value = {"id": "new-folder-id"}
        result = provider._get_or_create_folder("NewFolder", parent_id="parent-1")
        assert result == "new-folder-id"

    def test_creates_root_folder_without_parent(self):
        provider, svc = self._make_provider()
        svc.files().list().execute.return_value = {"files": []}
        svc.files().create().execute.return_value = {"id": "root-id"}
        result = provider._get_or_create_folder("Root", parent_id=None)
        assert result == "root-id"


class TestEnsureFolderStructure:
    def _make_provider(self):
        provider = DriveProvider({"refresh_token": "tok", "client_id": "cid", "client_secret": "cs"})
        svc = MagicMock()
        provider._service = svc
        counter = [0]
        def make_folder(*args, **kwargs):
            counter[0] += 1
            mock = MagicMock()
            mock.execute.return_value = {"id": f"folder-{counter[0]}"}
            return mock
        svc.files().list.return_value = MagicMock(execute=MagicMock(return_value={"files": []}))
        svc.files().create.side_effect = make_folder
        return provider, svc

    def test_returns_folder_id_dict(self):
        provider, svc = self._make_provider()
        result = provider.ensure_folder_structure({"inbox": "Inbox", "bills": "Bills"})
        assert "root" in result
        assert "inbox" in result
        assert "bills" in result

    def test_creates_system_data_subfolder(self):
        provider, svc = self._make_provider()
        result = provider.ensure_folder_structure({})
        assert "system" in result
        assert "data" in result


class TestUploadPdf:
    def _make_provider(self):
        provider = DriveProvider({"refresh_token": "tok", "client_id": "cid", "client_secret": "cs"})
        svc = MagicMock()
        provider._service = svc
        return provider, svc

    def test_uploads_and_returns_file_id(self, tmp_path):
        provider, svc = self._make_provider()
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF data")
        svc.files.return_value.create.return_value.execute.return_value = {
            "id": "uploaded-id", "name": "test.pdf", "size": "8"
        }
        with patch("googleapiclient.http.MediaFileUpload") as MockMedia:
            MockMedia.return_value = MagicMock()
            with patch.object(provider, "_verify_upload") as mock_verify:
                file_id = provider.upload_pdf(pdf, "test.pdf", "folder-id", verify=True)
        assert file_id == "uploaded-id"
        mock_verify.assert_called_once()

    def test_upload_without_verify(self, tmp_path):
        provider, svc = self._make_provider()
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF data")
        svc.files.return_value.create.return_value.execute.return_value = {
            "id": "uploaded-id", "name": "test.pdf", "size": "8"
        }
        with patch("googleapiclient.http.MediaFileUpload") as MockMedia:
            MockMedia.return_value = MagicMock()
            file_id = provider.upload_pdf(pdf, "test.pdf", "folder-id", verify=False)
        assert file_id == "uploaded-id"


class TestMoveFile:
    def test_moves_file(self):
        provider = DriveProvider({})
        svc = MagicMock()
        provider._service = svc
        provider.move_file("file-id", "new-folder", "old-folder")
        # Verify the update was called with the right args
        svc.files.return_value.update.assert_called_once_with(
            fileId="file-id",
            addParents="new-folder",
            removeParents="old-folder",
            fields="id, parents",
        )


class TestRenameFile:
    def test_renames_file(self):
        provider = DriveProvider({})
        svc = MagicMock()
        provider._service = svc
        provider.rename_file("file-id", "new-name.pdf")
        svc.files.return_value.update.assert_called_once_with(
            fileId="file-id", body={"name": "new-name.pdf"}
        )


class TestListFolder:
    def test_returns_files_list(self):
        provider = DriveProvider({})
        svc = MagicMock()
        provider._service = svc
        svc.files().list().execute.return_value = {
            "files": [{"id": "f1", "name": "a.pdf", "mimeType": "application/pdf"}],
            "nextPageToken": None,
        }
        result = provider.list_folder("folder-id")
        assert len(result) == 1
        assert result[0]["id"] == "f1"

    def test_handles_pagination(self):
        provider = DriveProvider({})
        svc = MagicMock()
        provider._service = svc
        responses = [
            {"files": [{"id": "f1"}], "nextPageToken": "token1"},
            {"files": [{"id": "f2"}], "nextPageToken": None},
        ]
        svc.files().list().execute.side_effect = responses
        result = provider.list_folder("folder-id")
        assert len(result) == 2


class TestTrashFile:
    def test_soft_deletes_file(self):
        provider = DriveProvider({})
        svc = MagicMock()
        provider._service = svc
        provider.trash_file("file-id")
        svc.files.return_value.update.assert_called_once_with(
            fileId="file-id", body={"trashed": True}
        )


class TestVerifyUpload:
    def test_passes_when_hashes_match(self, tmp_path):
        provider = DriveProvider({})
        data = b"%PDF content"
        sha = hashlib.sha256(data).hexdigest()

        with patch.object(provider, "download_file", return_value=data):
            # Should not raise
            provider._verify_upload("file-id", sha, "test.pdf")

    def test_raises_when_hashes_differ(self, tmp_path):
        provider = DriveProvider({})
        with patch.object(provider, "download_file", return_value=b"different content"):
            with pytest.raises(RuntimeError, match="verification FAILED"):
                provider._verify_upload("file-id", "wrong-hash", "test.pdf")
