# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
> Maintenance: before adding a new entry, delete the previous one. One issue max. Full history is in `git log`.

Issue #52 — Wire `mockup_email_daily.html` as Jinja2 template:
- `postmule/web/templates/email_daily.html` — production Jinja2 template derived from the mockup
- `postmule/agents/summary.py` — `_build_summary_html` now renders via Jinja2; new `_build_email_context` helper
- `docs/decisions.md` — new living doc for non-obvious design decisions (8 entries, issue refs)
- `docs/architecture.md` — added dry-run, API safety gate, 50-file cap invariants
- `HANDOFF.md` — Active Design Decisions now points to `docs/decisions.md`

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
