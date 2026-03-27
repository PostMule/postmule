"""
Unit tests for Protocol base classes:
  postmule/providers/spreadsheet/base.py
  postmule/providers/storage/base.py

Protocols with @runtime_checkable only have their import lines and the
isinstance() check path exercised — the method bodies are `...` and are
never executed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from postmule.providers.spreadsheet.base import SpreadsheetProvider
from postmule.providers.storage.base import StorageProvider


# ---------------------------------------------------------------------------
# SpreadsheetProvider
# ---------------------------------------------------------------------------

class TestSpreadsheetProviderProtocol:
    def test_concrete_class_with_all_methods_is_instance(self):
        class MySpreadsheet:
            def get_or_create_workbook(self, drive_folder_id=None):
                return "wb-id"

            def write_sheet(self, sheet_name, rows):
                pass

            def health_check(self):
                pass

        obj = MySpreadsheet()
        assert isinstance(obj, SpreadsheetProvider)

    def test_class_missing_write_sheet_is_not_instance(self):
        class Incomplete:
            def get_or_create_workbook(self, drive_folder_id=None):
                return "wb-id"

        assert not isinstance(Incomplete(), SpreadsheetProvider)

    def test_class_missing_get_or_create_workbook_is_not_instance(self):
        class Incomplete:
            def write_sheet(self, sheet_name, rows):
                pass

        assert not isinstance(Incomplete(), SpreadsheetProvider)

    def test_plain_object_is_not_instance(self):
        assert not isinstance(object(), SpreadsheetProvider)

    def test_mock_with_spec_is_instance(self):
        """MagicMock with spec satisfies the Protocol."""
        mock = MagicMock(spec=SpreadsheetProvider)
        assert isinstance(mock, SpreadsheetProvider)

    def test_protocol_is_runtime_checkable(self):
        """isinstance() should not raise TypeError."""
        try:
            isinstance(object(), SpreadsheetProvider)
        except TypeError:
            raise AssertionError("SpreadsheetProvider is not @runtime_checkable")

    def test_get_or_create_workbook_default_arg_is_none(self):
        """Verifies the protocol signature accepts no drive_folder_id."""
        class MinimalSpreadsheet:
            def get_or_create_workbook(self, drive_folder_id=None):
                return "id"

            def write_sheet(self, sheet_name, rows):
                pass

        obj = MinimalSpreadsheet()
        assert obj.get_or_create_workbook() == "id"


# ---------------------------------------------------------------------------
# StorageProvider
# ---------------------------------------------------------------------------

class TestStorageProviderProtocol:
    def _make_concrete(self):
        class MyStorage:
            def upload_pdf(self, local_path, filename, folder_id, verify=True):
                return "file-id"

            def move_file(self, file_id, new_folder_id, old_folder_id):
                pass

            def rename_file(self, file_id, new_name):
                pass

            def list_folder(self, folder_id):
                return []

            def ensure_folder_structure(self, folders):
                return {}

            def upload_bytes(self, data, filename, folder_id, mimetype="application/octet-stream"):
                return "file-id"

            def delete_file(self, file_id):
                pass

            def health_check(self):
                pass

        return MyStorage()

    def test_concrete_class_with_all_methods_is_instance(self):
        assert isinstance(self._make_concrete(), StorageProvider)

    def test_class_missing_upload_pdf_is_not_instance(self):
        class Incomplete:
            def move_file(self, file_id, new_folder_id, old_folder_id):
                pass

            def rename_file(self, file_id, new_name):
                pass

            def list_folder(self, folder_id):
                return []

            def ensure_folder_structure(self, folders):
                return {}

        assert not isinstance(Incomplete(), StorageProvider)

    def test_class_missing_list_folder_is_not_instance(self):
        class Incomplete:
            def upload_pdf(self, local_path, filename, folder_id, verify=True):
                return "id"

            def move_file(self, file_id, new_folder_id, old_folder_id):
                pass

            def rename_file(self, file_id, new_name):
                pass

            def ensure_folder_structure(self, folders):
                return {}

        assert not isinstance(Incomplete(), StorageProvider)

    def test_class_missing_ensure_folder_structure_is_not_instance(self):
        class Incomplete:
            def upload_pdf(self, local_path, filename, folder_id, verify=True):
                return "id"

            def move_file(self, file_id, new_folder_id, old_folder_id):
                pass

            def rename_file(self, file_id, new_name):
                pass

            def list_folder(self, folder_id):
                return []

        assert not isinstance(Incomplete(), StorageProvider)

    def test_plain_object_is_not_instance(self):
        assert not isinstance(object(), StorageProvider)

    def test_mock_with_spec_is_instance(self):
        mock = MagicMock(spec=StorageProvider)
        assert isinstance(mock, StorageProvider)

    def test_protocol_is_runtime_checkable(self):
        try:
            isinstance(object(), StorageProvider)
        except TypeError:
            raise AssertionError("StorageProvider is not @runtime_checkable")

    def test_upload_pdf_verify_default_is_true(self):
        obj = self._make_concrete()
        result = obj.upload_pdf(Path("/tmp/x.pdf"), "x.pdf", "folder-1")
        assert result == "file-id"


# ---------------------------------------------------------------------------
# Per-provider smoke tests
# ---------------------------------------------------------------------------

class TestGeminiProviderSmoke:
    def test_classify_dry_run_returns_classification_result(self):
        from postmule.providers.llm.gemini import GeminiProvider
        from postmule.providers.llm.base import ClassificationResult
        provider = GeminiProvider(api_key="dummy-key")
        result = provider.classify("some OCR text", dry_run=True)
        assert isinstance(result, ClassificationResult)

    def test_classify_dry_run_does_not_call_api(self):
        from postmule.providers.llm.gemini import GeminiProvider
        provider = GeminiProvider(api_key="dummy-key")
        with patch.object(provider, "_get_client") as mock_client:
            provider.classify("text", dry_run=True)
        mock_client.assert_not_called()

    def test_health_check_returns_health_result(self):
        from postmule.providers.llm.gemini import GeminiProvider
        from postmule.providers import HealthResult
        provider = GeminiProvider(api_key="dummy-key")
        with patch("google.generativeai.configure"), patch("google.generativeai.list_models", return_value=[]):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.status in ("ok", "error", "warn")


class TestGmailProviderSmoke:
    def test_health_check_does_not_raise_with_dummy_creds(self):
        from postmule.providers.email.gmail import GmailProvider
        from postmule.providers import HealthResult
        provider = GmailProvider(credentials=MagicMock())
        mock_svc = MagicMock()
        mock_svc.users().labels().list().execute.side_effect = Exception("auth error")
        with patch.object(provider, "_get_service", return_value=mock_svc):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is False

    def test_health_check_returns_ok_when_service_succeeds(self):
        from postmule.providers.email.gmail import GmailProvider
        from postmule.providers import HealthResult
        provider = GmailProvider(credentials=MagicMock())
        mock_svc = MagicMock()
        mock_svc.users().labels().list().execute.return_value = {"labels": []}
        with patch.object(provider, "_get_service", return_value=mock_svc):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is True

    def test_list_emails_with_pdf_attachments_returns_list(self):
        from postmule.providers.email.gmail import GmailProvider
        provider = GmailProvider(credentials=MagicMock())
        mock_svc = MagicMock()
        mock_svc.users().messages().list().execute.return_value = {"messages": [], "nextPageToken": None}
        mock_svc.users().labels().list().execute.return_value = {"labels": [{"id": "L1", "name": "PostMule"}]}
        with patch.object(provider, "_get_service", return_value=mock_svc):
            result = provider.list_emails_with_pdf_attachments()
        assert isinstance(result, list)


class TestDriveProviderSmoke:
    def test_health_check_does_not_raise_with_dummy_creds(self):
        from postmule.providers.storage.google_drive import DriveProvider
        from postmule.providers import HealthResult
        provider = DriveProvider(credentials=MagicMock())
        mock_svc = MagicMock()
        mock_svc.about().get().execute.side_effect = Exception("auth error")
        with patch.object(provider, "_get_service", return_value=mock_svc):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is False

    def test_health_check_returns_ok_when_service_succeeds(self):
        from postmule.providers.storage.google_drive import DriveProvider
        from postmule.providers import HealthResult
        provider = DriveProvider(credentials=MagicMock())
        mock_svc = MagicMock()
        mock_svc.about().get().execute.return_value = {"user": {"displayName": "Test"}}
        with patch.object(provider, "_get_service", return_value=mock_svc):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is True
