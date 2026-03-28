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

import pytest

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


class TestAnthropicProviderSmoke:
    def test_classify_dry_run_returns_classification_result(self):
        from postmule.providers.llm.anthropic import AnthropicProvider
        from postmule.providers.llm.base import ClassificationResult
        provider = AnthropicProvider(api_key="dummy-key")
        result = provider.classify("some OCR text", dry_run=True)
        assert isinstance(result, ClassificationResult)
        assert result.summary == "[dry-run — no API call made]"

    def test_classify_dry_run_does_not_call_api(self):
        from postmule.providers.llm.anthropic import AnthropicProvider
        provider = AnthropicProvider(api_key="dummy-key")
        with patch.object(provider, "_get_client") as mock_client:
            provider.classify("text", dry_run=True)
        mock_client.assert_not_called()

    def test_health_check_returns_health_result_on_error(self):
        import sys
        from postmule.providers.llm.anthropic import AnthropicProvider
        from postmule.providers import HealthResult
        provider = AnthropicProvider(api_key="dummy-key")
        mock_anthropic = MagicMock()
        mock_client = MagicMock()
        mock_client.models.list.side_effect = Exception("auth error")
        mock_anthropic.Anthropic.return_value = mock_client
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is False

    def test_health_check_ok_when_api_succeeds(self):
        import sys
        from postmule.providers.llm.anthropic import AnthropicProvider
        from postmule.providers import HealthResult
        provider = AnthropicProvider(api_key="dummy-key")
        mock_anthropic = MagicMock()
        mock_client = MagicMock()
        mock_client.models.list.return_value = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is True

    def test_satisfies_llm_provider_protocol(self):
        from postmule.providers.llm.anthropic import AnthropicProvider
        from postmule.providers.llm.base import LLMProvider
        provider = AnthropicProvider(api_key="dummy-key")
        assert isinstance(provider, LLMProvider)


class TestOpenAIProviderSmoke:
    def test_classify_dry_run_returns_classification_result(self):
        from postmule.providers.llm.openai import OpenAIProvider
        from postmule.providers.llm.base import ClassificationResult
        provider = OpenAIProvider(api_key="dummy-key")
        result = provider.classify("some OCR text", dry_run=True)
        assert isinstance(result, ClassificationResult)
        assert result.summary == "[dry-run — no API call made]"

    def test_classify_dry_run_does_not_call_api(self):
        from postmule.providers.llm.openai import OpenAIProvider
        provider = OpenAIProvider(api_key="dummy-key")
        with patch.object(provider, "_get_client") as mock_client:
            provider.classify("text", dry_run=True)
        mock_client.assert_not_called()

    def test_health_check_returns_health_result_on_error(self):
        import sys
        from postmule.providers.llm.openai import OpenAIProvider
        from postmule.providers import HealthResult
        provider = OpenAIProvider(api_key="dummy-key")
        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_client.models.list.side_effect = Exception("auth error")
        mock_openai.OpenAI.return_value = mock_client
        with patch.dict(sys.modules, {"openai": mock_openai}):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is False

    def test_health_check_ok_when_api_succeeds(self):
        import sys
        from postmule.providers.llm.openai import OpenAIProvider
        from postmule.providers import HealthResult
        provider = OpenAIProvider(api_key="dummy-key")
        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_client.models.list.return_value = MagicMock()
        mock_openai.OpenAI.return_value = mock_client
        with patch.dict(sys.modules, {"openai": mock_openai}):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is True

    def test_satisfies_llm_provider_protocol(self):
        from postmule.providers.llm.openai import OpenAIProvider
        from postmule.providers.llm.base import LLMProvider
        provider = OpenAIProvider(api_key="dummy-key")
        assert isinstance(provider, LLMProvider)


