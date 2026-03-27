# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## On Restart — Always Do First
Before writing any code, check for and commit any uncommitted changes:
```
git status
git diff --stat
```
If files are modified, commit them before starting new work. Never let a session end with uncommitted changes.

---

## Last Completed
Issue #48 — Config generation derives from config.example.yaml at runtime:
- `postmule/cli.py`: added `_find_example_config()` (dev + PyInstaller via `sys._MEIPASS`); replaced 160-line f-string in `_build_config_yaml()` with ~25-line YAML overlay (`yaml.safe_load` → overlay → `yaml.dump`)
- `installer/build.ps1`: added `--add-data "config.example.yaml;."` to fallback PyInstaller invocation
- `tests/unit/test_cli.py`: 4 new tests in `TestBuildConfigYaml` — completeness (all top-level keys present), installer values applied, blank VPM defaults preserved, output is valid YAML

Issues #50 (fix 1) and #51 (short-term) — Provider Protocol enforcement + doc freshness:
- New: `.github/pull_request_template.md` — doc checklist on every PR (config, providers, mockup, /help, README, CLAUDE.md) + test reminders
- `email/storage/llm/spreadsheet base.py` — `health_check() -> HealthResult` added to each Protocol; omitting it now fails runtime `isinstance()` checks and type-checker validation
- `tests/unit/test_provider_protocols.py` — updated concrete mock classes to include `health_check()`
- Note: #50 fix 2 (test_provider_completeness.py) and fix 3 (CONTRIBUTING_PROVIDER.md) still open if desired

Issue #40 — Windows .exe installer with guided setup wizard:
- New: `installer/postmule.iss` — Inno Setup 6 script; 5 custom Pascal Script wizard pages:
  - Page 1: Google credentials.json (file picker via PowerShell OpenFileDialog, optional)
  - Page 2: Gemini API key (optional, masked)
  - Page 3: Alert email address (required)
  - Page 4: Virtual mailbox provider + sender email + subject prefix
  - Page 5: Daily run time (HH:MM, defaults to 02:00)
  - `CurStepChanged(ssPostInstall)` calls `postmule.exe configure` with all collected values
- New: `installer/build.ps1` — developer build script (PyInstaller → `dist/postmule/` → ISCC → `PostMuleSetup.exe`)
- Modified: `postmule/cli.py` — 4 new commands + 2 helpers:
  - `configure` — non-interactive setup called by installer (writes config.yaml, encrypts credentials, registers Task Scheduler)
  - `serve` — starts the Flask dashboard
  - `install-task` / `uninstall-task` — manage Windows Task Scheduler entry
  - `_build_config_yaml()` — generates config.yaml from installer inputs (VPM defaults to VPM sender/prefix if blank)
  - `_do_install_task()` — PowerShell `Register-ScheduledTask` helper
- Target audience: non-technical Windows 11 users; no Python or PowerShell interaction required

Issue #41 — Silent/scripted CLI install path for advanced users:
- New: `setup.ps1` — interactive + fully silent (`-AlertEmail`, `-GeminiApiKey`, `-VpmSender`, `-MasterPassword`, `-NoTaskScheduler`, `-DryRunOnly`)
- New: `setup.bat` — thin wrapper calling `setup.ps1` via `powershell -ExecutionPolicy Bypass`
- Updated: `README.md` — Prerequisites collapsible section + `setup.ps1` usage under Option B
- Updated: `docs/install-cli.md` — points to `setup.ps1` as the quickest path; manual steps remain as reference

Issue #45 — Split Outlook into two distinct provider entries:
- `outlook_365` → "Outlook / Microsoft 365" (org accounts, Azure AD OAuth)
- `outlook_com` → "outlook.com / Hotmail / Live" (personal accounts, IMAP/personal OAuth)
- Updated: `registry.py`, `outlook_365.py`, `outlook_com.py`, `page.html`, `mockup_dashboard.html`

Previously: Issues #44, #46, #47 — Providers tab improvements (all implemented together):

**#44 — Show and edit non-sensitive provider settings:**
- Flask route `POST /api/providers/<category>/config` in `connections.py` writes whitelisted fields (email→label_name, storage→root_folder, spreadsheet→workbook_name, llm→model) to config.yaml
- `_connection_status()` in `pages.py` now includes `label_name` in email dict
- Each active provider card has a Configure button that expands an inline form panel (Alpine.js `configOpen` toggle)

**#46 — Browseable catalog of available providers:**
- "Configured" section label above the active provider card (Jinja conditional)
- "Available" section label above inactive providers (uses `conn-provider--inactive` CSS class, auto-hides with toggle)
- "Show all providers" checkbox toggle (`showAll` Alpine state on the outer pane, `:class="{ 'hide-inactive': !showAll }"`)
- `.hide-inactive .conn-provider--inactive { display: none; }` already existed in style.css

**#47 — Connection health check with Test button:**
- `HealthResult` dataclass in `postmule/providers/__init__.py` (`ok`, `status`, `message`)
- `health_check()` added to all 5 provider adapters: GmailProvider, DriveProvider, SheetsProvider, GeminiProvider, VpmProvider
- Flask route `POST /api/providers/<category>/<service>/test` in `connections.py` instantiates provider and calls `health_check()`, returns JSON
- Each active card has Test button (Alpine.js fetch → reactive badge: idle/checking/ok/warn/error)
- New CSS class `.conn-provider-badge--error` added to `style.css`

All five tabs (Email, Storage, Spreadsheet, Physical Mail, AI/LLM) and `mockup_dashboard.html` updated.

Previously: Issues #42 and #43 — README overhaul + Help page overhaul

## Next
Work the issues in this order (check `gh issue list --repo PostMule/app` for current state):

1. **#49** — Installer build pipeline: PyInstaller spec + CI workflow (medium)
2. **#30** — End-to-end validation (BLOCKED — do not start; user will unblock manually)

## Mid-Session Decisions (active)
- **Friendly name is primary, must be unique.** Canonical `name` (LLM-extracted) shown as secondary muted text. Validation must block save if friendly_name already exists on another entity.
- **One entity per account number.** AT&T Mobile (****1234) and AT&T Internet (****5678) are two separate entity records, not one entity with two accounts. Matching uses account number + name; falls back to name-only when account is unknown.
- **Account number display:** strip all spaces and special chars, show last 4 as `****1234`.
- **Last payment column:** show last matched payment date + amount (e.g. "Mar 18 · $94.00") or `—` if none on record.
- **Mail reassignment UX:** small "Edit" link per item; expands a row below. Click the category badge to pick a new category. Click the entity name to pick from alphabetical list of friendly names. Save commits, Cancel collapses.
- **Aliases:** never shown in main entity table row; only visible in expanded chevron detail panel.
- **Issue #30 (end-to-end):** blocked with a GitHub comment; user will unblock when app is ready.

## Mid-Session Decisions (historical)
- `statement_date` and `ach_descriptor` on `ProcessedMail` have `default=None` to avoid breaking existing constructors.
- Step 1b (bill_email_intake) runs inside the same `with tempfile.TemporaryDirectory()` block as step 1a.
- Only Gmail is supported for bill_intake today; unsupported services log a warning and are skipped.
