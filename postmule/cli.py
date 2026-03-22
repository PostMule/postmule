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
  postmule --uninstall              Remove PostMule and all scheduled tasks
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

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


if __name__ == "__main__":
    main()
