"""
PostMule CLI — entry point for the `postmule` command.

Usage:
  postmule                          Run full daily pipeline
  postmule --dry-run                Simulate run, no writes
  postmule --agent email            Run only the email ingestion agent
  postmule --status                 Show last run status
  postmule --verify                 Run integrity check
  postmule --logs                   Print tail of today's verbose log
  postmule --retroactive            Process all existing PDFs
  postmule --encrypt-credentials    Encrypt credentials.yaml -> credentials.enc
  postmule --set-master-password    Store master password in the system keyring
  postmule --update-config          Open config.yaml in default editor
  postmule --update-credentials     Open credentials.yaml in default editor
  postmule uninstall                Remove PostMule and all scheduled tasks
  postmule uninstall --keep-data    Remove PostMule but keep JSON data + credentials.enc
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click
import yaml

from postmule.core.config import ConfigError, load_config
from postmule.core.credentials import CredentialsError
from postmule.core.logging_setup import setup_logging

APP_NAME = "PostMule"
DEFAULT_ENC = Path("credentials.enc")


def _resolve_default_config() -> Path:
    """
    Locate config.yaml without relying on cwd (safe for Task Scheduler).

    Search order:
      1. POSTMULE_CONFIG env var
      2. ./config.yaml  (dev / running from install dir)
      3. %APPDATA%/PostMule/config.yaml  (Windows standard install)
      4. ~/.postmule/config.yaml         (macOS / Linux)
    """
    if env := os.environ.get("POSTMULE_CONFIG"):
        return Path(env)
    local = Path("config.yaml")
    if local.exists():
        return local
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidate = Path(appdata) / "PostMule" / "config.yaml"
        if candidate.exists():
            return candidate
    home_candidate = Path.home() / ".postmule" / "config.yaml"
    if home_candidate.exists():
        return home_candidate
    return local  # let the caller produce a clear "not found" error


DEFAULT_CONFIG = _resolve_default_config()


def _setup(config_path: Path, dry_run: bool = False):
    """Load config and set up logging. Returns Config object."""
    cfg = load_config(config_path)
    if dry_run:
        cfg._data["app"]["dry_run"] = True
    log_dir = Path(cfg.get("app", "install_dir", default=".")) / "logs"
    setup_logging(
        log_dir=log_dir,
        verbose_days=cfg.get("logging", "verbose_days", default=7),
        processing_years=cfg.get("logging", "processing_years", default=3),
        level=cfg.get("logging", "level", default="INFO"),
    )
    return cfg


@click.group(invoke_without_command=True)
@click.option("--dry-run", is_flag=True, help="Simulate all actions without writing anything.")
@click.option("--agent", default=None, help="Run a single agent: email | ocr | classify | summarize")
@click.option("--config", default=str(DEFAULT_CONFIG), help="Path to config.yaml")
@click.pass_context
def main(ctx: click.Context, dry_run: bool, agent: str | None, config: str) -> None:
    """PostMule — AI-powered physical mail management."""
    if ctx.invoked_subcommand is not None:
        return

    try:
        cfg = _setup(Path(config), dry_run=dry_run)
    except ConfigError as exc:
        click.echo(f"\nConfiguration error:\n\n{exc}\n", err=True)
        sys.exit(1)

    if dry_run:
        click.echo("[DRY RUN] No files will be written or moved.")

    if agent:
        _run_single_agent(agent, cfg)
    else:
        _run_full_pipeline(cfg)


def _run_full_pipeline(cfg) -> None:
    from postmule.core.credentials import CredentialsError, load_credentials
    from postmule.pipeline import run_daily_pipeline

    install_dir = Path(cfg.get("app", "install_dir", default="."))
    data_dir = install_dir / "data"
    enc_path = install_dir / cfg.get("credentials", "enc_file", default="credentials.enc")

    try:
        credentials = load_credentials(enc_path)
    except CredentialsError:
        credentials = {}
        click.echo("[WARNING] credentials.enc not found — smtp/finance/llm credentials unavailable.")

    click.echo("PostMule daily run starting...")
    stats = run_daily_pipeline(cfg, credentials, data_dir, dry_run=cfg.dry_run)
    status = stats.get("status", "unknown")
    pdfs = stats.get("pdfs_processed", 0)
    click.echo(f"Done. Status: {status} | PDFs processed: {pdfs} | Errors: {len(stats.get('errors', []))}")


def _run_single_agent(agent: str, cfg) -> None:
    valid = {"email", "ocr", "classify", "summarize"}
    if agent not in valid:
        click.echo(f"Unknown agent '{agent}'. Valid options: {', '.join(sorted(valid))}", err=True)
        sys.exit(1)
    click.echo(f"Running agent: {agent} (not yet implemented)")


@main.command()
@click.option("--config", default=str(DEFAULT_CONFIG))
def status(config: str) -> None:
    """Show the status of the last run."""
    click.echo("Status: (not yet implemented)")


@main.command()
@click.option("--config", default=str(DEFAULT_CONFIG))
def verify(config: str) -> None:
    """Run integrity verification across all data stores."""
    click.echo("Integrity verification: (not yet implemented)")


@main.command()
@click.option("--config", default=str(DEFAULT_CONFIG))
def retroactive(config: str) -> None:
    """Process all existing PDFs retroactively."""
    click.echo("Retroactive processing: (not yet implemented)")


@main.command("encrypt-credentials")
@click.option("--yaml-file", default="credentials.yaml", help="Path to credentials.yaml")
@click.option("--enc-file", default=str(DEFAULT_ENC), help="Output path for credentials.enc")
def encrypt_credentials(yaml_file: str, enc_file: str) -> None:
    """Encrypt credentials.yaml into credentials.enc."""
    from postmule.core.credentials import CredentialsError, encrypt_credentials as _enc

    yaml_path = Path(yaml_file)
    enc_path = Path(enc_file)

    password = click.prompt("Master password", hide_input=True, confirmation_prompt=True)
    try:
        _enc(yaml_path, enc_path, password)
        click.echo(f"Credentials encrypted to: {enc_path}")
        click.echo("You can now delete credentials.yaml (keep credentials.enc as your backup).")
    except CredentialsError as exc:
        click.echo(f"\nEncryption failed:\n{exc}\n", err=True)
        sys.exit(1)


@main.command("set-master-password")
def set_master_password() -> None:
    """Store the master password in the system keyring."""
    from postmule.core.credentials import CredentialsError, save_master_password as _save

    password = click.prompt("New master password", hide_input=True, confirmation_prompt=True)
    try:
        _save(password)
        click.echo("Master password saved to the system keyring.")
    except CredentialsError as exc:
        click.echo(f"\nFailed:\n{exc}\n", err=True)
        sys.exit(1)


@main.command("update-config")
@click.option("--config", default=str(DEFAULT_CONFIG))
def update_config(config: str) -> None:
    """Open config.yaml in the default editor."""
    path = Path(config)
    if not path.exists():
        click.echo(f"config.yaml not found at {path}. Copy config.example.yaml first.", err=True)
        sys.exit(1)
    click.launch(str(path))


@main.command()
@click.option("--lines", default=50, help="Number of lines to show.")
def logs(lines: int) -> None:
    """Print the tail of today's verbose log."""
    import datetime
    today = datetime.date.today().isoformat()
    # Try to find the log file relative to install_dir or cwd
    candidates = [
        Path("logs") / "verbose" / f"{today}.log",
        Path("C:/ProgramData/PostMule/logs/verbose") / f"{today}.log",
    ]
    for path in candidates:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                all_lines = f.readlines()
            click.echo("".join(all_lines[-lines:]))
            return
    click.echo(f"No verbose log found for today ({today}).")


