# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
> Maintenance: before adding a new entry, delete the previous one. One issue max. Full history is in `git log`.

Issue #64 — Mail lifecycle (Open/Filed) complete:
- `set_filed(data_dir, id, bool)` added to `bills.py`, `notices.py`, `forward_to_me.py`
- `POST /api/mail/<id>/file` and `/api/mail/<id>/unfile` routes (dry-run aware)
- Main mail view (`pages.py`) filters out `filed=True` items by default
- File button added to all mail edit panels in `mockup_dashboard.html`
- Full suite: 823 tests, 74% coverage

---

## Next
> Check `gh issue list --repo PostMule/app` for current state before starting.
> Do not suggest or offer to work on blocked or deferred issues — only note they exist.

**Blocked/Deferred (do not action):**
- #30 — End-to-end validation (BLOCKED)

**Priority order (start at the top):**

Tier 1 — Core workflow (in order):
1. #65 — Reports section: unified mail search/archive — depends on #64 (done)
3. #66 — Remove year filter from main mail view — trivial cleanup, bundle at end of #65

Tier 2 — Provider breadth (self-hosted value prop):
4. #72 — LLM stubs: Ollama (offline/free), Anthropic, OpenAI — interface already defined, low risk
5. #69 — Email stubs: IMAP first (unblocks Yahoo/Fastmail/self-hosted), then Outlook, ProtonMail
6. #67 — Provider config UI — more valuable after more providers exist (#69, #72 done)

Tier 3 — Later:
7. #70 — Storage stubs (Dropbox, OneDrive, S3)
8. #71 — Spreadsheet stubs (Airtable, Excel Online)
9. #73 — Mailbox stubs (needs API investigation first)
10. #68 — Multi-email providers (most complex, depends on #67 + #69)

---

## Active Design Decisions
> Maintained in `docs/decisions.md`. Check there for the current list.