class TestOllamaProviderSmoke:
    def test_classify_dry_run_returns_classification_result(self):
        from postmule.providers.llm.ollama import OllamaProvider
        from postmule.providers.llm.base import ClassificationResult
        provider = OllamaProvider()
        result = provider.classify("some OCR text", dry_run=True)
        assert isinstance(result, ClassificationResult)
        assert result.summary == "[dry-run — no API call made]"

    def test_classify_dry_run_does_not_make_http_request(self):
        from postmule.providers.llm.ollama import OllamaProvider
        provider = OllamaProvider()
        with patch("requests.post") as mock_post:
            provider.classify("text", dry_run=True)
        mock_post.assert_not_called()

    def test_health_check_server_unreachable(self):
        from postmule.providers.llm.ollama import OllamaProvider
        from postmule.providers import HealthResult
        provider = OllamaProvider(host="http://localhost:11434")
        with patch("requests.get", side_effect=Exception("connection refused")):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is False

    def test_health_check_model_not_pulled(self):
        from postmule.providers.llm.ollama import OllamaProvider
        from postmule.providers import HealthResult
        provider = OllamaProvider(model="llama3.2")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"models": [{"name": "mistral:latest"}]}
        mock_resp.raise_for_status.return_value = None
        with patch("requests.get", return_value=mock_resp):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is False
        assert "pull" in result.message

    def test_health_check_ok_when_model_available(self):
        from postmule.providers.llm.ollama import OllamaProvider
        from postmule.providers import HealthResult
        provider = OllamaProvider(model="llama3.2")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"models": [{"name": "llama3.2:latest"}]}
        mock_resp.raise_for_status.return_value = None
        with patch("requests.get", return_value=mock_resp):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is True

    def test_no_api_key_required(self):
        from postmule.providers.llm.ollama import OllamaProvider
        # Should not raise — Ollama needs no credentials
        provider = OllamaProvider()
        assert provider is not None

    def test_satisfies_llm_provider_protocol(self):
        from postmule.providers.llm.ollama import OllamaProvider
        from postmule.providers.llm.base import LLMProvider
        provider = OllamaProvider()
        assert isinstance(provider, LLMProvider)


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


class TestImapProviderSmoke:
    def _make_provider(self):
        from postmule.providers.email.imap import ImapProvider
        return ImapProvider(host="imap.example.com", username="user@example.com", password="pw")

    def test_health_check_connection_error(self):
        from postmule.providers import HealthResult
        provider = self._make_provider()
        with patch.object(provider, "_connect", side_effect=RuntimeError("connection refused")):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is False

    def test_health_check_ok(self):
        from postmule.providers import HealthResult
        provider = self._make_provider()
        mock_conn = MagicMock()
        mock_conn.select.return_value = ("OK", [b"1"])
        with patch.object(provider, "_connect", return_value=mock_conn):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is True

    def test_list_emails_with_pdf_attachments_returns_list(self):
        provider = self._make_provider()
        mock_conn = MagicMock()
        mock_conn.uid.return_value = ("OK", [b""])
        with patch.object(provider, "_connect", return_value=mock_conn):
            result = provider.list_emails_with_pdf_attachments()
        assert isinstance(result, list)

    def test_satisfies_email_provider_protocol(self):
        from postmule.providers.email.base import EmailProvider
        provider = self._make_provider()
        assert isinstance(provider, EmailProvider)


class TestProtonMailProviderSmoke:
    def test_delegates_to_imap(self):
        from postmule.providers.email.imap import ImapProvider
        from postmule.providers.email.proton import ProtonMailProvider
        provider = ProtonMailProvider(username="user@proton.me", password="bridge-pw")
        assert isinstance(provider, ImapProvider)
        assert provider.host == "127.0.0.1"
        assert provider.port == 1143

    def test_health_check_includes_bridge_message(self):
        from postmule.providers import HealthResult
        from postmule.providers.email.proton import ProtonMailProvider
        provider = ProtonMailProvider(username="user@proton.me", password="bridge-pw")
        mock_conn = MagicMock()
        mock_conn.select.return_value = ("OK", [b"1"])
        with patch.object(provider, "_connect", return_value=mock_conn):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is True
        assert "Bridge" in result.message

    def test_satisfies_email_provider_protocol(self):
        from postmule.providers.email.base import EmailProvider
        from postmule.providers.email.proton import ProtonMailProvider
        provider = ProtonMailProvider(username="user@proton.me", password="bridge-pw")
        assert isinstance(provider, EmailProvider)