@main.command("backup")
@click.option("--config", default=str(DEFAULT_CONFIG), help="Path to config.yaml")
@click.option("--dry-run", is_flag=True, help="Build the ZIP but don't upload it.")
def backup(config: str, dry_run: bool) -> None:
    """Create an on-demand backup and upload it to cloud storage."""
    from postmule.agents.backup import run_backup
    from postmule.core.credentials import CredentialsError, load_credentials

    cfg = _setup(Path(config))
    install_dir = Path(cfg.get("app", "install_dir", default="."))
    data_dir = install_dir / "data"
    enc_path = install_dir / cfg.get("credentials", "enc_file", default="credentials.enc")
    config_path = Path(config)

    try:
        credentials = load_credentials(enc_path)
    except CredentialsError:
        credentials = {}
        click.echo("[WARNING] credentials.enc not found — backup may fail.")

    if dry_run:
        click.echo("[DRY RUN] No files will be uploaded.")

    result = run_backup(cfg, credentials, data_dir, config_path, enc_path, dry_run=dry_run)

    if result["status"] == "ok":
        size_kb = result["bytes_uploaded"] / 1024
        click.echo(f"Backup complete: {result['backup_name']} ({size_kb:.1f} KB, {len(result['files_included'])} files)")
        if result["pruned_count"]:
            click.echo(f"Pruned {result['pruned_count']} old backup(s).")
    else:
        click.echo(f"Backup failed: {result['error']}", err=True)
        sys.exit(1)


