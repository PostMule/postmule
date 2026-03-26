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
Issues #44, #46, #47 — Providers tab improvements (all implemented together):

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

1. **#30** — End-to-end validation (BLOCKED — do not start; user will unblock manually)

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
