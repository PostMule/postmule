# PostMule — Daily Workflow

The daily pipeline runs automatically on a configurable schedule (default: 2:00 AM local time, set via `config.yaml` → `schedule.run_time`). Here is everything that happens in one run.

## Pipeline Flowchart

```mermaid
flowchart TD
    START([Pipeline starts]) --> INGEST

    subgraph INGEST["Step 1 — Mail Ingestion"]
        direction TB
        A1["Check mailbox notification email\nfor VPM scan alerts"] --> A2["Download PDFs from VPM"]
        A3["Check bill intake email\nfor biller PDF attachments"] --> A4["Download PDF attachments"]
        A2 --> UPLOAD["Upload all PDFs to /Inbox\nin cloud storage"]
        A4 --> UPLOAD
    end

    UPLOAD --> PER_PDF

    subgraph PER_PDF["Step 2 — Per-PDF Processing"]
        direction TB
        B1["OCR extraction\npdfplumber → pytesseract fallback"] --> B2
        B2["LLM classification\nBill / Notice / ForwardToMe / Personal / Junk"] --> B3
        B3{"Confidence\n≥ threshold?"}
        B3 -->|yes| B4["Rename file\n{date}_{recipients}_{sender}_{category}.pdf"]
        B3 -->|no| NEEDS["Move to /NeedsReview"]
        B4 --> B5["Move to correct folder\n/Bills, /Notices, /ForwardToMe, etc."]
        B5 --> B6["Update JSON data files\nbills.json / notices.json / etc."]
        B6 --> B7["Sync Sheets view\nfrom JSON"]
    end

    B7 --> CONSISTENCY

    subgraph CONSISTENCY["Step 3 — Storage Consistency Check"]
        C1["Verify storage folder\ncontents match JSON records"]
    end

    CONSISTENCY --> FINANCE

    subgraph FINANCE["Step 4 — Finance Sync"]
        D1["Pull bank transactions\nfrom finance provider (YNAB / Plaid)"]
    end

    FINANCE --> MATCHING

    subgraph MATCHING["Step 5 — Bill Matching"]
        E1["Match bills to bank transactions\nby exact amount + statement date"]
        E2["Populate PendingBillMatches\nfor human approval in dashboard"]
        E1 --> E2
    end

    MATCHING --> ENTITY

    subgraph ENTITY["Step 6 — Entity Discovery"]
        F1["Scan new mail for unknown sender names"]
        F2["Fuzzy-match against known entities"]
        F3["Propose alias matches\nfor human review in dashboard"]
        F1 --> F2 --> F3
    end

    ENTITY --> NOTIFY

    subgraph NOTIFY["Step 7 — Notifications"]
        G1["Send daily summary email\nwith counts + highlights"]
        G2{"ForwardToMe\nitems?"}
        G3["Send immediate urgent alert\nfor each ForwardToMe item"]
        G4{"Bills due\nwithin N days?"}
        G5["Send proactive\nbill-due alert"]
        G1 --> G2
        G2 -->|yes| G3
        G2 -->|no| G4
        G3 --> G4
        G4 -->|yes| G5
    end

    G4 -->|no| DONE([Run complete])
    G5 --> DONE
```

## Step Details

### Step 1 — Mail Ingestion
Two parallel ingestion paths feed the same downstream pipeline:

1. **Physical mail (VPM path):** PostMule monitors a Gmail inbox for scan notification emails from your virtual mailbox provider. When found, it downloads the PDF scans and uploads them to `/Inbox` in cloud storage.
2. **Email bill intake:** A separate inbox monitors for biller-sent PDF attachments (e.g. AT&T, utilities emailing your bill directly). PDFs are downloaded and uploaded to the same `/Inbox`.

### Step 2 — Per-PDF Processing
For each PDF in `/Inbox`:

1. **OCR** — `pdfplumber` extracts the text layer first (fast, accurate for digital PDFs). If no usable text is found, `pytesseract` OCRs the rendered image.
2. **LLM classification** — The extracted text is sent to the configured LLM with a structured prompt. The LLM returns: category, sender name, recipients, amount (for bills), due date (for bills), and a summary.
3. **Confidence gate** — If classification confidence is below `classification_confidence_threshold` (default 0.80), the file goes to `/NeedsReview` instead of being classified.
4. **Rename & move** — The file is renamed to `{date}_{recipients}_{sender}_{category}.pdf` and moved to the correct folder.
5. **JSON update** — The relevant JSON data file (`bills.json`, `notices.json`, etc.) is updated with the extracted fields.
6. **Sheets sync** — The corresponding Google Sheet tab is regenerated from the JSON.

### Step 3 — Storage Consistency Check
PostMule verifies that files in cloud storage folders match the records in JSON. Discrepancies are flagged in the run log.

### Step 4 — Finance Sync
Pulls recent bank transactions from the configured finance provider (YNAB, Plaid, etc.) and writes them to `bank_transactions.json`.

### Step 5 — Bill Matching
Attempts to match each unmatched bill to a bank transaction using:
- **Exact dollar amount** (configurable tolerance, default 0 cents)
- **Statement date** (exact match)

Note: Company name is deliberately excluded — finance providers normalize transaction names in ways that don't match biller names.

Matches are written to `pending/bill_matches.json` and shown in the dashboard for manual approval. When approved, PostMule updates the finance provider transaction name.

### Step 6 — Entity Discovery
Scans new mail items for sender names not yet in the entity database. Runs fuzzy string matching against all known entity names and aliases. Matches above `fuzzy_match_threshold` (default 0.85) are added to `pending/entity_matches.json` for review in the dashboard.

### Step 7 — Notifications
- **Daily summary email** — always sent; summarizes mail counts, new bills, matched transactions, and pending items.
- **Urgent ForwardToMe alert** — sent immediately if any physical mail was classified as ForwardToMe (configurable: `forward_to_me_urgent`).
- **Bill due alert** — sent if any bill is due within `bill_due_alert_days` (default 7).

## File Naming Convention

```
{date}_{recipients}_{sender}_{category}.pdf

Examples:
  2025-11-15_Alice_ATT_Bill.pdf
  2025-12-01_Alice-Bob_IRS_Notice.pdf
  2026-01-03_Alice_Verizon_Bill.pdf
```