class TestOutlookProviderSmoke:
    def test_outlook_365_health_check_ok(self):
        from postmule.providers import HealthResult
        from postmule.providers.email.outlook_365 import Outlook365Provider
        provider = Outlook365Provider(access_token="dummy-token")
        with patch.object(provider, "_get", return_value={"displayName": "Test User"}):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is True

    def test_outlook_365_health_check_error(self):
        from postmule.providers import HealthResult
        from postmule.providers.email.outlook_365 import Outlook365Provider
        provider = Outlook365Provider(access_token="dummy-token")
        with patch.object(provider, "_get", side_effect=Exception("401 Unauthorized")):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is False

    def test_outlook_com_health_check_ok(self):
        from postmule.providers import HealthResult
        from postmule.providers.email.outlook_com import OutlookComProvider
        provider = OutlookComProvider(access_token="dummy-token")
        with patch.object(provider, "_get", return_value={"mail": "user@outlook.com"}):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is True

    def test_list_emails_returns_list(self):
        from postmule.providers.email.outlook_365 import Outlook365Provider
        provider = Outlook365Provider(access_token="dummy-token")
        with patch.object(provider, "_get", return_value={"value": []}):
            result = provider.list_emails_with_pdf_attachments()
        assert isinstance(result, list)

    def test_mark_as_processed_applies_category(self):
        from postmule.providers.email.outlook_365 import Outlook365Provider
        provider = Outlook365Provider(access_token="dummy-token")
        with patch.object(provider, "_patch") as mock_patch:
            provider.mark_as_processed("msg-123")
        mock_patch.assert_called_once()
        call_body = mock_patch.call_args[0][1]
        assert "PostMule" in call_body.get("categories", [])

    def test_satisfies_email_provider_protocol(self):
        from postmule.providers.email.base import EmailProvider
        from postmule.providers.email.outlook_365 import Outlook365Provider
        provider = Outlook365Provider(access_token="dummy-token")
        assert isinstance(provider, EmailProvider)


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


