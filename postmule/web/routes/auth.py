"""Auth blueprint — login/logout routes and before_app_request auth guard."""

from __future__ import annotations

import hmac
import time

from flask import Blueprint, redirect, render_template, request, session, url_for

import postmule.web.app as _app

auth_bp = Blueprint("auth", __name__)


@auth_bp.app_context_processor
def inject_auth_state():
    from flask import session as _session
    pw = _app._dashboard_password()
    return {
        "auth_enabled": bool(pw),
        "is_authenticated": bool(_session.get("authenticated")),
    }


@auth_bp.before_app_request
def require_auth():
    if request.endpoint in (
        "auth.login",
        "auth.logout",
        "static",
        "connections.setup_oauth_google_callback",
    ) or (request.endpoint and request.endpoint.startswith("setup.")):
        return
    pw = _app._dashboard_password()
    if not pw:
        return
    if not session.get("authenticated"):
        return redirect(url_for("auth.login"))
    if time.time() - session.get("auth_time", 0) > _app._SESSION_TIMEOUT:
        session.clear()
        return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("pages.home"))
    error = None
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        if _app._is_locked_out(ip):
            error = "Too many failed attempts. Try again in 15 minutes."
        else:
            pw = _app._dashboard_password()
            submitted = request.form.get("password", "")
            if pw and hmac.compare_digest(submitted.encode(), pw.encode()):
                _app._clear_attempts(ip)
                session["authenticated"] = True
                session["auth_time"] = time.time()
                return redirect(url_for("pages.home"))
            _app._record_failed_attempt(ip)
            error = "Incorrect password"
    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
