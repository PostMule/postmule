# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
> Maintenance: before adding a new entry, delete the previous one. One issue max. Full history is in `git log`.

Issues #50 (all fixes) and #51 — Provider Protocol enforcement + doc freshness:
- `.github/pull_request_template.md` — doc checklist on every PR + test reminders
- `health_check() -> HealthResult` added to all 4 Protocol base classes; omitting it fails `isinstance()` checks
- `tests/unit/test_provider_completeness.py` — parametrized across all 17 concrete providers; class-level inspect, no credentials required
- `docs/CONTRIBUTING_PROVIDER.md` — step-by-step guide for adding a new provider
- `health_check()` added to 13 stubs (raise NotImplementedError): imap, outlook_365, outlook_com, proton, dropbox, onedrive, s3, anthropic, ollama, openai, airtable, excel_online

---

## Next
> Check `gh issue list --repo PostMule/app` for current state before starting.
> Do not suggest or offer to work on blocked or deferred issues — only note they exist.

**Blocked/Deferred (do not action):**
- #30 — End-to-end validation (BLOCKED)
- #29 — SQLite storage layer (DEFERRED)

**Ready to work:** none — await user direction.

---

## Active Design Decisions
> These capture non-obvious choices not derivable from the code. Remove entries once they are superseded or fully baked in.

- **Friendly name is primary, must be unique.** Canonical `name` (LLM-extracted) shown as secondary muted text. Validation must block save if friendly_name already exists on another entity.
- **One entity per account number.** AT&T Mobile (****1234) and AT&T Internet (****5678) are two separate entity records. Matching uses account number + name; falls back to name-only when account is unknown.
- **Account number display:** strip all spaces and special chars, show last 4 as `****1234`.
- **Last payment column:** show last matched payment date + amount (e.g. "Mar 18 · $94.00") or `—` if none on record.
- **Mail reassignment UX:** small "Edit" link per item; expands a row below. Click the category badge to pick a new category. Click the entity name to pick from alphabetical list of friendly names. Save commits, Cancel collapses.
- **Aliases:** never shown in main entity table row; only visible in expanded chevron detail panel.
- **Issue #30 (end-to-end):** blocked with a GitHub comment; user will unblock when app is ready.
