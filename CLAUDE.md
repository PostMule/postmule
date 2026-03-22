# PostMule — Claude Code Project Context

## How To Resume In A New Session
Tell Claude Code:
> "I'm working on PostMule. Please read CLAUDE.md at the project root
>  (C:\ClaudeCodeFiles\ClaudeCode\PostMule\CLAUDE.md) and continue from where we left off."

The build phases below track current progress. Read this file, check git log for recent
commits, and pick up the next incomplete phase.

---

## Review Protocol — Required Every Session

Before writing any code, Claude must:

1. Re-read this entire CLAUDE.md file
2. Run `git log --oneline -15` to see recent commits
3. State in one sentence what is about to be built and how it fits the architecture
4. Check the Architecture Invariants below — flag any drift before proceeding
5. If anything looks inconsistent or misaligned, stop and raise it before coding

### Architecture Invariants (non-negotiable)
- Every external service is accessed through a provider interface in `postmule/providers/*/`
- JSON files are the source of truth — Google Sheets is a generated view only, never written to directly
- Soft deletes only — nothing is permanently deleted automatically
- All Drive writes use 3-layer redundancy: execute → MD5 verify → audit log
- No credentials or sensitive values ever committed to GitHub
- `config.yaml` is in `.gitignore` (contains user email and local paths); `credentials.yaml` is not committed either
- Dry-run mode (`--dry-run`) must be respected by every agent and provider
- API safety agent limits must be checked before every Gemini call
- Max 50 files moved per run (safety cap enforced in pipeline)

### Before Starting Any New Feature or Phase
- Zoom out: does this approach still fit the overall system design?
- Check: does this duplicate something that already exists?
- Check: does this change any interfaces that other modules depend on?
- If adding a new provider: does it implement the base interface pattern?

---

## What PostMule Is
An open source, self-hosted replacement for PayTrust/PayMyBills. Receives physical mail
scanned to PDF by a virtual mailbox service AND email-delivered bills (Phase 23), uses AI
to classify and extract data, manages bills, sends alerts, and reconciles with bank
transactions. Runs on Windows 11.

- **License:** MIT
- **Repo:** https://github.com/PostMule/app
- **Local path:** C:\ClaudeCodeFiles\ClaudeCode\PostMule\
- **Owner GitHub:** github.com/openclaw0123
- **Domain:** postmule.com (not yet registered as of 2026-03-21)

---

## Brand & Design System
Reference file: `postmule/web/templates/postmule_brand_03_final.html`

### Colors
| Name | Hex | Usage |
|---|---|---|
| Navy Seal | `#0F2044` | Header, nav, CTA buttons, card titles |
| Brass | `#E8A020` | Accent, badges, bill indicator, logo detail |
| Steel Blue | `#7A9CC4` | Logo body, secondary text, subheadings |
| Linen | `#F5F6F8` | Page background |
| Smoke | `#DDE3EC` | Card borders, dividers, read/neutral state |
| Red | `#C62828` | Overdue / urgent |
| Green | `#2E7D32` | Delivered / OK |

### Typography
- Page titles: 20px, weight 600, `#0F2044`, tracking -0.3px
- Card titles (unread): 13px, weight 600, `#0F2044`
- Card titles (read): 13px, weight 400, `#8A9BB0`
- Body: 13px, `#5A7090`
- Badges/labels: 10px, weight 600, letter-spacing 1px

### Logo
SVG mule mark — ears (tall navy rectangles with brass stripe), eyes (navy circles with
brass highlight), muzzle bar (steel blue), nostrils (navy circles).
Wordmark: "Post" white + "Mule" brass (`#E8A020`), weight 600.
Tagline: "Smart mail management" — `#5A7CA4`, 11px, letter-spacing 2px, uppercase.

### Component Patterns
- **Cards:** white bg, 8px radius, 1px `#DDE3EC` border, 3px colored left bar
- **Left bar colors:** Brass = bill, Red = overdue/urgent, Smoke = read/neutral, Blue = notice
- **Page bg:** `#F5F6F8` (Linen)
- **Header/nav:** `#0F2044` (Navy Seal)
- **Toast/alert:** Navy bg, brass dot, white text

### Brand Personality
Authoritative · Trustworthy · Financial-grade · Precise
"The app your accountant would actually recommend."
Brand voice: short, declarative. "Bill arrived. $94 due Apr 5." "16 days remaining."

---

