"""
PostMule web dashboard — Flask + HTMX + Tailwind CSS.

Routes:
  GET  /              Home / status dashboard
  GET  /mail          All mail items (paginated)
  GET  /bills         Bills list + pending matches
  GET  /forward       ForwardToMe items
  GET  /pending        Pending entity matches + bill matches
  GET  /entities       Entity list
  GET  /settings       Config editor
  GET  /logs           Log viewer
  GET  /setup          First-run setup wizard
  POST /api/approve    Approve a pending match
  POST /api/deny       Deny a pending match
  POST /api/run        Trigger a manual run
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template_string, request, session, url_for

from postmule.core.config import ConfigError, load_config
from postmule.data import bills as bills_data
from postmule.data import entities as entity_data
from postmule.data import forward_to_me as ftm_data
from postmule.data import notices as notices_data
from postmule.data import run_log as run_log_data

log = logging.getLogger("postmule.web")

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

# Config and data dir are set at startup
_config = None
_data_dir: Path = Path("data")
_enc_path: Path = Path("credentials.enc")


def create_app(
    config_path: Path | None = None,
    data_dir: Path | None = None,
    enc_path: Path | None = None,
) -> Flask:
    global _config, _data_dir, _enc_path
    if config_path:
        try:
            _config = load_config(config_path)
        except ConfigError:
            pass
    if data_dir:
        _data_dir = data_dir
    if enc_path:
        _enc_path = enc_path
    app.secret_key = os.urandom(24)
    return app


# ------------------------------------------------------------------
# Authentication
# ------------------------------------------------------------------

def _dashboard_password() -> str | None:
    """Return configured dashboard password, or None if auth is disabled."""
    return _config and _config.get("dashboard", "password") or None


@app.before_request
def require_auth():
    if request.endpoint in ("login", "logout", "static"):
        return
    pw = _dashboard_password()
    if pw and not session.get("authenticated"):
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        pw = _dashboard_password()
        if request.form.get("password") == pw:
            session["authenticated"] = True
            return redirect(url_for("home"))
        error = "Incorrect password"
    return render_template_string(_LOGIN_TEMPLATE, error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------

@app.route("/")
def home():
    last_run = run_log_data.get_last_run(_data_dir)
    pending_ftm = ftm_data.get_pending_items(_data_dir)
    bills_this_year = bills_data.load_bills(_data_dir)
    pending_bills = [b for b in bills_this_year if b.get("status") == "pending"]

    return render_template_string(
        _PAGE_TEMPLATE,
        page="home",
        title="Home",
        last_run=last_run,
        pending_ftm_count=len(pending_ftm),
        pending_bills_count=len(pending_bills),
        today=date.today().isoformat(),
    )


@app.route("/mail")
def mail():
    year = request.args.get("year", date.today().year, type=int)
    all_bills = bills_data.load_bills(_data_dir, year)
    all_notices = notices_data.load_notices(_data_dir, year)
    all_ftm = ftm_data.load_forward_to_me(_data_dir)

    items = (
        [{"_type": "Bill", **b} for b in all_bills]
        + [{"_type": "Notice", **n} for n in all_notices]
        + [{"_type": "ForwardToMe", **f} for f in all_ftm]
    )
    items.sort(key=lambda x: x.get("date_received", ""), reverse=True)

    return render_template_string(
        _PAGE_TEMPLATE,
        page="mail",
        title="Mail",
        items=items,
        year=year,
        today=date.today().isoformat(),
    )


@app.route("/bills")
def bills():
    year = request.args.get("year", date.today().year, type=int)
    all_bills = bills_data.load_bills(_data_dir, year)
    pending = [b for b in all_bills if b.get("status") == "pending"]
    return render_template_string(
        _PAGE_TEMPLATE,
        page="bills",
        title="Bills",
        bills=all_bills,
        pending_bills=pending,
        year=year,
        today=date.today().isoformat(),
    )


@app.route("/forward")
def forward():
    items = ftm_data.load_forward_to_me(_data_dir)
    pending = [i for i in items if i.get("forwarding_status") == "pending"]
    return render_template_string(
        _PAGE_TEMPLATE,
        page="forward",
        title="Forward To Me",
        items=items,
        pending=pending,
        today=date.today().isoformat(),
    )


@app.route("/pending")
def pending():
    pending_matches = entity_data.load_pending_matches(_data_dir)
    pending_only = [m for m in pending_matches if m.get("status") == "pending"]
    return render_template_string(
        _PAGE_TEMPLATE,
        page="pending",
        title="Pending Reviews",
        pending_matches=pending_only,
        today=date.today().isoformat(),
    )


@app.route("/entities")
def entities():
    all_entities = entity_data.load_entities(_data_dir)
    return render_template_string(
        _PAGE_TEMPLATE,
        page="entities",
        title="Entities",
        entities=all_entities,
        today=date.today().isoformat(),
    )


@app.route("/logs")
def logs():
    lines = _read_log_tail(50)
    return render_template_string(
        _PAGE_TEMPLATE,
        page="logs",
        title="Logs",
        log_lines=lines,
        today=date.today().isoformat(),
    )


@app.route("/setup")
def setup():
    return render_template_string(
        _PAGE_TEMPLATE,
        page="setup",
        title="Setup",
        today=date.today().isoformat(),
    )


# ------------------------------------------------------------------
# API endpoints (HTMX)
# ------------------------------------------------------------------

@app.route("/api/approve", methods=["POST"])
def api_approve():
    match_id = request.form.get("match_id")
    if not match_id:
        return jsonify({"error": "match_id required"}), 400

    pending = entity_data.load_pending_matches(_data_dir)
    entities = entity_data.load_entities(_data_dir)

    for match in pending:
        if match["id"] == match_id and match["status"] == "pending":
            match["status"] = "approved"
            for entity in entities:
                if entity["id"] == match["match_entity_id"]:
                    if match["proposed_name"] not in entity["aliases"]:
                        entity["aliases"].append(match["proposed_name"])
                    break
            entity_data.save_pending_matches(_data_dir, pending)
            entity_data.save_entities(_data_dir, entities)
            return jsonify({"ok": True})

    return jsonify({"error": "match not found"}), 404


@app.route("/api/deny", methods=["POST"])
def api_deny():
    match_id = request.form.get("match_id")
    if not match_id:
        return jsonify({"error": "match_id required"}), 400

    pending = entity_data.load_pending_matches(_data_dir)
    for match in pending:
        if match["id"] == match_id:
            match["status"] = "denied"
            entity_data.save_pending_matches(_data_dir, pending)
            return jsonify({"ok": True})

    return jsonify({"error": "match not found"}), 404


@app.route("/api/run", methods=["POST"])
def api_run():
    if _config is None:
        return jsonify({"error": "No config loaded"}), 500
    dry_run = request.form.get("dry_run", "false").lower() == "true"

    def _run():
        from postmule.core.credentials import CredentialsError, load_credentials
        from postmule.pipeline import run_daily_pipeline
        try:
            creds = load_credentials(_enc_path)
            run_daily_pipeline(_config, creds, _data_dir, dry_run=dry_run)
        except CredentialsError as exc:
            log.error(f"Pipeline aborted — credentials error: {exc}")
        except Exception as exc:
            log.error(f"Pipeline run failed: {exc}")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "message": "Run started"})


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _read_log_tail(lines: int) -> list[str]:
    today = date.today().isoformat()
    candidates = [
        _data_dir.parent / "logs" / "verbose" / f"{today}.log",
        Path("logs") / "verbose" / f"{today}.log",
    ]
    for path in candidates:
        if path.exists():
            with path.open("r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            return [l.rstrip() for l in all_lines[-lines:]]
    return [f"No log file found for {today}"]


# ------------------------------------------------------------------
# Minimal inline template (brand-consistent)
# ------------------------------------------------------------------

_LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>PostMule — Login</title>
  <style>
    body { background: #F5F6F8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
    .card { background: white; border-radius: 10px; border: 1px solid #DDE3EC; padding: 32px; width: 320px; }
    h1 { font-size: 20px; color: #0F2044; margin: 0 0 24px; }
    input { width: 100%; padding: 9px 12px; border: 1px solid #DDE3EC; border-radius: 6px;
            font-size: 14px; box-sizing: border-box; margin-bottom: 12px; }
    button { width: 100%; padding: 10px; background: #0F2044; color: white; border: none;
             border-radius: 6px; font-size: 14px; cursor: pointer; }
    .error { color: #C62828; font-size: 12px; margin-bottom: 10px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Post<span style="color:#E8A020;">Mule</span></h1>
    <form method="post">
      {% if error %}<div class="error">{{ error }}</div>{% endif %}
      <input type="password" name="password" placeholder="Dashboard password" autofocus>
      <button type="submit">Sign in</button>
    </form>
  </div>
</body>
</html>
"""

