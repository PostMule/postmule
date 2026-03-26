"""Tests for postmule.data.feedback — local feedback log."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from postmule.data.feedback import append_feedback, list_feedback


def test_append_creates_file(tmp_path):
    entry = append_feedback(tmp_path, {"type": "general", "title": "Test", "description": "desc"})
    assert (tmp_path / "feedback.json").exists()
    assert entry["id"]
    assert entry["timestamp"]
    assert entry["title"] == "Test"


def test_append_multiple(tmp_path):
    append_feedback(tmp_path, {"type": "bug", "title": "Bug 1", "description": "d1"})
    append_feedback(tmp_path, {"type": "feature", "title": "Feature 1", "description": "d2"})
    records = json.loads((tmp_path / "feedback.json").read_text())
    assert len(records) == 2
    assert records[0]["title"] == "Bug 1"
    assert records[1]["title"] == "Feature 1"


def test_none_fields_excluded(tmp_path):
    entry = append_feedback(tmp_path, {"type": "general", "title": "T", "description": "D", "steps": None, "page": None})
    assert "steps" not in entry
    assert "page" not in entry


def test_list_feedback_empty(tmp_path):
    assert list_feedback(tmp_path) == []


def test_list_feedback_newest_first(tmp_path):
    append_feedback(tmp_path, {"type": "general", "title": "First", "description": "d1"})
    append_feedback(tmp_path, {"type": "bug", "title": "Second", "description": "d2"})
    records = list_feedback(tmp_path)
    assert records[0]["title"] == "Second"
    assert records[1]["title"] == "First"


def test_ids_are_unique(tmp_path):
    e1 = append_feedback(tmp_path, {"type": "general", "title": "A", "description": "d"})
    e2 = append_feedback(tmp_path, {"type": "general", "title": "B", "description": "d"})
    assert e1["id"] != e2["id"]


def test_append_returns_entry_with_all_fields(tmp_path):
    entry = append_feedback(tmp_path, {
        "type": "bug",
        "title": "Crash on load",
        "description": "App crashes",
        "steps": "1. Open app",
        "page": "mail",
        "version": "0.1.0",
    })
    assert entry["type"] == "bug"
    assert entry["steps"] == "1. Open app"
    assert entry["page"] == "mail"
    assert entry["version"] == "0.1.0"