## Tech Stack
| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| Scheduling | Windows Task Scheduler (daily 2am Pacific) |
| OCR | pdfplumber (text layer) → pytesseract (image fallback) |
| AI | Configurable LLM provider (default: Gemini 1.5 Flash, free tier 1500 req/day) |
| Storage | JSON files (primary) + configurable spreadsheet view (default: Google Sheets) |
| Files | Configurable storage provider (default: Google Drive) |
| Email | Configurable email provider (default: Gmail API / OAuth2) |
| Dashboard | Flask + vanilla JS (fetch API) + custom inline CSS (localhost:5000) |
| Finance sync | YNAB API (recommended), Plaid API, Monarch (Playwright scraping, experimental) |
| Encryption | Fernet (credentials) + system keyring (master password) |
| Testing | pytest, 80%+ coverage, GitHub Actions CI |
| CLI | `postmule` command (click-based) |

---

## Architecture — Provider/Adapter Pattern
Every external service is abstracted behind an interface. Swap providers with one config line.
Multiple providers per module supported simultaneously with priority ordering.

### Provider Categories
- **Physical mailbox:** VPM (VirtualPostMail.com, default), Earth Class Mail, Traveling Mailbox, PostScan, Anytime Mailbox, US Global Mail
- **Email:** Gmail, Outlook.com, Proton Mail, Yahoo, iCloud, Fastmail, Zoho, Tuta, HEY, IMAP generic
  - Each email provider entry has a `role` field: `mailbox_notifications` (receives VPM scan
    notification emails) or `bill_intake` (dedicated inbox for biller-sent PDF attachments)
  - Multiple providers per role are supported; pipeline runs each role independently
- **Storage:** Google Drive, Dropbox, OneDrive, Box, iCloud Drive, S3, B2, MEGA, pCloud, WebDAV
- **LLM:** Gemini, OpenAI, Anthropic, Ollama, Azure OpenAI, Mistral, Cohere
- **Finance:** Simplifi (Playwright), YNAB (real API), Monarch, Tiller, Empower, Copilot
- **Notifications:** Email, SMS/Twilio, Pushover, Slack, Teams, Webhook, Multi
- **Spreadsheet:** Google Sheets, Excel Online, Airtable, Notion, None

Provider interfaces live in `postmule/providers/*/base.py`.
Concrete implementations live alongside their base class.

---

## Daily Workflow (2am Pacific, ~2–5 min normally)
1a. `mailbox_notifications` email provider → scan notification emails from VPM → download PDFs → upload to storage /Inbox
1b. `bill_intake` email provider (Phase 23) → direct biller PDF attachments → download → upload to storage /Inbox
2. Per PDF in Inbox: OCR → LLM classify → rename → move to correct storage folder → update JSON/Sheets
3. Check all storage providers for consistency (multi-provider)
4. Pull bank transactions from finance provider
5. Run bill matching → populate PendingBillMatches
6. Run entity discovery → propose alias matches
7. Build and send summary email (immediate alert if ForwardToMe items found)
   → Proactive bill due alert if any unpaid bills due within N days (`bill_due_alert_days`)

---

## Mail Categories
| Category | Description |
|---|---|
| Bill | Invoice or payment demand → log to bills DB, alert if due soon |
| Notice | Statements, EOBs, tax docs → log and file |
| ForwardToMe | Physical items of value (credit cards, checks, gift cards, tickets, anything unusual) → URGENT alert, contact VPM to ship |
| Personal | Greeting cards, personal letters |
| Junk | Marketing |
| NeedsReview | Low confidence (<0.80) → human review in dashboard |

---

## Cloud Storage (Google Drive)
Google Drive is the intentional storage backend — not just a convenience. It provides:
- **Data resilience:** PDFs and JSON data survive local PC failure or loss
- **Reinstall recovery:** Reinstall PostMule on any machine and immediately pick up where you left off — no data loss, no re-import

The root folder name is configurable (`root_folder` in config). Default: `PostMule`.

```
PostMule/
├── _System/data/          ← JSON files, credentials.enc backup
├── Inbox/                 ← unprocessed
├── Bills/
├── Notices/
├── ForwardToMe/
├── Personal/
├── Junk/
├── NeedsReview/
├── Duplicates/
└── Archive/               ← pre-system files
```

---

## Data Storage (JSON Primary)
Files stored in Google Drive `_System/data/`:
- `bills_YYYY.json`, `notices_YYYY.json` (one per year)
- `forward_to_me.json`, `entities.json`, `sender_directory.json`
- `run_log.json`, `hashes.json`
- `pending/entity_matches.json`, `pending/bill_matches.json`

