"""
Integration tests for the E2E fixture gate (PLAN section 14.18).

The gate itself checks the v0.1.0 success scenario: one fixture email fetched, OCR'd,
classified, filed into the correct folder, and recorded in JSON.

These tests check something the gate cannot check about itself -- that it is capable of
FAILING. That is the whole substance of app #113: the previous gate asserted a hardcoded
constant against the same hardcoded constant, so it passed no matter what the pipeline did.
A green gate is only evidence if a broken pipeline turns it red, so every negative control
below breaks one real thing and asserts the gate notices.

If you ever have to delete one of these to make the suite pass, the gate has regressed into
a tautology again -- fix the gate, not the test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.e2e_fixture_run import load_expected, run_gate  # noqa: E402
from scripts.fake_drive import FakeDriveService  # noqa: E402


def _failed_checks(result) -> list[str]:
    return [d for d in result.details if d.startswith("FAIL")]


# --- the gate passes on a healthy pipeline -----------------------------------------


def test_e2e_fixture_gate_passes(tmp_path):
    result = run_gate(tmp_path)
    assert result.passed, "\n".join(result.details)


def test_the_gate_actually_checks_a_meaningful_number_of_things(tmp_path):
    """Guards against a future 'fix' that makes the gate green by checking less."""
    result = run_gate(tmp_path)
    assert len(result.details) >= 15, "\n".join(result.details)


# --- negative control: OCR ---------------------------------------------------------


def test_gate_fails_when_ocr_returns_nothing(tmp_path, monkeypatch):
    """The headline #113 failure. The old gate passed with OCR completely broken, because
    the fixture classifier never looked at the OCR text it was given."""
    monkeypatch.setattr("postmule.agents.classification.extract_text", lambda _p: "")

    result = run_gate(tmp_path)

    assert not result.passed, "a gate that survives total OCR failure is testing nothing"
    assert any("OCR text" in f for f in _failed_checks(result)), result.details


def test_gate_fails_when_ocr_returns_a_different_document(tmp_path, monkeypatch):
    """OCR that silently reads the wrong thing is worse than OCR that returns nothing --
    it produces a confident, wrong bill. The gate must catch that too."""
    monkeypatch.setattr(
        "postmule.agents.classification.extract_text",
        lambda _p: (
            "Globex Water\nAccount Number: 1112223333\n"
            "Bill To: Bob Other\nAmount Due: $999.99\nDue Date: 2030-01-01\n"
        ),
    )

    result = run_gate(tmp_path)

    assert not result.passed
    failures = _failed_checks(result)
    assert any("amount_due" in f for f in failures), failures


def test_gate_fails_when_ocr_reads_only_part_of_the_document(tmp_path, monkeypatch):
    """A partial read must not slip through on the strength of the fields that survived."""
    monkeypatch.setattr(
        "postmule.agents.classification.extract_text",
        lambda _p: "Acme Utilities\nStatement Date: 2026-06-01\n",
    )

    result = run_gate(tmp_path)

    assert not result.passed


# --- negative control: Drive file integrity ----------------------------------------


def test_gate_fails_when_drive_reports_a_mismatched_checksum(tmp_path):
    """Exercises the real DriveProvider._verify_upload against a Drive that hands back a
    checksum for different bytes. The old gate filed through LocalStorageProvider and never
    ran this path at all."""
    drive = FakeDriveService()
    drive.corrupt_all_md5 = True

    result = run_gate(tmp_path, drive_service=drive)

    assert not result.passed, "the MD5-verify path did not reject a corrupt upload"


def test_the_integrity_path_is_genuinely_exercised(tmp_path):
    """A checksum read must actually happen -- a gate that never calls the verify path
    cannot fail on it, however good its assertions look."""
    drive = FakeDriveService()

    run_gate(tmp_path, drive_service=drive)

    assert drive.verified_md5_reads, "no md5Checksum read-back occurred during the run"


def test_no_hard_delete_is_ever_attempted(tmp_path):
    """The soft-delete-only invariant (max 0 auto-deletes ever), asserted against the
    transport rather than trusted."""
    drive = FakeDriveService()

    run_gate(tmp_path, drive_service=drive)

    assert drive.hard_delete_attempts == []


# --- negative control: the expectations file ---------------------------------------


def test_gate_fails_when_the_document_disagrees_with_the_expectations(tmp_path, monkeypatch):
    """The two sides must be independent. If the expectations file could not disagree with
    the extraction, it would be decoration rather than a check."""
    expected = load_expected()
    expected["amount_due"] = 1234.56
    monkeypatch.setattr("scripts.e2e_fixture_run.load_expected", lambda: expected)

    result = run_gate(tmp_path)

    assert not result.passed
    assert any("amount_due" in f for f in _failed_checks(result))


def test_expectations_file_covers_every_asserted_field(tmp_path):
    """A missing key would raise rather than silently skip a check, but state it explicitly."""
    expected = load_expected()
    for key in ("sender", "amount_due", "due_date", "account_number", "document_markers"):
        assert key in expected, f"expectations file is missing {key!r}"


# --- the classifier double must read, not recite -----------------------------------


def test_the_fixture_classifier_consumes_the_ocr_text_it_is_given():
    """The precise defect from #113, pinned directly: `classify()` must derive its answer
    from `ocr_text`, so that identical calls with different documents differ."""
    from scripts.e2e_fixture_run import DocumentReadingLLM

    llm = DocumentReadingLLM()
    real = llm.classify(
        "Acme Utilities\nBill To: Alice Example\nAccount Number: 9988776655\n"
        "Amount Due: $84.50\nDue Date: 2026-07-15\n"
    )
    empty = llm.classify("")

    assert real.amount_due == 84.50
    assert real.due_date == "2026-07-15"
    assert empty.amount_due is None, "the classifier returned a value it was never shown"
    assert empty.confidence == 0.0
    assert empty.category != "Bill"


@pytest.mark.parametrize("amount,expected", [("$12.00", 12.0), ("$1,234.56", 1234.56)])
def test_the_fixture_classifier_reads_the_amount_it_is_actually_shown(amount, expected):
    from scripts.e2e_fixture_run import DocumentReadingLLM

    result = DocumentReadingLLM().classify(f"Acme Utilities\nAmount Due: {amount}\n")

    assert result.amount_due == expected
