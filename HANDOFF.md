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
> Maintained in `docs/decisions.md`. Check there for the current list.
