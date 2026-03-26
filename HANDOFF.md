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
Issues #42 and #43 — README overhaul + Help page overhaul:

**#42 — README (dual-audience):**
- `README.md`: restructured for two audiences — plain-English hero + Get Started (installer vs CLI) for non-technical users; Technical Reference section with links at the bottom for developers; feature bullets rewritten without tech stack details
- `docs/install-cli.md`: new file absorbing CLI Quick Start content from README

**#43 — Help page (plain English, remove Installation, add Troubleshooting):**
- Both `mockup_dashboard.html` and `page.html` updated identically
- Removed Installation tab (wrong place — user hasn't installed yet)
- Overview → "How It Works": plain English description, mail categories table, where-your-data-lives paragraph; removed Components table (pdfplumber, Flask, etc.) and numbered pipeline steps
- Configuration → "Settings Reference": plain English description of each Settings section; no YAML field references
- Added Troubleshooting tab: 5 scenarios (not run today, missing email, needs review, unpaid bill, post-Windows-update breakage) + links to Logs page and GitHub Issues

Previously: Mockup interactivity — Mail tab Edit rows (mockup-only, no issue)

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
