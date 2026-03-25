# PostMule

> The open source, self-hosted replacement for PayTrust / PayMyBills.

PostMule receives your physical mail as PDFs from a virtual mailbox service, uses AI to
classify and extract data, manages your bills, sends alerts for important items, and
reconciles transactions with your bank — all running on your own machine.

## Features

- **AI-powered classification** — Bills, Notices, ForwardToMe, Personal, Junk
- **Urgent alerts** — Detects credit cards, checks, and other physical items that need forwarding
- **Bill management** — Due date tracking, amount extraction, bank transaction matching
- **Entity discovery** — Automatically learns names and aliases from your mail
- **Modular providers** — Swap virtual mailbox, email, storage, LLM, and finance providers with one config line
- **Zero lock-in** — All data stored as plain JSON files; Google Sheets is a generated view
- **Privacy-first** — Runs locally; credentials encrypted with Fernet, master password in system keyring
- **Web dashboard** — Local browser UI (localhost:5000) for reviewing mail, managing bills, editing entities, and configuring all connections; optional Tailscale for remote access
- **Retroactive processing** — Process your full mail history in one command

## Status

Early development — core pipeline complete, not yet validated against a live mailbox.
See [build phases](CLAUDE.md#build-order--status) for detailed progress.

## Requirements

- Python 3.12+
- Windows 11 (primary target; macOS/Linux may work with minor adjustments)
- A supported virtual mailbox service (VirtualPostMail, Earth Class Mail, etc.)
- A supported email provider for notifications (default: Gmail)
- A supported cloud storage provider (default: Google Drive + Sheets)
- An API key for a supported LLM provider (default: Gemini free tier — 1,500 req/day)

All providers are configurable via a single line in `config.yaml`. Defaults are chosen for
cost (free tiers) and ease of setup.

## Quick Start

```powershell
# Clone and install
git clone https://github.com/PostMule/app.git
cd postmule
python -m venv .venv
.venv\Scripts\activate
pip install -e .

# Copy and edit config files
copy config.example.yaml config.yaml
copy credentials.example.yaml credentials.yaml
# Edit config.yaml — set alert_email and your virtual mailbox provider
# Edit credentials.yaml — fill in your Google OAuth and Gemini API key

# Store master password in your system keyring
postmule set-master-password

# Encrypt credentials
postmule encrypt-credentials

# Test with a dry run
postmule --dry-run
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.

## Supported Providers

| Category | Default | Alternatives |
|---|---|---|
| Virtual mailbox | VirtualPostMail | Earth Class Mail, Traveling Mailbox, PostScan |
| Email | Gmail | Outlook.com, Proton Mail, any IMAP |
| Storage | Google Drive | Dropbox, OneDrive, S3 |
| Spreadsheet | Google Sheets | Excel Online, Airtable |
| LLM | Gemini 1.5 Flash | OpenAI, Anthropic, Ollama |
| Finance | — | YNAB, Plaid, Simplifi (experimental), Monarch (experimental) |

## License

MIT — see [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Attribution

See [ATTRIBUTION.md](ATTRIBUTION.md).