Google Sheets is a **generated view only** — never the source of truth.
Sheets: Bills, Notices, ForwardToMe, Entities, SenderDirectory, BankTransactions,
PendingEntityMatches, PendingBillMatches, RunLog, APIUsage

---

## Security & Credentials
- `credentials.yaml` → encrypted to `credentials.enc` (Fernet, master password)
- `credentials.enc` stored in Google Drive `_System/` as backup
- Master password stored in the system keyring (Windows: DPAPI, macOS: Keychain, Linux: Secret Service) for unattended restarts
- On startup: read master password from system keyring → download credentials.enc → decrypt in memory
- `config.yaml` is in `.gitignore` — contains user email and local paths, do not commit
- `credentials.example.yaml` committed (template, all values blank)
- **NOTHING sensitive ever in GitHub**

---

## Data Protection
- Soft deletes ONLY — nothing permanently deleted automatically
- Trash folder, 90-day retention (configurable)
- 3-layer write redundancy: execute → verify (read back + hash) → audit log
- 6 months of daily encrypted backups (configurable)
- Max 50 files moved per run (safety cap), 0 auto-deletes ever
- Dry run mode: `postmule --dry-run`

---

## Integrity Agents (4)
1. **Run Monitor** — verifies each run completed, alerts if missed
2. **Gap Detector** (weekly) — finds date gaps in processing, re-queues missed emails
3. **Integrity Verifier** (weekly) — Drive file count matches Sheets row count
4. **Duplicate Detector** (daily) — SHA-256 hash comparison, moves dupes to /Duplicates

---

## API Safety Agent
- Hard limits: configurable per provider (defaults: 1400 req/day, 900K tokens/day — buffer below Gemini free tier)
- Monthly cost budget: $0.00 (free tier default), configurable
- Warning at 80% of any limit
- Stops processing if limit hit, alerts user
- Tracks and reports estimated cost in daily summary

---

## Logging
- **Verbose:** rolling N days (configurable, default 7), one file per day
- **Processing:** annual files (YYYY.log), one line per run, kept N years (configurable)
- **Human-readable errors:** plain English title + what happened + what to do + technical
  details in verbose log only

---

## Web Dashboard (v1)
- Flask + vanilla JS (fetch API) + custom inline CSS
- localhost:5000 (optional Tailscale for anywhere access)
- Setup wizard IS the web UI (first run opens browser to /setup)
- Pages: Home, Mail, Bills, ForwardToMe, Pending, Entities, Settings, Logs, Setup
- Templates: `postmule/web/templates/login.html` and `page.html` (base layout with injected content)

---

## Setup Flow (Minimal User Input)
1. Select providers (or accept defaults: Gmail, Google Drive/Sheets, Gemini, VPM)
2. Authenticate chosen providers (e.g. Google OAuth for Gmail/Drive defaults)
   → Auto-creates required resources for default providers (Drive folders, Sheets workbook, Gmail label/filter)
3. Enter personal alert email address
4. Enter credentials for chosen virtual mailbox provider

Done. ~10–15 minutes total.
Pre-registered project OAuth client → users never touch Google Cloud Console.

---

