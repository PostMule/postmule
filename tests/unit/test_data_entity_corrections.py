"""Unit tests for postmule.data.entity_corrections."""

import json

import pytest

from postmule.data.entity_corrections import (
    correction_summary,
    load_corrections,
    log_correction,
)


class TestLoadCorrections:
    def test_returns_empty_when_no_file(self, tmp_path):
        assert load_corrections(tmp_path) == []

    def test_loads_existing_data(self, tmp_path):
        data = [{"id": "x", "original_sender": "ATTT"}]
        (tmp_path / "entity_corrections.json").write_text(json.dumps(data), encoding="utf-8")
        assert load_corrections(tmp_path) == data


class TestLogCorrection:
    def test_creates_file_on_first_call(self, tmp_path):
        log_correction(tmp_path, "mail-1", "Bill", "ATTT", "entity-1", "AT&T")
        assert (tmp_path / "entity_corrections.json").exists()

    def test_assigns_id(self, tmp_path):
        record = log_correction(tmp_path, "mail-1", "Bill", "ATTT", "entity-1", "AT&T")
        assert "id" in record
        assert len(record["id"]) > 8

    def test_fields_stored_correctly(self, tmp_path):
        record = log_correction(
            tmp_path, "mail-2", "Notice", "IRSS", "entity-2", "IRS", added_alias=True
        )
        assert record["mail_id"] == "mail-2"
        assert record["mail_type"] == "Notice"
        assert record["original_sender"] == "IRSS"
        assert record["corrected_entity_id"] == "entity-2"
        assert record["corrected_entity_name"] == "IRS"
        assert record["added_alias"] is True

    def test_correction_date_set(self, tmp_path):
        from datetime import date
        record = log_correction(tmp_path, "mail-3", "Bill", "X", "e-3", "Entity")
        assert record["correction_date"] == date.today().isoformat()

    def test_appends_multiple_corrections(self, tmp_path):
        log_correction(tmp_path, "mail-1", "Bill", "A", "e-1", "EntityA")
        log_correction(tmp_path, "mail-2", "Bill", "B", "e-2", "EntityB")
        assert len(load_corrections(tmp_path)) == 2

    def test_added_alias_defaults_false(self, tmp_path):
        record = log_correction(tmp_path, "mail-4", "Bill", "X", "e-4", "Entity")
        assert record["added_alias"] is False


class TestCorrectionSummary:
    def test_empty_when_no_corrections(self, tmp_path):
        assert correction_summary(tmp_path) == []

    def test_groups_by_original_sender(self, tmp_path):
        log_correction(tmp_path, "m1", "Bill", "ATTT", "e1", "AT&T")
        log_correction(tmp_path, "m2", "Bill", "ATTT", "e1", "AT&T")
        log_correction(tmp_path, "m3", "Bill", "IRSS", "e2", "IRS")
        summary = correction_summary(tmp_path)
        senders = {s["original_sender"]: s for s in summary}
        assert senders["ATTT"]["count"] == 2
        assert senders["IRSS"]["count"] == 1

    def test_sorted_by_count_descending(self, tmp_path):
        log_correction(tmp_path, "m1", "Bill", "ATTT", "e1", "AT&T")
        log_correction(tmp_path, "m2", "Bill", "ATTT", "e1", "AT&T")
        log_correction(tmp_path, "m3", "Bill", "IRSS", "e2", "IRS")
        summary = correction_summary(tmp_path)
        assert summary[0]["original_sender"] == "ATTT"

    def test_entity_names_deduplicated(self, tmp_path):
        log_correction(tmp_path, "m1", "Bill", "ATTT", "e1", "AT&T")
        log_correction(tmp_path, "m2", "Bill", "ATTT", "e1", "AT&T")
        summary = correction_summary(tmp_path)
        assert summary[0]["entity_names"] == ["AT&T"]

    def test_multiple_entity_targets_listed(self, tmp_path):
        log_correction(tmp_path, "m1", "Bill", "ATTT", "e1", "AT&T")
        log_correction(tmp_path, "m2", "Bill", "ATTT", "e2", "ATT Mobility")
        summary = correction_summary(tmp_path)
        assert len(summary[0]["entity_names"]) == 2