class TestS3ProviderSmoke:
    def _make_provider(self):
        from postmule.providers.storage.s3 import S3Provider
        return S3Provider(
            bucket="test-bucket",
            region="us-east-1",
            access_key_id="AKIAIOSFODNN7EXAMPLE",
            secret_access_key="secret",
        )

    def test_can_instantiate(self):
        provider = self._make_provider()
        assert provider.bucket == "test-bucket"
        assert provider.region == "us-east-1"
        assert provider.root_prefix == "PostMule/"

    def test_root_prefix_normalised(self):
        from postmule.providers.storage.s3 import S3Provider
        p = S3Provider("b", "us-east-1", "k", "s", root_prefix="MyFolder")
        assert p.root_prefix == "MyFolder/"

    def test_health_check_ok(self):
        from postmule.providers import HealthResult
        provider = self._make_provider()
        mock_s3 = MagicMock()
        mock_s3.head_bucket.return_value = {}
        with patch.object(provider, "_get_client", return_value=mock_s3):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is True
        assert "test-bucket" in result.message

    def test_health_check_error(self):
        from postmule.providers import HealthResult
        provider = self._make_provider()
        mock_s3 = MagicMock()
        mock_s3.head_bucket.side_effect = Exception("403 Forbidden")
        with patch.object(provider, "_get_client", return_value=mock_s3):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is False

    def test_upload_pdf_returns_key(self, tmp_path):
        from postmule.providers.storage.s3 import S3Provider
        provider = self._make_provider()
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake content")
        mock_s3 = MagicMock()
        import hashlib
        md5 = hashlib.md5(pdf.read_bytes()).hexdigest()
        mock_s3.put_object.return_value = {}
        mock_s3.head_object.return_value = {"ETag": f'"{md5}"'}
        with patch.object(provider, "_get_client", return_value=mock_s3):
            key = provider.upload_pdf(pdf, "test.pdf", "PostMule/Bills/")
        assert key == "PostMule/Bills/test.pdf"
        mock_s3.put_object.assert_called_once()

    def test_upload_pdf_verify_fails_on_mismatch(self, tmp_path):
        provider = self._make_provider()
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 content")
        mock_s3 = MagicMock()
        mock_s3.put_object.return_value = {}
        mock_s3.head_object.return_value = {"ETag": '"aabbcc112233"'}
        with patch.object(provider, "_get_client", return_value=mock_s3):
            with pytest.raises(RuntimeError, match="verification FAILED"):
                provider.upload_pdf(pdf, "test.pdf", "PostMule/Bills/")

    def test_upload_pdf_multipart_etag_skips_verify(self, tmp_path):
        provider = self._make_provider()
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"content")
        mock_s3 = MagicMock()
        mock_s3.put_object.return_value = {}
        # Multipart ETag contains '-'
        mock_s3.head_object.return_value = {"ETag": '"abc123-3"'}
        with patch.object(provider, "_get_client", return_value=mock_s3):
            key = provider.upload_pdf(pdf, "test.pdf", "PostMule/Bills/")
        assert key == "PostMule/Bills/test.pdf"

    def test_move_file(self):
        provider = self._make_provider()
        mock_s3 = MagicMock()
        with patch.object(provider, "_get_client", return_value=mock_s3):
            provider.move_file("PostMule/Inbox/file.pdf", "PostMule/Bills/", "PostMule/Inbox/")
        mock_s3.copy_object.assert_called_once()
        mock_s3.delete_object.assert_called_once()

    def test_rename_file(self):
        provider = self._make_provider()
        mock_s3 = MagicMock()
        with patch.object(provider, "_get_client", return_value=mock_s3):
            provider.rename_file("PostMule/Bills/old.pdf", "new.pdf")
        mock_s3.copy_object.assert_called_once()
        mock_s3.delete_object.assert_called_once()

    def test_list_folder_returns_files(self):
        provider = self._make_provider()
        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"Contents": [
                {"Key": "PostMule/Bills/a.pdf", "Size": 1024},
                {"Key": "PostMule/Bills/.keep", "Size": 0},
            ]}
        ]
        mock_s3.get_paginator.return_value = mock_paginator
        with patch.object(provider, "_get_client", return_value=mock_s3):
            result = provider.list_folder("PostMule/Bills/")
        # .keep excluded
        assert len(result) == 1
        assert result[0]["name"] == "a.pdf"

    def test_delete_file(self):
        provider = self._make_provider()
        mock_s3 = MagicMock()
        with patch.object(provider, "_get_client", return_value=mock_s3):
            provider.delete_file("PostMule/Bills/old.pdf")
        mock_s3.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="PostMule/Bills/old.pdf"
        )

    def test_satisfies_storage_provider_protocol(self):
        from postmule.providers.storage.base import StorageProvider
        provider = self._make_provider()
        assert isinstance(provider, StorageProvider)


