# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
Issue #32 — Entity data model overhaul. Schema v3: `friendly_name` (unique, user-editable primary label), `account_number` scalar replaces `account_numbers` list. Migration v2→v3 splits multi-account entities into separate records. New helpers: `mask_account_number()`, `validate_friendly_name_unique()`, `find_entity_by_account()`. Entity discovery now does account-number primary matching; unrecognized accounts route to unassigned. API: friendly_name uniqueness (409), account endpoint sets single value. 620 tests passing.

## Next
Work the issues in this order (check `gh issue list --repo PostMule/app` for current state):

1. **#33** — Entities page UI overhaul (depends on #32 ✓)
2. **#34** — Mail page inline reassignment UI (independent, can be done any time)
3. **#30** — End-to-end validation (BLOCKED — do not start; user will unblock manually)

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
