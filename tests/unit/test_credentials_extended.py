"""
Extended unit tests for postmule/core/credentials.py

Covers: save_master_password, load_master_password, load_credentials,
        decrypt_credentials (non-dict result), save_google_refresh_token,
        load_google_refresh_token, google_credentials_available,
        build_google_credentials
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from postmule.core.credentials import (
    CredentialsError,
    decrypt_credentials,
    encrypt_credentials,
    google_credentials_available,
    load_credentials,
    load_google_refresh_token,
    load_master_password,
    save_google_refresh_token,
    save_master_password,
)

_KEYRING_SERVICE = "PostMule"
_KEYRING_USER = "MasterPassword"


# ---------------------------------------------------------------------------
# save_master_password
# ---------------------------------------------------------------------------

class TestSaveMasterPassword:
    def test_success(self):
        mock_keyring = MagicMock()
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            save_master_password("s3cr3t")
        mock_keyring.set_password.assert_called_once_with(_KEYRING_SERVICE, _KEYRING_USER, "s3cr3t")

    def test_raises_credentials_error_when_keyring_not_installed(self):
        with patch.dict(sys.modules, {"keyring": None}):
            with pytest.raises(CredentialsError, match="keyring is not installed"):
                save_master_password("s3cr3t")

    def test_raises_credentials_error_on_keyring_exception(self):
        mock_keyring = MagicMock()
        mock_keyring.set_password.side_effect = Exception("OS keyring locked")
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            with pytest.raises(CredentialsError, match="Failed to save master password"):
                save_master_password("s3cr3t")


# ---------------------------------------------------------------------------
# load_master_password
# ---------------------------------------------------------------------------

class TestLoadMasterPassword:
    def test_success(self):
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = "my_password"
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            result = load_master_password()
        assert result == "my_password"

    def test_raises_when_keyring_not_installed(self):
        with patch.dict(sys.modules, {"keyring": None}):
            with pytest.raises(CredentialsError, match="keyring is not installed"):
                load_master_password()

    def test_raises_on_keyring_exception(self):
        mock_keyring = MagicMock()
        mock_keyring.get_password.side_effect = Exception("access denied")
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            with pytest.raises(CredentialsError, match="Failed to read master password"):
                load_master_password()

    def test_raises_when_password_is_none(self):
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = None
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            with pytest.raises(CredentialsError, match="not found in system keychain"):
                load_master_password()


# ---------------------------------------------------------------------------
# load_credentials (full pipeline)
# ---------------------------------------------------------------------------

class TestLoadCredentials:
    def test_success_calls_load_master_password_then_decrypt(self, tmp_path):
        yaml_path = tmp_path / "creds.yaml"
        enc_path = tmp_path / "creds.enc"
        yaml_path.write_text("smtp:\n  host: mail.example.com\n")

        password = "integration_pass"
        encrypt_credentials(yaml_path, enc_path, password)

        with patch("postmule.core.credentials.load_master_password", return_value=password):
            result = load_credentials(enc_path)

        assert result["smtp"]["host"] == "mail.example.com"

    def test_propagates_load_master_password_error(self, tmp_path):
        enc_path = tmp_path / "creds.enc"
        enc_path.write_bytes(b"fake")

        with patch("postmule.core.credentials.load_master_password",
                   side_effect=CredentialsError("no password")):
            with pytest.raises(CredentialsError, match="no password"):
                load_credentials(enc_path)


# ---------------------------------------------------------------------------
# decrypt_credentials — non-dict YAML result
# ---------------------------------------------------------------------------

class TestDecryptCredentialsNonDict:
    def test_raises_when_decrypted_content_is_not_dict(self, tmp_path):
        """If credentials.yaml contains a plain list or scalar, raise CredentialsError."""
        yaml_path = tmp_path / "creds.yaml"
        enc_path = tmp_path / "creds.enc"
        # Write a YAML list (not a dict)
        yaml_path.write_text("- item1\n- item2\n")

        password = "pw"
        encrypt_credentials(yaml_path, enc_path, password)

        with pytest.raises(CredentialsError, match="valid key-value structure"):
            decrypt_credentials(enc_path, password)


# ---------------------------------------------------------------------------
# save_google_refresh_token
# ---------------------------------------------------------------------------

class TestSaveGoogleRefreshToken:
    def test_success(self):
        mock_keyring = MagicMock()
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            save_google_refresh_token("1//my_refresh_token")
        mock_keyring.set_password.assert_called_once()
        args = mock_keyring.set_password.call_args[0]
        assert args[2] == "1//my_refresh_token"

    def test_raises_when_keyring_not_installed(self):
        with patch.dict(sys.modules, {"keyring": None}):
            with pytest.raises(CredentialsError, match="keyring is not installed"):
                save_google_refresh_token("token")

    def test_raises_on_keyring_exception(self):
        mock_keyring = MagicMock()
        mock_keyring.set_password.side_effect = Exception("permission denied")
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            with pytest.raises(CredentialsError, match="Failed to save Google refresh token"):
                save_google_refresh_token("token")


# ---------------------------------------------------------------------------
# load_google_refresh_token
# ---------------------------------------------------------------------------

class TestLoadGoogleRefreshToken:
    def test_success(self):
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = "1//my_token"
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            result = load_google_refresh_token()
        assert result == "1//my_token"

    def test_raises_when_keyring_not_installed(self):
        with patch.dict(sys.modules, {"keyring": None}):
            with pytest.raises(CredentialsError, match="keyring is not installed"):
                load_google_refresh_token()

    def test_raises_on_keyring_exception(self):
        mock_keyring = MagicMock()
        mock_keyring.get_password.side_effect = Exception("backend error")
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            with pytest.raises(CredentialsError, match="Failed to read Google refresh token"):
                load_google_refresh_token()

    def test_raises_when_token_is_none(self):
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = None
        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            with pytest.raises(CredentialsError, match="Google account not connected"):
                load_google_refresh_token()


# ---------------------------------------------------------------------------
# google_credentials_available
# ---------------------------------------------------------------------------

class TestGoogleCredentialsAvailable:
    def test_returns_true_when_token_present(self):
        with patch("postmule.core.credentials.load_google_refresh_token", return_value="token"):
            assert google_credentials_available() is True

    def test_returns_false_when_credentials_error(self):
        with patch("postmule.core.credentials.load_google_refresh_token",
                   side_effect=CredentialsError("not found")):
            assert google_credentials_available() is False


# ---------------------------------------------------------------------------
# build_google_credentials
# ---------------------------------------------------------------------------

class TestBuildGoogleCredentials:
    def test_raises_when_google_auth_not_installed(self):
        with patch.dict(sys.modules, {
            "google": None,
            "google.oauth2": None,
            "google.oauth2.credentials": None,
            "google.auth": None,
            "google.auth.transport": None,
            "google.auth.transport.requests": None,
        }):
            from postmule.core import credentials as creds_module
            with patch.object(creds_module, "load_google_refresh_token", return_value="tok"):
                from postmule.core.credentials import build_google_credentials
                with pytest.raises(CredentialsError, match="google-auth is not installed"):
                    build_google_credentials()

    def test_raises_when_client_id_is_empty(self):
        mock_creds_cls = MagicMock()
        mock_request_cls = MagicMock()

        with patch("postmule.core.credentials.load_google_refresh_token", return_value="token"), \
             patch("postmule.core.constants.GOOGLE_CLIENT_ID", ""), \
             patch.dict(sys.modules, {
                 "google.oauth2.credentials": MagicMock(Credentials=mock_creds_cls),
                 "google.auth.transport.requests": MagicMock(Request=mock_request_cls),
             }):
            from postmule.core.credentials import build_google_credentials
            with pytest.raises(CredentialsError, match="GOOGLE_CLIENT_ID"):
                build_google_credentials()

    def test_success_builds_and_refreshes_credentials(self):
        mock_creds_instance = MagicMock()
        mock_creds_cls = MagicMock(return_value=mock_creds_instance)
        mock_request_instance = MagicMock()
        mock_request_cls = MagicMock(return_value=mock_request_instance)

        mock_google_oauth2 = MagicMock()
        mock_google_oauth2.Credentials = mock_creds_cls
        mock_google_auth_transport = MagicMock()
        mock_google_auth_transport.Request = mock_request_cls

        with patch("postmule.core.credentials.load_google_refresh_token", return_value="refresh_tok"), \
             patch.dict(sys.modules, {
                 "google.oauth2.credentials": mock_google_oauth2,
                 "google.auth.transport.requests": mock_google_auth_transport,
             }):
            from postmule.core.credentials import build_google_credentials
            result = build_google_credentials()

        assert result is mock_creds_instance
        mock_creds_instance.refresh.assert_called_once_with(mock_request_instance)