class TestDropboxProviderSmoke:
    def _make_provider(self):
        from postmule.providers.storage.dropbox import DropboxProvider
        return DropboxProvider(access_token="dummy-token")

    def test_can_instantiate(self):
        provider = self._make_provider()
        assert provider.root_folder == "/PostMule"
        assert provider.access_token == "dummy-token"

    def test_root_folder_normalised(self):
        from postmule.providers.storage.dropbox import DropboxProvider
        p = DropboxProvider("tok", root_folder="MyFolder")
        assert p.root_folder == "/MyFolder"

    def test_health_check_ok(self):
        from postmule.providers import HealthResult
        provider = self._make_provider()
        mock_account = MagicMock()
        mock_account.name.display_name = "Alice"
        mock_dbx = MagicMock()
        mock_dbx.users_get_current_account.return_value = mock_account
        with patch.object(provider, "_get_client", return_value=mock_dbx):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is True
        assert "Alice" in result.message

    def test_health_check_error(self):
        from postmule.providers import HealthResult
        provider = self._make_provider()
        mock_dbx = MagicMock()
        mock_dbx.users_get_current_account.side_effect = Exception("401 Unauthorized")
        with patch.object(provider, "_get_client", return_value=mock_dbx):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is False

    def test_content_hash_file(self, tmp_path):
        import hashlib
        from postmule.providers.storage.dropbox import _content_hash_file, _BLOCK_SIZE
        data = b"hello world" * 1000
        f = tmp_path / "test.bin"
        f.write_bytes(data)
        # Verify algorithm: single block (< 4MB) -> SHA-256(SHA-256(data))
        block_hash = hashlib.sha256(data).digest()
        expected = hashlib.sha256(block_hash).hexdigest()
        assert _content_hash_file(f) == expected

    def test_upload_pdf_verifies_content_hash(self, tmp_path):
        import sys, hashlib
        from postmule.providers.storage.dropbox import _content_hash_file
        provider = self._make_provider()
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 content")
        local_hash = _content_hash_file(pdf)
        mock_dbx = MagicMock()
        mock_meta = MagicMock()
        mock_meta.content_hash = local_hash
        mock_dropbox_module = MagicMock()
        mock_dropbox_module.files.WriteMode.overwrite = "overwrite"
        mock_dbx.files_upload.return_value = mock_meta
        with patch.object(provider, "_get_client", return_value=mock_dbx):
            with patch.dict(sys.modules, {"dropbox": mock_dropbox_module}):
                path = provider.upload_pdf(pdf, "test.pdf", "/PostMule/Bills")
        assert path == "/PostMule/Bills/test.pdf"

    def test_move_file(self):
        provider = self._make_provider()
        mock_dbx = MagicMock()
        with patch.object(provider, "_get_client", return_value=mock_dbx):
            provider.move_file("/PostMule/Inbox/f.pdf", "/PostMule/Bills", "/PostMule/Inbox")
        mock_dbx.files_move_v2.assert_called_once_with(
            "/PostMule/Inbox/f.pdf", "/PostMule/Bills/f.pdf", allow_ownership_transfer=False
        )

    def test_rename_file(self):
        provider = self._make_provider()
        mock_dbx = MagicMock()
        with patch.object(provider, "_get_client", return_value=mock_dbx):
            provider.rename_file("/PostMule/Bills/old.pdf", "new.pdf")
        mock_dbx.files_move_v2.assert_called_once_with(
            "/PostMule/Bills/old.pdf", "/PostMule/Bills/new.pdf"
        )

    def test_list_folder_returns_files(self):
        import sys
        provider = self._make_provider()
        mock_dbx = MagicMock()
        mock_entry = MagicMock()
        mock_entry.path_lower = "/postmule/bills/a.pdf"
        mock_entry.name = "a.pdf"
        mock_response = MagicMock()
        mock_response.entries = [mock_entry]
        mock_response.has_more = False
        mock_dbx.files_list_folder.return_value = mock_response
        mock_dropbox_module = MagicMock()
        mock_dropbox_module.files.FileMetadata = type(mock_entry)
        with patch.object(provider, "_get_client", return_value=mock_dbx):
            with patch.dict(sys.modules, {"dropbox": mock_dropbox_module}):
                result = provider.list_folder("/PostMule/Bills")
        assert len(result) == 1
        assert result[0]["name"] == "a.pdf"

    def test_delete_file(self):
        provider = self._make_provider()
        mock_dbx = MagicMock()
        with patch.object(provider, "_get_client", return_value=mock_dbx):
            provider.delete_file("/PostMule/Bills/old.pdf")
        mock_dbx.files_permanently_delete.assert_called_once_with("/PostMule/Bills/old.pdf")

    def test_satisfies_storage_provider_protocol(self):
        from postmule.providers.storage.base import StorageProvider
        provider = self._make_provider()
        assert isinstance(provider, StorageProvider)


