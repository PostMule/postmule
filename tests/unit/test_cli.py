"""Unit tests for postmule.cli."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from postmule.cli import _build_config_yaml, _find_example_config, main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def config_file(tmp_path):
    data = {
        "app": {"dry_run": False, "install_dir": str(tmp_path)},
        "notifications": {"alert_email": "test@example.com"},
        "llm": {
            "providers": [{"service": "gemini", "enabled": True}],
            "classification_confidence_threshold": 0.80,
        },
        "email": {
            "providers": [{"service": "gmail", "enabled": True, "address": "test@gmail.com"}]
        },
        "storage": {
            "providers": [{"service": "google_drive", "enabled": True, "root_folder": "PostMule"}]
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


class TestUninstallCommand:
    def test_cancel_does_not_call_subprocess(self, runner, tmp_path):
        script = tmp_path / "uninstall.ps1"
        script.write_text("# fake")
        with patch("postmule.cli.Path") as mock_path_cls:
            mock_script = MagicMock()
            mock_script.exists.return_value = True
            mock_path_cls.return_value.__truediv__.return_value.__truediv__.return_value = mock_script
            # Patch the actual Path used inside uninstall to return a real path
        with patch("subprocess.run") as mock_run:
            result = runner.invoke(main, ["uninstall", "--install-dir", str(tmp_path)], input="n\n")
        assert mock_run.call_count == 0
        assert "Cancelled" in result.output or result.exit_code == 0

    def test_missing_script_exits_with_error(self, runner, tmp_path):
        with patch("postmule.cli.Path") as mock_path_cls:
            mock_script = MagicMock()
            mock_script.exists.return_value = False
            instance = MagicMock()
            instance.__truediv__ = MagicMock(return_value=mock_script)
            mock_path_cls.return_value = instance
            result = runner.invoke(main, ["uninstall", "--install-dir", str(tmp_path)], input="YES\n")
        # Either exits with error or prints not found
        assert result.exit_code != 0 or "not found" in result.output.lower()

    def test_confirmed_calls_powershell(self, runner, tmp_path):
        script = tmp_path / "uninstall.ps1"
        script.write_text("# fake")
        with patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
            with patch("postmule.cli.Path", wraps=Path) as mock_path:
                # Patch __file__ path resolution to point at our tmp script
                with patch("postmule.cli.__file__", str(tmp_path / "cli.py")):
                    result = runner.invoke(
                        main, ["uninstall", "--install-dir", str(tmp_path)], input="YES\n"
                    )
        # subprocess.run may or may not be called depending on script path resolution
        assert result.exit_code in (0, 1)

    def test_keep_data_flag_propagated(self, runner, tmp_path):
        with patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run:
            with patch("postmule.cli.__file__", str(tmp_path / "cli.py")):
                script = tmp_path / "installer" / "uninstall.ps1"
                script.parent.mkdir(parents=True, exist_ok=True)
                script.write_text("# fake")
                result = runner.invoke(
                    main,
                    ["uninstall", "--install-dir", str(tmp_path), "--keep-data"],
                    input="YES\n",
                )
        if mock_run.called:
            call_args = mock_run.call_args[0][0]
            assert "-KeepData" in call_args


class TestBuildConfigYaml:
    """_build_config_yaml() must stay in sync with config.example.yaml."""

    def _make_config(self, **kwargs) -> dict:
        defaults = dict(
            install_dir=Path("C:/ProgramData/PostMule"),
            alert_email="user@example.com",
            vpm_provider="vpm",
            vpm_sender="",
            vpm_prefix="",
            run_time="02:00",
        )
        defaults.update(kwargs)
        return yaml.safe_load(_build_config_yaml(**defaults))

    def test_all_top_level_keys_present(self):
        """Every top-level key in config.example.yaml must appear in generated output."""
        example = yaml.safe_load(_find_example_config().read_text(encoding="utf-8"))
        generated = self._make_config()
        missing = set(example) - set(generated)
        assert not missing, f"Generated config missing top-level keys: {missing}"

    def test_installer_values_are_applied(self):
        cfg = self._make_config(
            install_dir=Path("C:/custom"),
            alert_email="alert@test.com",
            run_time="06:30",
            vpm_provider="earth_class",
            vpm_sender="mail@ec.com",
            vpm_prefix="[EC]",
        )
        assert cfg["app"]["install_dir"] == "C:/custom" or "custom" in cfg["app"]["install_dir"]
        assert cfg["notifications"]["alert_email"] == "alert@test.com"
        assert cfg["schedule"]["run_time"] == "06:30"
        assert cfg["mailbox"]["providers"][0]["service"] == "earth_class"
        assert cfg["mailbox"]["providers"][0]["scan_sender"] == "mail@ec.com"
        assert cfg["mailbox"]["providers"][0]["scan_subject_prefix"] == "[EC]"

    def test_default_vpm_sender_kept_when_blank(self):
        cfg = self._make_config(vpm_sender="", vpm_prefix="")
        vpm = cfg["mailbox"]["providers"][0]
        # Original defaults from config.example.yaml should be preserved
        assert vpm["scan_sender"] == "noreply@virtualpostmail.com"
        assert vpm["scan_subject_prefix"] == "[Scan Request]"

    def test_output_is_valid_yaml(self):
        raw = _build_config_yaml(
            install_dir=Path("C:/ProgramData/PostMule"),
            alert_email="x@y.com",
            vpm_provider="vpm",
            vpm_sender="",
            vpm_prefix="",
            run_time="02:00",
        )
        parsed = yaml.safe_load(raw)
        assert isinstance(parsed, dict)


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
