# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
Issue #39 — In-app Feedback button (local-first logging):
- `postmule/data/feedback.py`: new module — `append_feedback(data_dir, entry)` and `list_feedback(data_dir)`; appends to `data/feedback.json` atomically
- `api.py`: reworked `/api/feedback` — always writes locally first, GitHub submission optional (only if PAT configured); removed contact/email field from payload and issue body; always returns 200 with `{"saved": true}`
- `page.html`: moved Feedback button from header nav to footer; removed contact email field from modal; added read-only context block (page, version, timestamp) + "For follow-up, email support@postmule.com" note; added `openFeedbackModal()` JS function that stamps timestamp at open time; updated `submitFeedback()` to send page/version context, removed 503 error branch
- `style.css`: replaced `.feedback-nav-btn` with `.app-footer-feedback`; added `.feedback-context`, `.feedback-context-*`, `.feedback-support-note` styles
- `mockup_dashboard.html`: same header/footer/modal/JS changes as page.html
- `tests/unit/test_data_feedback.py`: 7 tests, feedback.py at 100% coverage

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
