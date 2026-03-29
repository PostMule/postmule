# PostMule — Design Decisions

Non-obvious decisions that would surprise a new contributor or be hard to infer from the code alone. Each entry notes the reasoning and links to the originating issue where one exists.

---

## Bill Matching

**Company name is not used for matching.**
Finance providers (YNAB, Simplifi, Plaid) overwrite the merchant name on transactions with their own normalized strings. These rarely match the biller name extracted from the PDF. Matching uses exact amount + exact statement date only. See #27 for the planned addition of ACH descriptor and statement date fields, which will make matching more reliable.

---

## Entity Model

**One entity per account number.**
AT&T Mobile (****1234) and AT&T Internet (****5678) are two separate entity records, not one entity with two accounts. This prevents ambiguous bill assignment and makes account-level matching precise. See #32.

**Friendly name is primary and must be unique.**
`friendly_name` is the user-editable label shown prominently in the UI. The canonical `name` (what the LLM/OCR extracts — e.g. "AT&T Mobility LLC") is shown as secondary muted text below it. Validation must block saving if `friendly_name` is already used by another entity. See #32.

**Account number is stored in full; displayed masked.**
Strip all spaces and special characters from the raw account number, then show the last 4 digits as `****1234`. The full value is stored in `entities.json` for matching. See #32, #33.

**Last Payment column shows matched payment only.**
Displays the most recent *matched* payment date and amount (e.g. "Mar 18 · $94.00"). Shows `—` if no payment has ever been matched to this entity. Unmatched pending bills do not contribute to this value. See #33.

**Aliases are only visible in the expanded detail panel.**
Aliases are never shown in the main entity table row — only in the chevron-expanded detail section below the row. This keeps the table scannable. See #33.

---

## Mail Reassignment

**Reassignment is inline, not a modal.**
Each mail item has a small "Edit" link. Clicking it expands a row directly below the item. The user clicks the category badge to pick a new category, or the entity name to pick from an alphabetical list of friendly names. Save commits; Cancel collapses without saving. See #34.

---

## Data Storage

**Google Sheets is a generated view and is never written to directly.**
All writes go to JSON files in `_System/data/`. The Sheets view is rebuilt from JSON on demand. If a user edits a cell in Sheets it will be overwritten on the next sync. This is intentional and must remain true even as new providers are added. See #14.

---

## Dashboard & Email Templates

**`mockup_dashboard.html` is the living mockup for the web dashboard.**
It is the design source of truth for the dashboard UI. `brand_reference.html` is the brand reference it was derived from. Any visual change to the dashboard must be reflected in `mockup_dashboard.html`.

**`mockup_email_daily.html` is the design reference for the daily summary email.**
The production Jinja2 template at `postmule/web/templates/email_daily.html` is derived from it. Any change to the email design should update both files together. See #52.
