"""
Setup wizard blueprint — first-run configuration flow.

Routes:
  GET  /setup          Step landing — redirects to current step
  GET  /setup/step/1   Alert email
  GET  /setup/step/2   Gmail App Password + IMAP test
  GET  /setup/step/3   Gemini API key + API test
  GET  /setup/step/4   Master password + encrypt credentials
  POST /setup/step/<n> Submit a step
"""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for

import postmule.web.app as _app

setup_bp = Blueprint("setup", __name__)

_TOTAL_STEPS = 4


def _current_step() -> int:
    """Return the step the wizard should resume at based on session state."""
    return session.get("setup_step", 1)


@setup_bp.before_app_request
def require_setup_completion():
    """Redirect every page to the setup wizard until credentials.enc exists."""
    from flask import current_app
    if current_app.config.get("TESTING"):
        return
    if not _app._setup_required():
        return
    # Let setup routes and static files through
    ep = request.endpoint or ""
    if ep.startswith("setup.") or ep == "static":
        return
    return redirect(url_for("setup.step_get", step=_current_step()))


@setup_bp.route("/setup")
def wizard():
    return redirect(url_for("setup.step_get", step=_current_step()))


@setup_bp.route("/setup/step/<int:step>", methods=["GET"])
def step_get(step: int):
    if step < 1 or step > _TOTAL_STEPS:
        return redirect(url_for("setup.step_get", step=1))
    # Capture values entered in previous steps so the template can pre-fill
    saved = session.get("setup_data", {})
    return render_template(
        "setup.html",
        step=step,
        total_steps=_TOTAL_STEPS,
        saved=saved,
        error=session.pop("setup_error", None),
    )


@setup_bp.route("/setup/step/<int:step>", methods=["POST"])
def step_post(step: int):
    """Save form data for a step and advance to the next, or finish."""
    if step < 1 or step > _TOTAL_STEPS:
        return redirect(url_for("setup.step_get", step=1))

    data = session.setdefault("setup_data", {})

    if step == 1:
        alert_email = request.form.get("alert_email", "").strip()
        if not alert_email or "@" not in alert_email:
            session["setup_error"] = "Please enter a valid email address."
            return redirect(url_for("setup.step_get", step=1))
        data["alert_email"] = alert_email
        session["setup_step"] = 2
        return redirect(url_for("setup.step_get", step=2))

    if step == 2:
        gmail_address = request.form.get("gmail_address", "").strip()
        app_password = request.form.get("app_password", "").strip()
        if not gmail_address or "@" not in gmail_address:
            session["setup_error"] = "Please enter a valid Gmail address."
            return redirect(url_for("setup.step_get", step=2))
        if not app_password:
            session["setup_error"] = "Please enter your App Password."
            return redirect(url_for("setup.step_get", step=2))
        data["gmail_address"] = gmail_address
        data["app_password"] = app_password
        session["setup_step"] = 3
        return redirect(url_for("setup.step_get", step=3))

    if step == 3:
        gemini_key = request.form.get("gemini_key", "").strip()
        if not gemini_key:
            session["setup_error"] = "Please enter your Gemini API key."
            return redirect(url_for("setup.step_get", step=3))
        data["gemini_key"] = gemini_key
        session["setup_step"] = 4
        return redirect(url_for("setup.step_get", step=4))

    if step == 4:
        master_password = request.form.get("master_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not master_password:
            session["setup_error"] = "Please enter a master password."
            return redirect(url_for("setup.step_get", step=4))
        if master_password != confirm_password:
            session["setup_error"] = "Passwords do not match."
            return redirect(url_for("setup.step_get", step=4))
        data["master_password"] = master_password
        # Step 4 completion is handled by /setup/finish
        return redirect(url_for("setup.finish"))

    return redirect(url_for("setup.step_get", step=step))


@setup_bp.route("/setup/finish", methods=["POST", "GET"])
def finish():
    """Write config.yaml and credentials.enc, then redirect to the dashboard."""
    import secrets

    import yaml

    from postmule.core.credentials import CredentialsError
    from postmule.core.credentials import encrypt_credentials as _enc
    from postmule.core.credentials import save_master_password as _save_pw

    data = session.get("setup_data", {})
    required = ("alert_email", "gmail_address", "app_password", "gemini_key", "master_password")
    if not all(k in data for k in required):
        session["setup_error"] = "Some required fields are missing. Please start again."
        session["setup_step"] = 1
        return redirect(url_for("setup.step_get", step=1))

    config_path = _app._config_path
    enc_path = _app._enc_path
    install_dir = enc_path.parent

    # Write config.yaml via PyYAML (no string templates, no regex)
    try:
        if config_path and config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        else:
            cfg = {}
        cfg.setdefault("notifications", {})["alert_email"] = data["alert_email"]
        cfg.setdefault("gmail", {})["address"] = data["gmail_address"]
        out_path = config_path or (install_dir / "config.yaml")
        with open(out_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, sort_keys=False, allow_unicode=True)
    except Exception as exc:
        session["setup_error"] = f"Failed to write config.yaml: {exc}"
        session["setup_step"] = 1
        return redirect(url_for("setup.step_get", step=1))

    # Write credentials.yaml, encrypt to credentials.enc, delete plaintext
    creds_yaml = install_dir / "credentials.yaml"
    try:
        creds = {
            "gmail": {
                "address": data["gmail_address"],
                "app_password": data["app_password"],
            },
            "gemini": {
                "api_key": data["gemini_key"],
            },
        }
        creds_yaml.write_text(
            yaml.dump(creds, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        master_password = data["master_password"]
        _save_pw(master_password)
        _enc(creds_yaml, enc_path, master_password)
        creds_yaml.unlink()
    except CredentialsError as exc:
        session["setup_error"] = f"Failed to save credentials: {exc}"
        session["setup_step"] = 4
        if creds_yaml.exists():
            creds_yaml.unlink()
        return redirect(url_for("setup.step_get", step=4))
    finally:
        if creds_yaml.exists():
            creds_yaml.unlink()

    # Clear wizard session state
    session.pop("setup_data", None)
    session.pop("setup_step", None)

    return redirect("/?setup=done")
