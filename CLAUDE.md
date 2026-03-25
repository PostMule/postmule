# PostMule — Claude Code Project Context

## Review Protocol — Required Every Session

Before writing any code, Claude must:
1. Re-read this entire CLAUDE.md file
2. Run `git log --oneline -15` to see recent commits
3. State in one sentence what is about to be built and how it fits the architecture
4. Check the Architecture Invariants below — flag any drift before proceeding

### Architecture Invariants (non-negotiable)
- Every external service is accessed through a provider interface in `postmule/providers/*/`
- JSON files are the source of truth — Google Sheets is a generated view only, never written to directly
- Soft deletes only — nothing is permanently deleted automatically; max 0 auto-deletes ever
- All Drive writes use 3-layer redundancy: execute → MD5 verify → audit log
- No credentials or sensitive values ever committed to GitHub
- `config.yaml` is in `.gitignore`; `credentials.yaml` is not committed either
- Dry-run mode (`--dry-run`) must be respected by every agent and provider
- API safety agent limits must be checked before every LLM call
- Max 50 files moved per run (safety cap enforced in pipeline)

### File Editing Strategy — Token Efficiency
When editing existing files (especially large templates like `page.html`):
- **Read once, plan all edits** — do a single full read (or targeted Grep passes) to identify every change needed before making any edits.
- **Use `Grep -C 3` for edit anchors** — to get the `old_string` for an `Edit` call, use `Grep` with 2–3 lines of context rather than a large `Read`. This yields the same anchor in ~5 lines instead of 50.
- **Batch parallel Grep calls** — when multiple sections need inspection, run all Grep calls at once.
- **`Read` is for exploration; `Grep -C` is for edit anchors.** Once a file has been read once in the session, subsequent edits do not need another `Read`.
- **Use `replace_all` for repeated identical patterns** — avoids multiple round-trips for the same change.

### Before Starting Any New Feature
- Does this approach fit the overall system design?
- Does this duplicate something that already exists?
- Does this change interfaces other modules depend on?
- If adding a new provider: does it implement the base interface pattern?

---

## What PostMule Is
Open source, self-hosted replacement for PayTrust/PayMyBills. Processes physical mail (scanned by VPM) and email-delivered bills, uses AI to classify/extract data, manages bills, sends alerts, reconciles with bank transactions. Runs on Windows 11.

