"""
PostMule E2E fixture gate (PLAN section 14.18 / mvp-review.md section 2).

Runs the full daily pipeline against one committed fixture PDF with no live credentials and
no network. The pipeline itself is unmodified: real OCR (`agents/ocr.extract_text`), the real
`classify_pdf`, and the real `DriveProvider` over an in-memory transport double, so the
upload -> MD5-verify path in the architecture invariants genuinely executes.

Run: python scripts/e2e_fixture_run.py

------------------------------------------------------------------------------------------
WHAT THIS GATE MUST NEVER BECOME AGAIN (app #113)
------------------------------------------------------------------------------------------
The previous version could not fail. Its `FixtureLLMProvider.classify()` never read its
`ocr_text` argument -- it returned module constants -- and the gate then asserted the stored
bill equalled those same constants. OCR could return an empty string, or the whole document
could change, and the gate still passed. It also filed through `LocalStorageProvider`, so the
Drive integrity path was never exercised. It certified orchestration wiring and nothing else,
which is the opposite of what a release gate is for.

Two rules keep it honest, and both have negative controls in
`tests/integration/test_e2e_fixture_gate.py`:

  1. Every asserted value is DERIVED FROM THE DOCUMENT at run time and compared against
     `sample_bill.expected.json`, which was written by reading the PDF. The extractor and the
     expectations have no shared source, so agreement means the document was really read.
  2. `DocumentReadingLLM` parses the OCR text it is given. It has no canned answers. Break
     OCR and it returns nothing, the confidence collapses, and the gate fails.

If you find yourself adding a constant to make a check pass, the check is no longer testing
anything. Fix the pipeline or fix the expectations file instead.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from postmule.core.config import Config  # noqa: E402
from postmule.data import bills as bills_data  # noqa: E402
from postmule.pipeline import Providers, run_daily_pipeline  # noqa: E402
from postmule.providers import HealthResult  # noqa: E402
from postmule.providers.email.base import EmailMessage  # noqa: E402
from postmule.providers.llm.base import ClassificationResult  # noqa: E402
from postmule.providers.spreadsheet.none import NoneSpreadsheetProvider  # noqa: E402
from postmule.providers.storage.google_drive import DriveProvider  # noqa: E402
from scripts.fake_drive import FakeDriveService  # noqa: E402

FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "e2e"
FIXTURE_PDF = FIXTURE_DIR / "sample_bill.pdf"
FIXTURE_EXPECTED = FIXTURE_DIR / "sample_bill.expected.json"


def load_expected() -> dict:
    """The independently-authored record of what the fixture document says."""
    return json.loads(FIXTURE_EXPECTED.read_text(encoding="utf-8"))


class FixtureEmailProvider:
    """In-memory email provider that returns the fixture email exactly once."""

    def __init__(self, pdf_path: Path) -> None:
        self._pdf_bytes = pdf_path.read_bytes()
        self._served = False

    def list_unprocessed_emails(
        self, sender_filter: str, subject_filter: str
    ) -> list[EmailMessage]:
        if self._served:
            return []
        self._served = True
        return [
            EmailMessage(
                message_id="e2e-fixture-msg-1",
                subject="[Scan Request] Fixture scan",
                received_date="2026-06-14",
                sender="noreply@virtualpostmail.com",
                attachments=[{"name": "sample_bill.pdf", "data": self._pdf_bytes}],
            )
        ]

    def list_emails_with_pdf_attachments(self) -> list[EmailMessage]:
        return []

    def mark_as_processed(self, message_id: str) -> None:
        pass

    def health_check(self) -> HealthResult:
        return HealthResult(ok=True, status="ok", message="fixture email provider")


class DocumentReadingLLM:
    """A deterministic local classifier that EXTRACTS FROM the OCR text it is handed.

    Standing in for Gemini without a network call is legitimate; standing in for *reading the
    document* is not. This double therefore has no canned answers at all: every field is
    parsed out of `ocr_text` at call time. Hand it an empty string -- which is exactly what a
    broken OCR path produces -- and it finds nothing, reports zero confidence, and the gate
    fails on the checks below.

    The regexes are deliberately literal about the fixture's layout. They are not a general
    bill parser and are not used in production; their only job is to make "did the pipeline
    actually read this document?" a question the gate can answer.
    """

    def __init__(self) -> None:
        self.seen_ocr_text: list[str] = []

    def classify(self, ocr_text: str, known_names=None, dry_run: bool = False):
        self.seen_ocr_text.append(ocr_text or "")
        text = ocr_text or ""

        sender = _first(r"^\s*([A-Za-z][A-Za-z .,&'-]+)\s*$", text)
        recipient = _first(r"Bill To:\s*(.+)", text)
        account = _first(r"Account Number:\s*([0-9-]+)", text)
        due_date = _first(r"Due Date:\s*(\d{4}-\d{2}-\d{2})", text)
        amount_raw = _first(r"Amount Due:\s*\$?\s*([0-9,]+\.\d{2})", text)
        amount = float(amount_raw.replace(",", "")) if amount_raw else None

        # Confidence reflects how much of the document was actually legible. It is computed,
        # never asserted as a constant, so a partial OCR failure degrades it honestly and the
        # pipeline's own confidence threshold routes the item to NeedsReview.
        found = [sender, recipient, account, due_date, amount]
        confidence = sum(1 for f in found if f not in (None, "")) / len(found)

        return ClassificationResult(
            category="Bill" if amount is not None and due_date else "NeedsReview",
            confidence=confidence,
            sender=sender or "",
            recipients=[recipient] if recipient else [],
            amount_due=amount,
            due_date=due_date,
            account_number=account or "",
            summary=f"Parsed from {len(text)} characters of OCR text",
            tokens_used=0,
        )

    def health_check(self) -> HealthResult:
        return HealthResult(ok=True, status="ok", message="document-reading fixture LLM")


def _first(pattern: str, text: str) -> str | None:
    found = re.search(pattern, text, re.MULTILINE)
    return found.group(1).strip() if found else None


def _build_fixture_config(tmp_path: Path) -> Config:
    data = {
        "app": {"dry_run": False},
        "notifications": {"alert_email": "e2e@example.invalid"},
        "llm": {
            "providers": [{"service": "gemini", "enabled": True}],
            "classification_confidence_threshold": 0.80,
        },
        "email": {
            "providers": [{"service": "gmail", "enabled": True, "id": "e2e"}],
        },
        "storage": {
            "providers": [
                {
                    "service": "google_drive",
                    "enabled": True,
                    "folders": {
                        "inbox": "Inbox",
                        "bills": "Bills",
                        "notices": "Notices",
                        "forward_to_me": "ForwardToMe",
                        "personal": "Personal",
                        "junk": "Junk",
                        "needs_review": "NeedsReview",
                        "duplicates": "Duplicates",
                        "archive": "Archive",
                        "system": "_System",
                    },
                }
            ]
        },
        "spreadsheet": {"providers": [{"service": "none", "enabled": True}]},
        "data_protection": {"max_files_moved_per_run": 50},
        "deployment": {"dashboard_port": 5000},
    }
    return Config(data, tmp_path / "config.yaml")


def _build_fixture_providers(cfg: Config, drive_service: FakeDriveService):
    """The real DriveProvider, wired to the transport double instead of the network."""
    storage_cfg = cfg.get("storage", "providers")[0]
    drive = DriveProvider(credentials=None, root_folder="PostMule")
    drive._service = drive_service  # inject the transport; provider logic stays untouched
    folder_ids = drive.ensure_folder_structure(storage_cfg["folders"])
    llm = DocumentReadingLLM()
    providers = Providers(
        drive=drive,
        sheets=NoneSpreadsheetProvider(),
        llm=llm,
        safety_agent=None,
        folder_ids=folder_ids,
        mailbox_notification_providers=[FixtureEmailProvider(FIXTURE_PDF)],
    )
    return providers, llm


@dataclass
class GateResult:
    passed: bool
    details: list[str] = field(default_factory=list)


def run_gate(tmp_path: Path, drive_service: FakeDriveService | None = None) -> GateResult:
    """Run the full pipeline against the fixture and check the v0.1.0 success scenario.

    `drive_service` is injectable so the negative-control tests can hand in a Drive that
    corrupts a checksum and confirm this gate goes red.
    """
    expected = load_expected()
    cfg = _build_fixture_config(tmp_path)
    drive_service = drive_service or FakeDriveService()
    providers, llm = _build_fixture_providers(cfg, drive_service)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    credentials = {
        "smtp": {"host": "127.0.0.1", "port": 1, "username": "", "password": ""}  # nosec B105
    }

    with patch("postmule.pipeline._build_providers", return_value=providers):
        stats = run_daily_pipeline(cfg, credentials, data_dir, dry_run=False)

    checks: list[tuple[str, bool]] = [
        ("pipeline status is not failed", stats["status"] != "failed"),
        ("one fixture email was fetched", stats["emails_found"] == 1),
        ("one PDF was OCR'd and classified", stats["pdfs_processed"] == 1),
    ]

    # --- 1. OCR really read the document ------------------------------------------------
    # The text the classifier was handed must contain the document's own landmarks. An empty
    # or garbled OCR result fails here, before anything downstream can paper over it.
    ocr_text = llm.seen_ocr_text[0] if llm.seen_ocr_text else ""
    checks.append(("the classifier was handed non-empty OCR text", bool(ocr_text.strip())))
    for marker in expected["document_markers"]:
        checks.append((f"OCR text contains the document marker {marker!r}", marker in ocr_text))

    # --- 2. The extraction came FROM the document ---------------------------------------
    # Compared against sample_bill.expected.json, which was authored by reading the PDF, not
    # by recording pipeline output. This is the check the old gate faked.
    bills = bills_data.load_bills(data_dir)
    checks.append(("classified bill was recorded in JSON", len(bills) == 1))
    if bills:
        bill = bills[0]
        for field_name in ("sender", "amount_due", "due_date", "account_number"):
            checks.append((
                f"recorded {field_name} matches what the document says "
                f"({expected[field_name]!r})",
                bill.get(field_name) == expected[field_name],
            ))
        checks.append((
            "recorded bill is pending (visible in dashboard)",
            bill.get("status") == "pending",
        ))

    # --- 3. The real Drive integrity path ran -------------------------------------------
    checks.append((
        "Drive upload was MD5-verified against the bytes actually stored",
        len(drive_service.verified_md5_reads) >= 1,
    ))
    checks.append((
        "no hard delete was attempted (soft-delete-only invariant)",
        drive_service.hard_delete_attempts == [],
    ))

    # --- 4. The document was filed where a bill belongs ---------------------------------
    bills_folder = providers.folder_ids["bills"]
    inbox_folder = providers.folder_ids["inbox"]
    filed = drive_service.files_in(bills_folder)
    checks.append(("fixture PDF was filed into the Bills folder", len(filed) == 1))
    checks.append(("Inbox is empty after filing", len(drive_service.files_in(inbox_folder)) == 0))
    if filed and bills:
        checks.append((
            "filed PDF was renamed to the suggested filename",
            filed[0]["name"] == bills[0].get("filename"),
        ))
        # The bytes in Drive are still the bytes that were sent: a move/rename must not
        # disturb content, and this is the only check that would notice if one did.
        checks.append((
            "filed PDF's bytes are unchanged end to end",
            drive_service.stored_bytes(filed[0]["id"]) == FIXTURE_PDF.read_bytes(),
        ))

    details = [f"{'PASS' if ok else 'FAIL'}: {label}" for label, ok in checks]
    return GateResult(passed=all(ok for _, ok in checks), details=details)


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_dir = REPO_ROOT / "validation"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"e2e-fixture-{ts}.log"

    with tempfile.TemporaryDirectory() as tmp:
        result = run_gate(Path(tmp))

    lines = [f"PostMule E2E fixture gate -- {ts}", ""]
    lines.extend(result.details)
    lines.append("")
    lines.append("E2E_PASS" if result.passed else "E2E_FAIL")
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {log_path}")
    print(lines[-1])
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
