"""Unit tests for postmule.core.credentials."""

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from postmule.core.credentials import (
    CredentialsError,
    _derive_key,
    decrypt_credentials,
    encrypt_credentials,
    save_credential,
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

    def test_two_encryptions_produce_different_bytes(self, credentials_yaml, tmp_path):
        enc1 = tmp_path / "c1.enc"
        enc2 = tmp_path / "c2.enc"
        encrypt_credentials(credentials_yaml, enc1, MASTER_PASSWORD)
        encrypt_credentials(credentials_yaml, enc2, MASTER_PASSWORD)
        assert enc1.read_bytes() != enc2.read_bytes()

    def test_non_dict_content_raises(self, tmp_path):
        # Build a .enc from a YAML list (not a dict)
        import os, base64
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        plaintext = b"- just\n- a\n- list\n"
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480_000)
        key = base64.urlsafe_b64encode(kdf.derive(MASTER_PASSWORD.encode()))
        token = Fernet(key).encrypt(plaintext)
        enc_path = tmp_path / "bad.enc"
        enc_path.write_bytes(salt + token)

        with pytest.raises(CredentialsError, match="valid key-value"):
            decrypt_credentials(enc_path, MASTER_PASSWORD)


class TestDeriveKey:
    def test_deterministic_for_same_inputs(self):
        salt = b"a" * 16
        k1 = _derive_key(MASTER_PASSWORD, salt)
        k2 = _derive_key(MASTER_PASSWORD, salt)
        assert k1 == k2

    def test_different_salts_produce_different_keys(self):
        k1 = _derive_key(MASTER_PASSWORD, b"a" * 16)
        k2 = _derive_key(MASTER_PASSWORD, b"b" * 16)
        assert k1 != k2


class TestSaveCredential:
    def _make_enc(self, tmp_path, data: dict) -> Path:
        """Helper: write a dict to credentials.enc."""
        import os, base64
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        plaintext = yaml.safe_dump(data).encode()
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480_000)
        key = base64.urlsafe_b64encode(kdf.derive(MASTER_PASSWORD.encode()))
        token = Fernet(key).encrypt(plaintext)
        enc_path = tmp_path / "credentials.enc"
        enc_path.write_bytes(salt + token)
        return enc_path

    def test_adds_new_provider_field(self, tmp_path):
        enc_path = self._make_enc(tmp_path, {"gemini": {"api_key": "old"}})
        with patch("postmule.core.credentials.load_master_password", return_value=MASTER_PASSWORD):
            save_credential(enc_path, "anthropic", "api_key", "new-key")
        result = decrypt_credentials(enc_path, MASTER_PASSWORD)
        assert result["anthropic"]["api_key"] == "new-key"
        assert result["gemini"]["api_key"] == "old"

    def test_updates_existing_field(self, tmp_path):
        enc_path = self._make_enc(tmp_path, {"gemini": {"api_key": "old-key"}})
        with patch("postmule.core.credentials.load_master_password", return_value=MASTER_PASSWORD):
            save_credential(enc_path, "gemini", "api_key", "updated-key")
        result = decrypt_credentials(enc_path, MASTER_PASSWORD)
        assert result["gemini"]["api_key"] == "updated-key"
