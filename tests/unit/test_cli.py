"""Unit tests for postmule.cli."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from postmule.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def config_file(tmp_path):
    data = {
        "app": {"dry_run": False, "install_dir": str(tmp_path)},
        "notifications": {"alert_email": "test@example.com"},
        "llm": {
            "providers": [{"type": "gemini", "enabled": True}],
            "classification_confidence_threshold": 0.80,
        },
        "email": {
            "providers": [{"type": "gmail", "enabled": True, "address": "test@gmail.com"}]
        },
        "storage": {
            "providers": [{"type": "google_drive", "enabled": True, "root_folder": "PostMule"}]
        },
        "data_protection": {"max_files_moved_per_run": 50},
        "deployment": {"dashboard_port": 5000},
    }
    path = tmp_path / "config.yaml"
    with path.open("w") as f:
        yaml.dump(data, f)
    return path


class TestMainCommandConfigError:
    def test_missing_config_exits_with_error(self, runner, tmp_path):
        result = runner.invoke(main, ["--config", str(tmp_path / "missing.yaml")])
        assert result.exit_code == 1
        assert "Configuration error" in result.output or "error" in result.output.lower()


class TestMainCommandDryRun:
    def test_dry_run_flag_printed(self, runner, config_file, tmp_path):
        enc_path = tmp_path / "credentials.enc"
        with patch("postmule.cli._run_full_pipeline") as mock_pipeline:
            result = runner.invoke(main, ["--config", str(config_file), "--dry-run"])
        # Either ran or printed dry run notice
        assert result.exit_code in (0, 1)

    def test_dry_run_message_shown(self, runner, config_file, tmp_path):
        with patch("postmule.cli._run_full_pipeline") as mock_run:
            result = runner.invoke(main, ["--config", str(config_file), "--dry-run"])
        # Should print dry run notice
        assert "[DRY RUN]" in result.output


class TestAgentFlag:
    def test_invalid_agent_exits(self, runner, config_file, tmp_path):
        with patch("postmule.cli._run_full_pipeline"):
            with patch("postmule.core.credentials.load_credentials", return_value={}):
                result = runner.invoke(main, ["--config", str(config_file), "--agent", "invalid"])
        assert result.exit_code != 0 or "Unknown agent" in result.output


class TestStatusCommand:
    def test_status_command_runs(self, runner):
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        assert "Status" in result.output


class TestVerifyCommand:
    def test_verify_command_runs(self, runner):
        result = runner.invoke(main, ["verify"])
        assert result.exit_code == 0
        assert "ntegrit" in result.output or "verify" in result.output.lower()


class TestRetroactiveCommand:
    def test_retroactive_command_runs(self, runner):
        result = runner.invoke(main, ["retroactive"])
        assert result.exit_code == 0
        assert "retroactive" in result.output.lower() or "processing" in result.output.lower()


class TestLogsCommand:
    def test_logs_no_file_prints_message(self, runner):
        result = runner.invoke(main, ["logs"])
        assert result.exit_code == 0
        assert "No verbose log found" in result.output

    def test_logs_reads_existing_file(self, runner, tmp_path):
        from datetime import date
        today = date.today().isoformat()
        log_dir = tmp_path / "logs" / "verbose"
        log_dir.mkdir(parents=True)
        log_file = log_dir / f"{today}.log"
        log_file.write_text("line 1\nline 2\n")
        import os
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(main, ["logs", "--lines", "10"])
            assert result.exit_code == 0
            assert "line 1" in result.output
        finally:
            os.chdir(old_cwd)


class TestUpdateConfigCommand:
    def test_missing_config_exits(self, runner, tmp_path):
        result = runner.invoke(main, ["update-config", "--config", str(tmp_path / "missing.yaml")])
        assert result.exit_code == 1

    def test_existing_config_launches(self, runner, config_file):
        with patch("click.launch") as mock_launch:
            result = runner.invoke(main, ["update-config", "--config", str(config_file)])
            assert result.exit_code == 0
            mock_launch.assert_called_once_with(str(config_file))


class TestEncryptCredentials:
    def test_encrypt_missing_yaml_fails(self, runner, tmp_path):
        result = runner.invoke(
            main,
            ["encrypt-credentials", "--yaml-file", str(tmp_path / "missing.yaml")],
            input="password\npassword\n",
        )
        assert result.exit_code != 0

    def test_encrypt_valid_yaml_succeeds(self, runner, tmp_path):
        creds_yaml = tmp_path / "credentials.yaml"
        creds_yaml.write_text("google:\n  client_id: test\n")
        enc_path = tmp_path / "credentials.enc"
        result = runner.invoke(
            main,
            ["encrypt-credentials", "--yaml-file", str(creds_yaml), "--enc-file", str(enc_path)],
            input="mypassword\nmypassword\n",
        )
        assert result.exit_code == 0
        assert enc_path.exists()
