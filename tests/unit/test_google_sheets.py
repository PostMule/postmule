"""Unit tests for postmule.providers.spreadsheet.google_sheets."""

from unittest.mock import MagicMock, patch

import pytest

from postmule.providers.spreadsheet.google_sheets import SheetsProvider


class TestSheetsProviderInit:
    def test_stores_credentials(self):
        creds = {"refresh_token": "tok"}
        provider = SheetsProvider(creds, workbook_name="TestWorkbook")
        assert provider.credentials == creds
        assert provider.workbook_name == "TestWorkbook"

    def test_default_workbook_name(self):
        provider = SheetsProvider({})
        assert provider.workbook_name == "PostMule"


class TestGetOrCreateWorkbook:
    def _make_provider(self):
        provider = SheetsProvider(
            {"refresh_token": "tok", "client_id": "cid", "client_secret": "cs"},
            workbook_name="PostMule"
        )
        svc = MagicMock()
        provider._service = svc
        return provider, svc

    def test_returns_cached_id(self):
        provider, svc = self._make_provider()
        provider._spreadsheet_id = "cached-id"
        result = provider.get_or_create_workbook()
        assert result == "cached-id"

    def test_creates_new_workbook_when_not_found(self):
        provider, svc = self._make_provider()
        # Drive search raises so we fall through to creation
        with patch("googleapiclient.discovery.build") as mock_build:
            mock_drive_svc = MagicMock()
            mock_build.return_value = mock_drive_svc
            mock_drive_svc.files.return_value.list.return_value.execute.return_value = {"files": []}
            # Mock sheets creation
            svc.spreadsheets.return_value.create.return_value.execute.return_value = {
                "spreadsheetId": "new-sheet-id"
            }
            result = provider.get_or_create_workbook()
        assert result == "new-sheet-id"
        assert provider._spreadsheet_id == "new-sheet-id"

    def test_finds_existing_workbook_via_drive(self):
        provider, svc = self._make_provider()
        with patch("googleapiclient.discovery.build") as mock_build:
            mock_drive_svc = MagicMock()
            mock_build.return_value = mock_drive_svc
            mock_drive_svc.files.return_value.list.return_value.execute.return_value = {
                "files": [{"id": "existing-sheet-id"}]
            }
            result = provider.get_or_create_workbook()
        assert result == "existing-sheet-id"


class TestWriteSheet:
    def _make_provider_with_id(self):
        provider = SheetsProvider(
            {"refresh_token": "tok", "client_id": "cid", "client_secret": "cs"}
        )
        svc = MagicMock()
        provider._service = svc
        provider._spreadsheet_id = "sheet-id"
        return provider, svc

    def test_raises_when_no_spreadsheet_id(self):
        provider = SheetsProvider({})
        provider._service = MagicMock()
        # _spreadsheet_id is None
        with pytest.raises(RuntimeError, match="get_or_create_workbook"):
            provider.write_sheet("Bills", [["Header", "Col2"]])

    def test_clears_then_updates(self):
        provider, svc = self._make_provider_with_id()
        rows = [["ID", "Amount"], ["1", "94.00"]]
        provider.write_sheet("Bills", rows)
        svc.spreadsheets().values().clear.assert_called_once()
        svc.spreadsheets().values().update.assert_called_once()

    def test_skips_update_when_rows_empty(self):
        provider, svc = self._make_provider_with_id()
        provider.write_sheet("Bills", [])
        svc.spreadsheets().values().clear.assert_called_once()
        svc.spreadsheets().values().update.assert_not_called()


class TestAppendRow:
    def test_appends_row(self):
        provider = SheetsProvider({})
        svc = MagicMock()
        provider._service = svc
        provider._spreadsheet_id = "sheet-id"
        provider.append_row("RunLog", ["val1", "val2"])
        svc.spreadsheets().values().append.assert_called_once()
        call_kwargs = svc.spreadsheets().values().append.call_args[1]
        assert call_kwargs["body"]["values"] == [["val1", "val2"]]