@main.command("restore")
@click.option("--config", default=str(DEFAULT_CONFIG), help="Path to config.yaml")
@click.option("--from-backup", "backup_name", default=None, help="Exact backup filename or 'latest'.")
@click.option("--list", "list_only", is_flag=True, help="List available backups without restoring.")
@click.option("--dry-run", is_flag=True, help="Show what would be restored without extracting files.")
def restore(config: str, backup_name: str | None, list_only: bool, dry_run: bool) -> None:
    """Restore PostMule data from a cloud backup."""
    from postmule.agents.backup import list_backups, run_restore
    from postmule.core.credentials import CredentialsError, load_credentials

    cfg = _setup(Path(config))
    install_dir = Path(cfg.get("app", "install_dir", default="."))
    data_dir = install_dir / "data"
    enc_path = install_dir / cfg.get("credentials", "enc_file", default="credentials.enc")

    try:
        credentials = load_credentials(enc_path)
    except CredentialsError:
        credentials = {}
        click.echo("[WARNING] credentials.enc not found — restore may fail.")

    if list_only:
        backups = list_backups(cfg, credentials)
        if not backups:
            click.echo("No backups found in cloud storage.")
            return
        click.echo(f"{'Backup Name':<42}  {'Date':<20}  Size")
        click.echo("-" * 72)
        for b in backups:
            size_kb = b["size_bytes"] / 1024
            click.echo(f"{b['name']:<42}  {b['date']:<20}  {size_kb:.1f} KB")
        return

    if not backup_name:
        click.echo("Specify --from-backup <name> or 'latest', or use --list to see available backups.", err=True)
        sys.exit(1)

    if dry_run:
        click.echo("[DRY RUN] No files will be written.")

    if not click.confirm(f"Restore from '{backup_name}'? This will overwrite local data files."):
        click.echo("Cancelled.")
        return

    result = run_restore(cfg, credentials, backup_name, data_dir, dry_run=dry_run)

    if result["status"] == "ok":
        click.echo(f"Restore complete: {result['backup_name']} ({len(result['files_restored'])} files restored)")
    else:
        click.echo(f"Restore failed: {result['error']}", err=True)
        sys.exit(1)


@main.command("uninstall")
@click.option("--install-dir", default="C:\\ProgramData\\PostMule", help="Installation directory to remove.")
@click.option("--keep-data", is_flag=True, help="Keep JSON data files and credentials.enc.")
def uninstall(install_dir: str, keep_data: bool) -> None:
    """Remove PostMule, the scheduled task, and the PATH entry."""
    import subprocess
    from pathlib import Path as _Path

    script = _Path(__file__).parent.parent / "installer" / "uninstall.ps1"
    if not script.exists():
        click.echo(f"Uninstall script not found at {script}.", err=True)
        sys.exit(1)

    click.echo("This will remove PostMule from your system.")
    click.echo(f"  Install dir : {install_dir}")
    click.echo(f"  Keep data   : {keep_data}")
    if not click.confirm("\nContinue?"):
        click.echo("Cancelled.")
        return

    args = [
        "powershell.exe", "-ExecutionPolicy", "Bypass",
        "-File", str(script),
        "-InstallDir", install_dir,
    ]
    if keep_data:
        args.append("-KeepData")

    result = subprocess.run(args)
    sys.exit(result.returncode)