_NAV_ITEMS = [
    ("home", "/", "Home"),
    ("mail", "/mail", "Mail"),
    ("bills", "/bills", "Bills"),
    ("forward", "/forward", "Forward To Me"),
    ("pending", "/pending", "Pending"),
    ("entities", "/entities", "Entities"),
    ("logs", "/logs", "Logs"),
    ("setup", "/setup", "Setup"),
]

_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PostMule — {{ title }}</title>
  <script>
    function pmPost(url, data, onSuccess) {
      fetch(url, {method: 'POST', body: new URLSearchParams(data)})
        .then(r => r.json())
        .then(j => { if (j.ok && onSuccess) onSuccess(); })
        .catch(e => console.error(e));
    }
  </script>
  <style>
    body { background: #F5F6F8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
    .nav-link { color: #5A7CA4; font-size: 13px; padding: 6px 12px; border-radius: 4px; text-decoration: none; }
    .nav-link:hover, .nav-link.active { background: #1a3060; color: white; }
  </style>
</head>
<body>
  <!-- Header -->
  <div style="background:#0F2044;padding:0 24px;">
    <div style="max-width:1100px;margin:0 auto;display:flex;align-items:center;gap:24px;height:52px;">
      <a href="/" style="font-size:18px;font-weight:600;color:white;text-decoration:none;">
        Post<span style="color:#E8A020;">Mule</span>
      </a>
      <nav style="display:flex;gap:4px;flex:1;">
        {% for key, href, label in nav_items %}
        <a href="{{ href }}" class="nav-link {% if page == key %}active{% endif %}">{{ label }}</a>
        {% endfor %}
      </nav>
      <div style="color:#5A7CA4;font-size:11px;">{{ today }}</div>
    </div>
  </div>

  <!-- Content -->
  <div style="max-width:1100px;margin:24px auto;padding:0 24px;">

    {% if page == 'home' %}
    <h1 style="font-size:22px;font-weight:600;color:#0F2044;margin-bottom:16px;">Dashboard</h1>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px;">
      <div style="background:white;border-radius:8px;border:1px solid #DDE3EC;padding:16px;">
        <div style="font-size:11px;color:#7A90A8;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">Last Run</div>
        <div style="font-size:14px;color:#0F2044;font-weight:600;">
          {% if last_run %}{{ last_run.get('end_time','')[:16] }} &mdash; {{ last_run.get('status','') }}{% else %}Never{% endif %}
        </div>
      </div>
      <div style="background:white;border-radius:8px;border:1px solid #DDE3EC;padding:16px;">
        <div style="font-size:11px;color:#7A90A8;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">Awaiting Forwarding</div>
        <div style="font-size:22px;font-weight:600;color:{% if pending_ftm_count > 0 %}#C62828{% else %}#2E7D32{% endif %};">{{ pending_ftm_count }}</div>
      </div>
      <div style="background:white;border-radius:8px;border:1px solid #DDE3EC;padding:16px;">
        <div style="font-size:11px;color:#7A90A8;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">Pending Bills</div>
        <div style="font-size:22px;font-weight:600;color:#E8A020;">{{ pending_bills_count }}</div>
      </div>
    </div>
    <div style="display:flex;gap:12px;">
      <button onclick="pmPost('/api/run', {dry_run: 'false'})"
              style="background:#0F2044;color:white;padding:10px 20px;border:none;border-radius:6px;font-size:13px;cursor:pointer;">
        Run Now
      </button>
      <button onclick="pmPost('/api/run', {dry_run: 'true'})"
              style="background:#F5F6F8;color:#0F2044;padding:10px 20px;border:1px solid #DDE3EC;border-radius:6px;font-size:13px;cursor:pointer;">
        Dry Run
      </button>
    </div>

    {% elif page == 'mail' %}
    <h1 style="font-size:22px;font-weight:600;color:#0F2044;margin-bottom:16px;">Mail</h1>
    {% for item in items %}
    {% set bar = {'Bill':'#E8A020','Notice':'#7A9CC4','ForwardToMe':'#C62828','Personal':'#7A9CC4','Junk':'#DDE3EC','NeedsReview':'#7A9CC4'} %}
    <div style="background:white;border-radius:8px;border:1px solid #DDE3EC;margin-bottom:8px;display:flex;overflow:hidden;">
      <div style="width:3px;background:{{ bar.get(item._type,'#DDE3EC') }};flex-shrink:0;"></div>
      <div style="padding:12px 16px;flex:1;">
        <div style="display:flex;justify-content:space-between;">
          <div style="font-weight:600;color:#0F2044;">{{ item.get('sender','Unknown') }}</div>
          <div style="font-size:11px;color:#B8C8D8;">{{ item.get('date_received','') }}</div>
        </div>
        <div style="font-size:12px;color:#5A7090;margin-top:2px;">{{ item.get('summary','') }}</div>
        <span style="display:inline-block;font-size:10px;font-weight:600;letter-spacing:0.8px;padding:2px 8px;border-radius:4px;margin-top:6px;background:#EEF3F9;color:#2C4A6E;border:1px solid #C0D0E4;">
          {{ item._type.upper() }}
        </span>
      </div>
    </div>
    {% else %}
    <div style="color:#7A90A8;font-size:13px;">No mail items found.</div>
    {% endfor %}

    {% elif page == 'bills' %}
    <h1 style="font-size:22px;font-weight:600;color:#0F2044;margin-bottom:16px;">Bills</h1>
    <table style="width:100%;border-collapse:collapse;background:white;border-radius:8px;border:1px solid #DDE3EC;overflow:hidden;">
      <thead>
        <tr style="background:#F5F6F8;">
          <th style="padding:10px 14px;text-align:left;font-size:11px;color:#5A7090;">Sender</th>
          <th style="padding:10px 14px;text-align:left;font-size:11px;color:#5A7090;">Amount</th>
          <th style="padding:10px 14px;text-align:left;font-size:11px;color:#5A7090;">Due</th>
          <th style="padding:10px 14px;text-align:left;font-size:11px;color:#5A7090;">Status</th>
        </tr>
      </thead>
      <tbody>
      {% for bill in bills %}
        <tr style="border-top:1px solid #DDE3EC;">
          <td style="padding:10px 14px;color:#0F2044;font-weight:500;">{{ bill.get('sender','') }}</td>
          <td style="padding:10px 14px;color:#0F2044;">${{ '%.2f'|format(bill.get('amount_due',0)) }}</td>
          <td style="padding:10px 14px;color:#E8A020;">{{ bill.get('due_date','') }}</td>
          <td style="padding:10px 14px;font-size:11px;">
            <span style="background:#EEF3F9;color:#2C4A6E;padding:2px 8px;border-radius:4px;border:1px solid #C0D0E4;">{{ bill.get('status','pending').upper() }}</span>
          </td>
        </tr>
      {% else %}
        <tr><td colspan="4" style="padding:16px;text-align:center;color:#7A90A8;">No bills found.</td></tr>
      {% endfor %}
      </tbody>
    </table>

    {% elif page == 'pending' %}
    <h1 style="font-size:22px;font-weight:600;color:#0F2044;margin-bottom:16px;">Pending Reviews</h1>
    {% for match in pending_matches %}
    <div data-match-row style="background:white;border-radius:8px;border:1px solid #DDE3EC;padding:14px 16px;margin-bottom:8px;display:flex;align-items:center;gap:16px;">
      <div style="flex:1;">
        <div style="font-weight:600;color:#0F2044;">"{{ match.proposed_name }}"</div>
        <div style="font-size:12px;color:#5A7090;">Looks like: {{ match.match_entity_id }} &mdash; similarity {{ '%.0f'|format(match.similarity * 100) }}%</div>
        <div style="font-size:11px;color:#B8C8D8;">Auto-approves: {{ match.auto_approve_after }}</div>
      </div>
      <button onclick="pmPost('/api/approve', {match_id: '{{ match.id }}'}, () => this.closest('[data-match-row]').remove())"
              style="background:#0F2044;color:white;padding:6px 14px;border:none;border-radius:4px;font-size:12px;cursor:pointer;">Approve</button>
      <button onclick="pmPost('/api/deny', {match_id: '{{ match.id }}'}, () => this.closest('[data-match-row]').remove())"
              style="background:#F5F6F8;color:#C62828;padding:6px 14px;border:1px solid #FFCDD2;border-radius:4px;font-size:12px;cursor:pointer;">Deny</button>
    </div>
    {% else %}
    <div style="color:#7A90A8;font-size:13px;">No pending items.</div>
    {% endfor %}

    {% elif page == 'entities' %}
    <h1 style="font-size:22px;font-weight:600;color:#0F2044;margin-bottom:16px;">Entities</h1>
    {% for entity in entities %}
    <div style="background:white;border-radius:8px;border:1px solid #DDE3EC;padding:12px 16px;margin-bottom:8px;">
      <div style="display:flex;gap:8px;align-items:center;">
        <span style="font-weight:600;color:#0F2044;">{{ entity.canonical_name }}</span>
        <span style="font-size:10px;background:#EEF3F9;color:#2C4A6E;padding:2px 8px;border-radius:4px;border:1px solid #C0D0E4;">{{ entity.type }}</span>
      </div>
      {% if entity.aliases | length > 1 %}
      <div style="font-size:11px;color:#7A90A8;margin-top:4px;">Aliases: {{ entity.aliases | join(', ') }}</div>
      {% endif %}
    </div>
    {% else %}
    <div style="color:#7A90A8;font-size:13px;">No entities found. Run PostMule to discover entities from your mail.</div>
    {% endfor %}

    {% elif page == 'forward' %}
    <h1 style="font-size:22px;font-weight:600;color:#0F2044;margin-bottom:16px;">Forward To Me</h1>
    {% for item in pending %}
    <div style="background:white;border-radius:8px;border:1px solid #FFCDD2;padding:14px 16px;margin-bottom:8px;">
      <div style="color:#C62828;font-weight:600;font-size:13px;margin-bottom:4px;">ACTION REQUIRED</div>
      <div style="font-weight:600;color:#0F2044;">{{ item.get('sender','') }}</div>
      <div style="font-size:12px;color:#5A7090;">{{ item.get('summary','') }}</div>
      <div style="font-size:11px;color:#B8C8D8;margin-top:4px;">Received: {{ item.get('date_received','') }}</div>
    </div>
    {% else %}
    <div style="color:#2E7D32;font-size:13px;">No items awaiting forwarding.</div>
    {% endfor %}

    {% elif page == 'logs' %}
    <h1 style="font-size:22px;font-weight:600;color:#0F2044;margin-bottom:16px;">Logs</h1>
    <div style="background:#0F2044;border-radius:8px;padding:16px;font-family:monospace;font-size:11px;color:#7A9CC4;overflow-x:auto;white-space:pre-wrap;max-height:600px;overflow-y:auto;">
      {% for line in log_lines %}{{ line }}
{% endfor %}
    </div>

    {% elif page == 'setup' %}
    <h1 style="font-size:22px;font-weight:600;color:#0F2044;margin-bottom:8px;">Setup</h1>
    <p style="color:#5A7090;margin-bottom:24px;">Complete these steps to get PostMule running.</p>
    <div style="background:white;border-radius:8px;border:1px solid #DDE3EC;padding:20px;max-width:560px;">
      <ol style="color:#0F2044;line-height:2;">
        <li>Run <code style="background:#F5F6F8;padding:2px 6px;border-radius:4px;">postmule set-master-password</code> in your terminal</li>
        <li>Fill in <code style="background:#F5F6F8;padding:2px 6px;border-radius:4px;">credentials.yaml</code> with your Google OAuth credentials</li>
        <li>Run <code style="background:#F5F6F8;padding:2px 6px;border-radius:4px;">postmule encrypt-credentials</code></li>
        <li>Edit <code style="background:#F5F6F8;padding:2px 6px;border-radius:4px;">config.yaml</code> — set your alert email address</li>
        <li>Run <code style="background:#F5F6F8;padding:2px 6px;border-radius:4px;">postmule --dry-run</code> to verify everything works</li>
      </ol>
    </div>
    {% endif %}

  </div>
</body>
</html>
""".replace(
    "{% for key, href, label in nav_items %}",
    "{% set nav_items = " + str(_NAV_ITEMS) + " %}{% for key, href, label in nav_items %}"
)