## Installer / CLI
```
install.ps1 [--install-dir path] [--config-url url] [--credentials-url url]
postmule --help | --run | --run --agent email | --status | --update-credentials
    --update-config | --retroactive | --verify | --logs | --dry-run | --uninstall
```
Install location: `C:\ProgramData\PostMule\`

---

## File Naming Convention
`{date}_{recipients}_{sender}_{category}.pdf`
Example: `2025-11-15_Alice_ATT_Bill.pdf`

---

## Entity System
- Auto-discovers names from mail OCR
- Fuzzy matching proposes aliases (configurable threshold, default 0.85)
- PendingEntityMatches — auto-approves after N days (default 7) unless denied
- Denied matches remembered permanently
- Entity types: Person, LLC, Trust, Corporation, Partnership, Other
- Multi-recipient: tagged as "Alice, Bob" not just one name

---

## Bill Matching
- Exact amount match + exact date match required
- Company name NOT used for matching (Simplifi overwrites with wrong names)
- ACH descriptor field (Phase 21) stored per bill — more reliable than merchant name for electronic payments
- Statement date (Phase 21) stored separately from `date_received` and `due_date` — needed for tax records and billing cycle matching
- Manual approval mode (default: true) — configurable
- When approved: updates finance provider transaction name to correct company name
- Finance providers: **YNAB** (real API, recommended default), **Plaid** (real API, development tier), **Simplifi** (Playwright scraping, experimental), **Monarch** (Playwright scraping, experimental)
- Simplifi labeled experimental — Playwright scraping is fragile; YNAB is preferred

---

## Retroactive Processing
- Flag: `retroactive_processing: true` in config
- Processes all existing PDFs in all folders
- Uses previous folder name as classification hint if Gemini uncertain
- Renames files, moves to correct Drive folders, populates all Sheets
- Rate limited to stay within Gemini free tier (15s delay between calls)

---

## Simplifi Reference
- finance-dl (MIT) used as architectural reference for web scraping patterns
- Credited in ATTRIBUTION.md and inline code comments

---

## Build Order & Status

| Phase | Description | Status |
|---|---|---|
| 1 | Repo + MIT license + folder structure | ✅ Done |
| 2 | Config system + credential encryption | ✅ Done |
| 3 | Logging system | ✅ Done |
| 4 | CLI entry point | ✅ Done |
| 5 | Installer + uninstaller + Task Scheduler | ✅ Done |
| 6 | Gmail ingestion agent | ✅ Done |
| 7 | OCR pipeline | ✅ Done |
| 8 | LLM abstraction layer + Gemini | ✅ Done |
| 9 | API safety agent | ✅ Done |
| 10 | Classification agent | ✅ Done |
| 11 | Google Drive storage | ✅ Done |
| 12 | JSON data layer + Google Sheets export | ✅ Done |
| 13 | Entity discovery system | ✅ Done |
| 14 | Daily summary + email alerts | ✅ Done |
| 15 | Integrity agents (4) | ✅ Done |
| 16 | Retroactive processing | ✅ Done |
| 17 | Simplifi sync agent | ✅ Done |
| 18 | Unit + integration tests | ✅ Done (481 tests passing) |
| 19 | Web dashboard (Flask) | ✅ Done |
| 20 | Documentation | ✅ Done (CLAUDE.md, README, CONTRIBUTING.md, config/credentials examples) |
| 21 | Statement date + ACH descriptor fields | Planned (small — schema + extraction) |
| 22 | Finance providers (YNAB, Plaid, Monarch) | ✅ Done (base.py shared types, factory in pipeline, full test coverage) |
| 23 | Online bill email intake (bill_intake role) | Planned (large — second intake pipeline) |
| 24 | SQLite storage layer | Planned (deferred — after core validated in production) |

### Priority Gaps (fix before first real-world run)
- **CLI rename:** ~~`vpm`~~ renamed to `postmule` (was colliding with VirtualPostMail brand) ✓
- **Dashboard auth:** Single configurable password, rate limiting, 15-min lockout, 8-hour session timeout — fully implemented in `web/app.py` ✓
- **Notification deduplication:** `alert_sent_date` field implemented in bill schema; `send_bill_due_alert` skips already-alerted bills ✓
- **End-to-end validation:** Run actual pipeline against real Gmail/VPM/Gemini/Drive before
  further feature work

## Key Module Notes

- `postmule/core/constants.py` — shared string constants (category names, status values, etc.)
- `postmule/data/_io.py` — shared I/O utilities (`atomic_write`, `year_from`, `recent_years`) imported by all data modules; do not add domain-specific logic here
- `postmule/web/templates/` — Flask HTML templates (`login.html`, `page.html`); embedded HTML strings were removed from `web/app.py`
- `postmule/providers/finance/` — base protocol + YNAB, Plaid, Simplifi, Monarch implementations

## Pipeline Orchestrator
`postmule/pipeline.py` — ties all agents together for the daily run.
Entry point: `run_daily_pipeline(cfg, credentials, data_dir, dry_run)`

## Python Notes
- Python 3.12.10 installed at: C:\Users\openclaw0123\AppData\Local\Programs\Python\Python312\
- Virtual env: C:\ClaudeCodeFiles\ClaudeCode\PostMule\.venv\
- Run tests: `.venv\Scripts\pytest tests\unit\ -v`

---

## Config Files
- `config.yaml` — all non-sensitive settings; in `.gitignore` (contains your email and local paths)
- `config.example.yaml` — committed to GitHub (template)
- `credentials.yaml` — sensitive values, NOT committed (in .gitignore)
- `credentials.example.yaml` — committed (blank template)
- `credentials.enc` — encrypted credentials, safe to commit/backup

## Key Sections in config.yaml
`app`, `schedule`, `logging`, `notifications`, `mailbox`, `email`, `storage`,
`spreadsheet`, `llm`, `api_safety`, `classification`, `ocr`, `file_naming`, `entities`,
`finance`, `data_protection`, `backups`, `integrity`, `credentials`, `deployment`