@main.command("configure")
@click.option("--data-dir", required=True, help="PostMule data directory (config, credentials, logs).")
@click.option("--credentials-json", default="", help="Path to downloaded Google OAuth credentials.json.")
@click.option("--gemini-key", default="", help="Gemini API key.")
@click.option("--alert-email", required=True, help="Email address for alerts and daily summary.")
@click.option("--vpm-provider", default="vpm", help="Virtual mailbox provider slug (vpm | earth_class | traveling_mailbox | postscan).")
@click.option("--vpm-sender", default="", help="VPM scan notification sender email.")
@click.option("--vpm-prefix", default="", help="VPM scan notification subject prefix.")
@click.option("--run-time", default="02:00", help="Daily run time (HH:MM, 24-hour).")
def configure(
    data_dir: str,
    credentials_json: str,
    gemini_key: str,
    alert_email: str,
    vpm_provider: str,
    vpm_sender: str,
    vpm_prefix: str,
    run_time: str,
) -> None:
    """Non-interactive first-time setup — called by the installer wizard."""
    import secrets
    import shutil

    from postmule.core.credentials import CredentialsError
    from postmule.core.credentials import encrypt_credentials as _enc
    from postmule.core.credentials import save_master_password as _save_pw

    data_path = Path(data_dir)
    for sub in ("data", "logs/verbose", "logs/processing"):
        (data_path / sub).mkdir(parents=True, exist_ok=True)
    click.echo(f"Data directory: {data_path}")

    # Copy Google credentials JSON if provided
    if credentials_json and Path(credentials_json).exists():
        dest = data_path / "google_credentials.json"
        shutil.copy2(credentials_json, dest)
        click.echo(f"Google credentials → {dest}")

    # Write config.yaml
    config_path = data_path / "config.yaml"
    config_path.write_text(
        _build_config_yaml(data_path, alert_email, vpm_provider, vpm_sender, vpm_prefix, run_time),
        encoding="utf-8",
    )
    click.echo(f"config.yaml → {config_path}")

    # Write and encrypt credentials
    if gemini_key:
        creds_yaml = data_path / "credentials.yaml"
        creds_yaml.write_text(f'gemini:\n  api_key: "{gemini_key}"\n', encoding="utf-8")
        master_password = secrets.token_urlsafe(32)
        try:
            _save_pw(master_password)
        except CredentialsError as exc:
            click.echo(f"[WARNING] Keyring save failed: {exc}", err=True)
        enc_path = data_path / "credentials.enc"
        try:
            _enc(creds_yaml, enc_path, master_password)
            creds_yaml.unlink()
            click.echo(f"Credentials encrypted → {enc_path}")
        except CredentialsError as exc:
            click.echo(f"[WARNING] Encryption failed: {exc}", err=True)

    # Register Task Scheduler entry
    _do_install_task(run_time, str(data_path))
    click.echo("PostMule configured successfully.")


def _find_example_config() -> Path:
    """Locate config.example.yaml in both dev and PyInstaller environments."""
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller extracts bundled data to sys._MEIPASS
        return Path(sys._MEIPASS) / "config.example.yaml"
    # Dev: postmule/cli.py → two levels up = repo root
    return Path(__file__).parent.parent / "config.example.yaml"


def _build_config_yaml(
    install_dir: Path,
    alert_email: str,
    vpm_provider: str,
    vpm_sender: str,
    vpm_prefix: str,
    run_time: str,
) -> str:
    """Return a populated config.yaml string derived from config.example.yaml.

    Reads config.example.yaml as the single source of truth, overlays the
    user-supplied installer values, and re-serializes.  Any new keys added to
    config.example.yaml are automatically included in all future installs.
    """
    example_path = _find_example_config()
    cfg = yaml.safe_load(example_path.read_text(encoding="utf-8"))

    cfg["app"]["install_dir"] = str(install_dir)
    cfg["schedule"]["run_time"] = run_time
    cfg["notifications"]["alert_email"] = alert_email

    vpm = cfg["mailbox"]["providers"][0]
    vpm["service"] = vpm_provider
    if vpm_sender:
        vpm["scan_sender"] = vpm_sender
    if vpm_prefix:
        vpm["scan_subject_prefix"] = vpm_prefix

    header = "# PostMule configuration — generated by installer wizard\n"
    return header + yaml.dump(cfg, sort_keys=False, allow_unicode=True)