- **License:** MIT | **Repo:** https://github.com/PostMule/app | **Owner:** github.com/openclaw0123
- **Local path:** `C:\ClaudeCodeFiles\ClaudeCode\PostMule\`

---

## Tech Stack
| Concern | Choice |
|---|---|
| Language | Python 3.12+ |
| Scheduling | Windows Task Scheduler (daily 2am Pacific) |
| OCR | pdfplumber (text layer) → pytesseract (image fallback) |
| AI | Configurable LLM provider (default: Gemini 1.5 Flash, free tier) |
| Storage | JSON files (primary) + configurable spreadsheet view (default: Google Sheets) |
| Dashboard | Flask + HTMX + Alpine.js (localhost:5000) |
| Encryption | Fernet (credentials) + system keyring (master password) |
| Testing | pytest, 80%+ coverage, GitHub Actions CI |

---

## Architecture — Provider/Adapter Pattern
Every external service is abstracted behind an interface. Swap any provider with one config line.
Defaults: Gmail, Google Drive, Google Sheets, Gemini 1.5 Flash, VPM, YNAB.
Categories: mailbox, email (roles: `mailbox_notifications`, `bill_intake`), storage, llm, finance, notifications, spreadsheet.
Interfaces: `postmule/providers/*/base.py`. Concrete implementations alongside their base class.

---

## Daily Workflow (2am Pacific)
1a. `mailbox_notifications` email → VPM notification emails → download PDFs → upload to /Inbox
1b. `bill_intake` email → direct biller PDF attachments → download → upload to /Inbox (Phase 23)
2. Per PDF: OCR → LLM classify → rename → move to correct storage folder → update JSON/Sheets
3. Check storage provider consistency
4. Pull bank transactions from finance provider
5. Run bill matching → populate PendingBillMatches
6. Run entity discovery → propose alias matches
7. Send summary email; immediate alert if ForwardToMe; proactive bill-due alert if bills due within N days

---

## Cloud Storage (Google Drive)
Root folder configurable (`root_folder` in config). Default: `PostMule`.
```
PostMule/
├── _System/data/     ← JSON files, credentials.enc backup
├── Inbox/            ← unprocessed
├── Bills/ Notices/ ForwardToMe/ Personal/ Junk/ NeedsReview/
├── Duplicates/
└── Archive/
```

---

## Security & Credentials
- `credentials.yaml` → encrypted to `credentials.enc` (Fernet); master password in system keyring
- On startup: read keyring → download `credentials.enc` → decrypt in memory
- `credentials.example.yaml` committed (blank template); `config.example.yaml` committed (template)
- **NOTHING sensitive ever in GitHub**

---

## Web Dashboard
- Blueprints: `auth_bp` (login/logout), `pages_bp` (all pages), `connections_bp` (OAuth), `api_bp` (HTMX/JSON)
- Auth (rate limiting, lockout, session) in `web/routes/auth.py`
- Nav: Mail (`/`), Entities, Settings, Logs, Providers
- Mail page is a unified hub: status widget, filter tabs (All, Bills, Notices, Forward To Me, Unassigned), chronological item list. Entity match proposals surface inline per item and in the Unassigned tab.
- Redirect aliases: `/bills` → `/mail?tab=bills`, `/forward` → `/mail?tab=forward`, `/pending` → `/mail?tab=unassigned`, `/home` → `/`, `/connections` → `/providers` (301)
- `/corrections` → `/logs`; entity corrections surface as collapsible sub-section in Logs
- Providers page: full provider catalog with category tabs (Email, Storage, Spreadsheet, Physical Mail, AI/LLM, Finance, Notifications, Developer) and an "All providers / Configured only" toggle filter
- Templates: `postmule/web/templates/login.html` and `page.html`

---

## Brand & Design
Authoritative source: `postmule/web/templates/postmule_brand_03_final.html` — colors, typography, logo, component patterns.
Living mockup: `postmule/web/templates/mockup_dashboard.html` — must be kept in sync with the real app.

---

## File Naming Convention
`{date}_{recipients}_{sender}_{category}.pdf` — e.g., `2025-11-15_Alice_ATT_Bill.pdf`

---

## Bill Matching (non-obvious rules)
- Exact amount + exact date required; company name NOT used (finance providers overwrite it)
- ACH descriptor and statement date fields planned (issue #27)
- Manual approval on by default; when approved, updates finance provider transaction name

---

## Key Module Notes
- `postmule/core/constants.py` — category names, status values, shared constants
- `postmule/data/_io.py` — shared I/O utilities (`atomic_write`, `year_from`, `recent_years`); no domain logic here
- `postmule/data/entity_corrections.py` — `correction_summary()` used by Logs page collapsible section
- `postmule/web/templates/mockup_email_daily.html` — design reference for daily notification email
- `postmule/agents/backup.py` — public API: `run_backup`, `run_restore`, `list_backups`, `get_last_backup`
- `postmule/providers/finance/` — base protocol + YNAB, Plaid, Simplifi, Monarch implementations
- `postmule/pipeline.py` — daily run entry point: `run_daily_pipeline(cfg, credentials, data_dir, dry_run)`

---

## Dev Notes
- Python 3.12.10: `C:\Users\openclaw0123\AppData\Local\Programs\Python\Python312\`
- Venv: `C:\ClaudeCodeFiles\ClaudeCode\PostMule\.venv\`
- Run tests: `.venv\Scripts\pytest tests\unit\ -v`
- Key config sections: `app`, `schedule`, `logging`, `notifications`, `mailbox`, `email`, `storage`, `spreadsheet`, `llm`, `api_safety`, `classification`, `entities`, `finance`, `data_protection`, `backups`, `deployment`

---

## Build Status
Phases 1–23 complete (590 tests passing). Planned work tracked as GitHub issues:
`gh issue list --repo PostMule/app`
