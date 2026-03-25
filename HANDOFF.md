# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
Issue #34 — Mail page inline reassignment UI:
- `bills/notices/forward_to_me.py`: added `set_category_override(data_dir, id, category)` (soft override, mirrors `entity_override_id` pattern)
- `api.py`: new `POST /api/mail/<id>/category` endpoint (respects dry_run); valid categories: Bill, Notice, ForwardToMe, Personal, Junk, NeedsReview
- `pages.py`: mail route honors `category_override` field when setting `_type` on items
- `page.html`: replaced `entityPicker` x-data on mail items with new `mailReassign` Alpine component — Edit button expands inline row with category chip picker + entity search + one Save button for both
- `style.css`: added `.mail-edit-btn`, `.mail-edit-row`, `.cat-chip`, `.cat-chip--active` styles
- `mockup_dashboard.html`: Edit button on all items; Verizon item shows open edit panel

## Next
Work the issues in this order (check `gh issue list --repo PostMule/app` for current state):

1. **#39** — In-app Feedback button (note: feedback modal HTML + `/api/feedback` GitHub endpoint already exist in `page.html` and `api.py`; issue needs local-first `data/feedback.json` log + footer placement + context fields)
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