def _do_install_task(run_time: str, work_dir: str) -> None:
    """Register the Windows Task Scheduler daily task for PostMule."""
    import subprocess

    task_name = "PostMule Daily Run"
    exe = str(Path(sys.executable).parent / "postmule.exe")
    ps = (
        f'$action   = New-ScheduledTaskAction -Execute "{exe}" -WorkingDirectory "{work_dir}"; '
        f'$trigger  = New-ScheduledTaskTrigger -Daily -At "{run_time}"; '
        f'$settings = New-ScheduledTaskSettingsSet '
        f'  -ExecutionTimeLimit (New-TimeSpan -Hours 2) '
        f'  -RestartCount 1 -RestartInterval (New-TimeSpan -Minutes 30) '
        f'  -StartWhenAvailable; '
        f'if (Get-ScheduledTask -TaskName "{task_name}" -ErrorAction SilentlyContinue) {{ '
        f'  Unregister-ScheduledTask -TaskName "{task_name}" -Confirm:$false }}; '
        f'Register-ScheduledTask -TaskName "{task_name}" -Action $action -Trigger $trigger '
        f'  -Settings $settings -RunLevel Highest '
        f'  -Description "PostMule daily mail processing run" | Out-Null'
    )
    result = subprocess.run(
        ["powershell.exe", "-NonInteractive", "-Command", ps],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        click.echo(f"[WARNING] Task Scheduler registration failed: {result.stderr.strip()}", err=True)
    else:
        click.echo(f"Task '{task_name}' registered — runs daily at {run_time}.")


@main.command("install-task")
@click.option("--time", "run_time", default="02:00", show_default=True, help="Daily run time (HH:MM, 24-hour).")
@click.option("--work-dir", default=None, help="Working directory for the scheduled task.")
def install_task(run_time: str, work_dir: str | None) -> None:
    """Register PostMule as a Windows Task Scheduler daily task."""
    _do_install_task(run_time, work_dir or str(Path(sys.executable).parent.parent))


@main.command("uninstall-task")
def uninstall_task() -> None:
    """Remove the PostMule Windows Task Scheduler entry."""
    import subprocess

    task_name = "PostMule Daily Run"
    ps = (
        f'if (Get-ScheduledTask -TaskName "{task_name}" -ErrorAction SilentlyContinue) {{ '
        f'  Unregister-ScheduledTask -TaskName "{task_name}" -Confirm:$false; '
        f'  Write-Host "Task removed." '
        f'}} else {{ Write-Host "Task not found — nothing to remove." }}'
    )
    result = subprocess.run(
        ["powershell.exe", "-NonInteractive", "-Command", ps],
        capture_output=True, text=True,
    )
    click.echo((result.stdout or result.stderr).strip())


@main.command("serve")
@click.option("--config", default=str(DEFAULT_CONFIG), help="Path to config.yaml.")
@click.option("--port", default=5000, show_default=True, help="Dashboard port.")
@click.option("--host", default="127.0.0.1", show_default=True, help="Host to bind to.")
def serve(config: str, port: int, host: str) -> None:
    """Start the PostMule web dashboard."""
    from postmule.web.app import create_app

    cfg_path = Path(config)
    install_dir = cfg_path.parent if cfg_path.exists() else Path(".")
    flask_app = create_app(
        config_path=cfg_path if cfg_path.exists() else None,
        data_dir=install_dir / "data",
        enc_path=install_dir / "credentials.enc",
    )
    click.echo(f"PostMule dashboard → http://{host}:{port}/")
    flask_app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
