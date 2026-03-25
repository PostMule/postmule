# PostMule — Session Handoff

**On restart, say:** "Resume PostMule work from HANDOFF.md"

---

## Last Completed
Issues #35, #36, #37 — In-app Help section, GitHub docs, entity UI polish.
- **#37**: Entity expand button replaced with CSS-rotated chevron `›` (`.entity-expand-chevron`). `payment_address` field added to entity schema v3 (`entities.py` migrate + add_entity), API save handler, and entity detail panel (view + edit modes with textarea).
- **#36**: Created `docs/` with Mermaid diagrams: `architecture.md`, `workflows.md`, `providers.md`, `installation.md`, `configuration.md`. README updated with Mermaid graph + doc links.
- **#35**: Help nav item added (`/help`, `/help/installation`, `/help/configuration` routes). `architecture.svg` created. Help page block added to `page.html` with three tabs: Overview (SVG + components table + pipeline steps), Installation (step-by-step guide), Configuration (config section tables). 620 tests passing.

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
