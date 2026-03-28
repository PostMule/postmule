# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
> Maintenance: before adding a new entry, delete the previous one. One issue max. Full history is in `git log`.

Issue #63 — Owner Registry complete:
- New `postmule/data/owners.py`: full CRUD + `resolve_owner_ids()` (exact/case-insensitive name+short_name match)
- `owner_ids: list[str]` added to all mail record types (bills, notices, forward_to_me) via `set_owner_ids()`
- `ProcessedMail` dataclass gets `owner_ids` field; `classify_pdf()` auto-resolves from LLM recipients if `owners` passed
- 5 new API routes: GET/POST/PATCH/DELETE `/api/owners`, PUT `/api/mail/<id>/owners`
- Owner filter dropdown added to mail list; owner badges on mail items; Owners tab in Settings
- Full test coverage: `test_data_owners.py` (34 tests), owners tests in bills/notices/ftm, classification, web routes
- Full suite: 808 tests, 73% coverage

---

## Next
> Check `gh issue list --repo PostMule/app` for current state before starting.
> Do not suggest or offer to work on blocked or deferred issues — only note they exist.

**Blocked/Deferred (do not action):**
- #30 — End-to-end validation (BLOCKED)

**Ready to work:** none — await user direction.

---

## Active Design Decisions
> Maintained in `docs/decisions.md`. Check there for the current list.
