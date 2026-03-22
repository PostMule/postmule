# Contributing to PostMule

## Development Setup

```powershell
git clone https://github.com/PostMule/app.git
cd postmule
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
playwright install chromium
```

Copy the example configs — you do not need real credentials to run the test suite:

```powershell
copy config.example.yaml config.yaml
copy credentials.example.yaml credentials.yaml
```

## Running Tests

```powershell
# Full unit test suite with coverage
pytest tests/unit/ -v

# Single file
pytest tests/unit/test_gmail.py -v

# Coverage report
pytest tests/unit/ --cov=postmule --cov-report=term-missing
```

The test suite uses mocks for all external services (Google Drive, Gmail, Gemini, etc.) — no
real accounts or API keys are needed.

Coverage target: 80%+. Do not submit a PR that drops coverage below that threshold.

## Code Style

```powershell
# Format
black postmule/ tests/

# Lint
ruff check postmule/ tests/
```

Both are enforced in CI. Line length is 100 characters (configured in `pyproject.toml`).

## Architecture — Read Before Adding Code

PostMule uses a **provider/adapter pattern**. Every external service is accessed through an
interface in `postmule/providers/*/base.py`. Before adding code that touches an external
service, check whether a provider interface already exists.

### Non-negotiable invariants

- **JSON files are the source of truth.** Google Sheets is a generated view — never write
  to it directly as a data store.
- **Soft deletes only.** Nothing is permanently deleted automatically. Move to Trash/Duplicates.
- **Dry-run must be respected.** Every agent and provider must check `dry_run` before
  writing anything. Pass it through; do not skip it.
- **API safety limits must be checked before every LLM call.** Use `api_safety.check()`.
- **Credentials never in source code or config.yaml.** All secrets go in `credentials.yaml`
  (encrypted to `credentials.enc`).

### Adding a new provider

1. Check `postmule/providers/*/base.py` for the relevant Protocol.
2. Create your implementation in the same package (e.g. `postmule/providers/storage/s3.py`).
3. Implement all methods defined in the Protocol — do not add provider-specific public methods
   that callers would depend on.
4. Add a `type:` key for your provider in `config.example.yaml`.
5. Add credentials fields (if any) to `credentials.example.yaml`.
6. Wire it into the factory/loader that instantiates providers from config.
7. Add unit tests with mocked external calls.

### Adding a new agent or pipeline step

- Agents live in `postmule/agents/`.
- Each agent takes `cfg`, `credentials`, and `dry_run` — do not reach into global state.
- Agents should be independently runnable via `postmule --agent <name>`.
- Log at `INFO` for normal events, `WARNING` for recoverable issues, `ERROR` for failures
  that stop processing.

## Pull Requests

- Keep PRs focused — one feature or fix per PR.
- Include or update tests for any changed behavior.
- Update `CLAUDE.md` build phase status if you complete a planned phase.
- PR titles should be short and descriptive (under 70 characters).
- All CI checks must pass before merge.

## Reporting Issues

Open an issue at https://github.com/PostMule/app/issues. Include:

- What you were doing
- What you expected to happen
- What actually happened
- Relevant lines from your verbose log (`postmule logs`)
- Your OS and Python version

Do not include credentials, personal email addresses, or real mail content in issues.

## Security

Do not open a public issue for security vulnerabilities. Contact the maintainer directly
via GitHub before disclosing.
