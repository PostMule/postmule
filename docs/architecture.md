# PostMule — System Architecture

PostMule is built around a **provider/adapter pattern**: every external service is abstracted behind an interface, so you can swap any component with a single line in `config.yaml`.

```mermaid
graph TB
    subgraph Physical["Physical Mail"]
        VPM["Virtual Mailbox\n(VPM / Earth Class / etc.)"]
    end

    subgraph Email["Email Layer"]
        NOTIF["Mailbox Notification\nEmail (Gmail, IMAP)"]
        INTAKE["Bill Intake Email\n(direct biller PDFs)"]
    end

    subgraph Pipeline["Daily Pipeline (2am Pacific)"]
        direction TB
        OCR["OCR\n(pdfplumber → pytesseract)"]
        LLM["LLM Classify\n(Gemini / OpenAI / Ollama)"]
        RENAME["Rename & Route\n{date}_{recipient}_{sender}_{category}.pdf"]
        ENTITY["Entity Discovery\nAlias matching & enrichment"]
        MATCH["Bill Matching\nAmount + date reconciliation"]
    end

    subgraph Storage["Storage Layer"]
        DRIVE["Cloud Storage\n(Google Drive / S3 / Dropbox)"]
        JSON["JSON Files\n(source of truth)"]
        SHEETS["Spreadsheet View\n(Google Sheets — generated)"]
    end

    subgraph Finance["Finance Provider"]
        BANK["Bank Transactions\n(YNAB / Plaid / Simplifi)"]
    end

    subgraph Output["Output"]
        DASH["Web Dashboard\nlocalhost:5000"]
        ALERT["Alert Email\n(daily summary + urgent)"]
    end

    VPM -->|scan notification| NOTIF
    NOTIF -->|download PDF| OCR
    INTAKE -->|PDF attachment| OCR
    OCR --> LLM
    LLM --> RENAME
    RENAME -->|move to folder| DRIVE
    DRIVE --> JSON
    JSON --> SHEETS
    JSON --> ENTITY
    JSON --> MATCH
    BANK -->|pull transactions| MATCH
    JSON --> DASH
    MATCH --> DASH
    ENTITY --> DASH
    MATCH --> ALERT
    ENTITY --> ALERT
```

## Components

| Component | Default | Purpose |
|---|---|---|
| Virtual Mailbox | VirtualPostMail | Scans physical mail; sends notification email |
| Email (notifications) | Gmail | Receives VPM scan emails; triggers PDF download |
| Email (bill intake) | Gmail | Receives biller PDF attachments directly |
| OCR | pdfplumber + pytesseract | Extracts text from PDFs; auto-selects best method |
| LLM | Gemini 1.5 Flash | Classifies documents, extracts structured fields |
| Storage | Google Drive | Stores PDFs and JSON data files (cloud-redundant) |
| Spreadsheet | Google Sheets | Generated view layer; rebuilt from JSON on demand |
| Finance | YNAB | Pulls bank transactions for bill reconciliation |
| Web Dashboard | Flask + HTMX + Alpine.js | Local browser UI (localhost:5000) |
| Notifications | Email | Daily summary + urgent alerts |

## Data Flow Principles

- **JSON files are the source of truth.** Sheets, the dashboard, and all exports are derived views.
- **Soft deletes only.** No file is permanently deleted automatically.
- **3-layer write redundancy.** Every Drive write: execute → MD5 verify → audit log.
- **Provider interfaces.** All external services implement a base protocol in `postmule/providers/*/base.py`. Swap any provider with one config line.
- **Dry-run everywhere.** The `--dry-run` flag is respected by every agent and every provider — no writes, moves, or sends occur in dry-run mode.
- **API safety gate.** LLM API usage limits (configured under `api_safety` in `config.yaml`) are checked before every LLM call. Calls are blocked if limits would be exceeded.
- **50-file cap per run.** No more than 50 files are moved out of Inbox in a single pipeline run, regardless of how many are present.

## Key File Paths

```
PostMule/                          ← Cloud storage root (configurable)
├── _System/data/                  ← JSON files, encrypted credential backup
│   ├── entities.json
│   ├── bills.json
│   ├── notices.json
│   ├── forward_to_me.json
│   └── pending/
│       ├── entity_matches.json
│       └── bill_matches.json
├── Inbox/                         ← Unprocessed incoming PDFs
├── Bills/                         ← Classified bills
├── Notices/
├── ForwardToMe/
├── Personal/
├── Junk/
├── NeedsReview/
├── Duplicates/
└── Archive/
```
