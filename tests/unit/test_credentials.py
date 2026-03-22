"""Unit tests for postmule.core.credentials."""

from pathlib import Path

import pytest
import yaml

from postmule.core.credentials import (
    CredentialsError,
    decrypt_credentials,
    encrypt_credentials,
)


MASTER_PASSWORD = "test-master-password-123"


class TestEncryptDecrypt:
    def test_roundtrip(self, credentials_yaml, tmp_path):
        enc_path = tmp_path / "credentials.enc"
        encrypt_credentials(credentials_yaml, enc_path, MASTER_PASSWORD)
        assert enc_path.exists()

        result = decrypt_credentials(enc_path, MASTER_PASSWORD)
        assert result["gemini"]["api_key"] == "test-gemini-key"
        assert result["google"]["client_id"] == "test-id"

    def test_wrong_password_raises(self, credentials_yaml, tmp_path):
        enc_path = tmp_path / "credentials.enc"
        encrypt_credentials(credentials_yaml, enc_path, MASTER_PASSWORD)

        with pytest.raises(CredentialsError, match="wrong master password"):
            decrypt_credentials(enc_path, "wrong-password")

    def test_missing_yaml_raises(self, tmp_path):
        with pytest.raises(CredentialsError, match="not found"):
            encrypt_credentials(
                tmp_path / "nonexistent.yaml",
                tmp_path / "credentials.enc",
                MASTER_PASSWORD,
            )

    def test_missing_enc_raises(self, tmp_path):
        with pytest.raises(CredentialsError, match="not found"):
            decrypt_credentials(tmp_path / "nonexistent.enc", MASTER_PASSWORD)

    def test_invalid_yaml_raises(self, tmp_path):
        bad_yaml = tmp_path / "credentials.yaml"
        bad_yaml.write_text("key: [unclosed")
        with pytest.raises(CredentialsError, match="syntax error"):
            encrypt_credentials(bad_yaml, tmp_path / "out.enc", MASTER_PASSWORD)

    def test_encrypted_file_is_not_plaintext(self, credentials_yaml, tmp_path):
        enc_path = tmp_path / "credentials.enc"
        encrypt_credentials(credentials_yaml, enc_path, MASTER_PASSWORD)
        raw = enc_path.read_bytes()
        assert b"api_key" not in raw
        assert b"test-gemini-key" not in raw
