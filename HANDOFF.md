# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
Mockup sync — added all missing features to `mockup_dashboard.html`:
- **Help section**: added Help button to switcher bar, Help link to nav, full `sec-help` section (Overview/Installation/Configuration tabs matching page.html), `helpTab()` JS function, updated `NAV_MAP` to include `help`.
- **Feedback modal**: added CSS styles, updated Feedback button onclick to open modal, added full modal HTML (type selector, title, description, steps-to-reproduce, contact email, success state), added JS (`closeFeedbackModal`, `updateFeedbackType`, `submitFeedbackMockup`). Mockup uses a simulated success instead of calling `/api/feedback`.

## Next
Work the issues in this order (check `gh issue list --repo PostMule/app` for current state):

1. **#34** — Mail page inline reassignment UI
2. **#39** — In-app Feedback button
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