class TestOneDriveProviderSmoke:
    def _make_provider(self):
        from postmule.providers.storage.onedrive import OneDriveProvider
        return OneDriveProvider(access_token="dummy-token")

    def test_can_instantiate(self):
        provider = self._make_provider()
        assert provider.root_folder == "PostMule"
        assert provider.access_token == "dummy-token"

    def test_health_check_ok(self):
        from postmule.providers import HealthResult
        provider = self._make_provider()
        with patch.object(provider, "_get", return_value={"quota": {"used": 2000000000}}):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is True
        assert "2.0 GB" in result.message

    def test_health_check_error(self):
        from postmule.providers import HealthResult
        provider = self._make_provider()
        with patch.object(provider, "_get", side_effect=Exception("401 Unauthorized")):
            result = provider.health_check()
        assert isinstance(result, HealthResult)
        assert result.ok is False

    def test_upload_pdf_returns_item_id(self, tmp_path):
        import hashlib
        provider = self._make_provider()
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 content")
        sha1 = hashlib.sha1(pdf.read_bytes()).hexdigest()
        with patch.object(provider, "_put_bytes", return_value={"id": "item-123"}):
            with patch.object(provider, "_get", return_value={"file": {"hashes": {"sha1Hash": sha1}}}):
                file_id = provider.upload_pdf(pdf, "test.pdf", "folder-456")
        assert file_id == "item-123"

    def test_upload_pdf_verify_fails_on_mismatch(self, tmp_path):
        provider = self._make_provider()
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"content")
        with patch.object(provider, "_put_bytes", return_value={"id": "item-123"}):
            with patch.object(provider, "_get", return_value={"file": {"hashes": {"sha1Hash": "wrong"}}}):
                with pytest.raises(RuntimeError, match="verification FAILED"):
                    provider.upload_pdf(pdf, "test.pdf", "folder-456")

    def test_move_file(self):
        provider = self._make_provider()
        with patch.object(provider, "_patch", return_value={}) as mock_patch:
            provider.move_file("item-1", "folder-2", "folder-1")
        mock_patch.assert_called_once_with(
            "/me/drive/items/item-1",
            {"parentReference": {"id": "folder-2"}},
        )

    def test_rename_file(self):
        provider = self._make_provider()
        with patch.object(provider, "_patch", return_value={}) as mock_patch:
            provider.rename_file("item-1", "new-name.pdf")
        mock_patch.assert_called_once_with("/me/drive/items/item-1", {"name": "new-name.pdf"})

    def test_list_folder_returns_files(self):
        provider = self._make_provider()
        with patch.object(provider, "_get", return_value={
            "value": [
                {"id": "f1", "name": "a.pdf", "size": 1024, "file": {}},
                {"id": "f2", "name": "subfolder", "folder": {}},
            ]
        }):
            result = provider.list_folder("folder-456")
        # Only files, not folders
        assert len(result) == 1
        assert result[0]["id"] == "f1"
        assert result[0]["name"] == "a.pdf"

    def test_delete_file(self):
        provider = self._make_provider()
        with patch.object(provider, "_delete") as mock_delete:
            provider.delete_file("item-1")
        mock_delete.assert_called_once_with("/me/drive/items/item-1")

    def test_satisfies_storage_provider_protocol(self):
        from postmule.providers.storage.base import StorageProvider
        provider = self._make_provider()
        assert isinstance(provider, StorageProvider)
