"""Unit tests for postmule.data.search."""

import pytest

from postmule.data.bills import add_bill
from postmule.data.forward_to_me import add_item as add_forward_to_me
from postmule.data.notices import add_notice
from postmule.data.search import search_mail


def _bill(tmp_path, **kwargs):
    defaults = {"date_received": "2026-01-15", "sender": "ATT", "status": "pending"}
    return add_bill(tmp_path, {**defaults, **kwargs})


def _notice(tmp_path, **kwargs):
    defaults = {"date_received": "2026-01-20", "sender": "IRS"}
    return add_notice(tmp_path, {**defaults, **kwargs})


def _ftm(tmp_path, **kwargs):
    defaults = {"date_received": "2026-01-25", "sender": "USPS", "forwarding_status": "pending"}
    return add_forward_to_me(tmp_path, {**defaults, **kwargs})


# ── Basic retrieval ────────────────────────────────────────────────

def test_returns_all_types(tmp_path):
    _bill(tmp_path)
    _notice(tmp_path)
    _ftm(tmp_path)
    results = search_mail(tmp_path)
    types = {r["_type"] for r in results}
    assert "Bill" in types
    assert "Notice" in types
    assert "ForwardToMe" in types


def test_empty_data_dir(tmp_path):
    assert search_mail(tmp_path) == []


def test_none_data_dir():
    assert search_mail(None) == []


# ── Lifecycle filter ───────────────────────────────────────────────

def test_lifecycle_open_excludes_filed(tmp_path):
    _bill(tmp_path, filed=True)
    _bill(tmp_path, filed=False, sender="Verizon")
    results = search_mail(tmp_path, lifecycle="open")
    assert all(not r.get("filed") for r in results)
    assert len(results) == 1


def test_lifecycle_filed_only(tmp_path):
    _bill(tmp_path, filed=True, sender="Filed-Co")
    _bill(tmp_path, filed=False, sender="Open-Co")
    results = search_mail(tmp_path, lifecycle="filed")
    assert all(r.get("filed") for r in results)
    assert len(results) == 1


def test_lifecycle_all_includes_both(tmp_path):
    _bill(tmp_path, filed=True)
    _bill(tmp_path, filed=False)
    results = search_mail(tmp_path, lifecycle="all")
    assert len(results) == 2


# ── Type filter ────────────────────────────────────────────────────

def test_type_filter_bills_only(tmp_path):
    _bill(tmp_path)
    _notice(tmp_path)
    _ftm(tmp_path)
    results = search_mail(tmp_path, types=["Bill"])
    assert all(r["_type"] == "Bill" for r in results)
    assert len(results) == 1


def test_type_filter_multiple(tmp_path):
    _bill(tmp_path)
    _notice(tmp_path)
    _ftm(tmp_path)
    results = search_mail(tmp_path, types=["Bill", "Notice"])
    assert {r["_type"] for r in results} == {"Bill", "Notice"}


# ── Owner filter ───────────────────────────────────────────────────

def test_owner_filter(tmp_path):
    _bill(tmp_path, owner_ids=["owner-1"])
    _bill(tmp_path, owner_ids=["owner-2"], sender="Other")
    results = search_mail(tmp_path, owner_id="owner-1")
    assert len(results) == 1
    assert results[0]["sender"] == "ATT"


# ── Entity filter ──────────────────────────────────────────────────

def test_entity_filter(tmp_path):
    _bill(tmp_path, entity_override_id="ent-abc")
    _bill(tmp_path, sender="Verizon")
    results = search_mail(tmp_path, entity_id="ent-abc")
    assert len(results) == 1
    assert results[0]["entity_override_id"] == "ent-abc"


# ── Date range filter ──────────────────────────────────────────────

def test_date_from_filter(tmp_path):
    _bill(tmp_path, date_received="2026-01-10", sender="Early")
    _bill(tmp_path, date_received="2026-02-01", sender="Late")
    results = search_mail(tmp_path, date_from="2026-01-15")
    assert len(results) == 1
    assert results[0]["sender"] == "Late"


def test_date_to_filter(tmp_path):
    _bill(tmp_path, date_received="2026-01-10", sender="Early")
    _bill(tmp_path, date_received="2026-02-01", sender="Late")
    results = search_mail(tmp_path, date_to="2026-01-31")
    assert len(results) == 1
    assert results[0]["sender"] == "Early"


def test_date_range_filter(tmp_path):
    _bill(tmp_path, date_received="2026-01-05", sender="Before")
    _bill(tmp_path, date_received="2026-01-20", sender="InRange")
    _bill(tmp_path, date_received="2026-02-05", sender="After")
    results = search_mail(tmp_path, date_from="2026-01-10", date_to="2026-01-31")
    assert len(results) == 1
    assert results[0]["sender"] == "InRange"


# ── Free text filter ───────────────────────────────────────────────

def test_freetext_sender(tmp_path):
    _bill(tmp_path, sender="Comcast")
    _bill(tmp_path, sender="Verizon")
    results = search_mail(tmp_path, q="comcast")
    assert len(results) == 1
    assert results[0]["sender"] == "Comcast"


def test_freetext_summary(tmp_path):
    _bill(tmp_path, summary="Monthly internet service bill")
    _bill(tmp_path, summary="Gas and electric utility")
    results = search_mail(tmp_path, q="internet")
    assert len(results) == 1


def test_freetext_no_match(tmp_path):
    _bill(tmp_path, sender="ATT")
    results = search_mail(tmp_path, q="xyznonexistent")
    assert results == []


# ── Sort order ─────────────────────────────────────────────────────

def test_sorted_by_date_desc(tmp_path):
    _bill(tmp_path, date_received="2026-01-01", sender="First")
    _bill(tmp_path, date_received="2026-03-01", sender="Last")
    _bill(tmp_path, date_received="2026-02-01", sender="Middle")
    results = search_mail(tmp_path)
    dates = [r["date_received"] for r in results]
    assert dates == sorted(dates, reverse=True)


# ── Multi-year spanning ────────────────────────────────────────────

def test_spans_multiple_years(tmp_path):
    _bill(tmp_path, date_received="2025-06-01", sender="OldBill")
    _bill(tmp_path, date_received="2026-01-15", sender="NewBill")
    results = search_mail(tmp_path)
    senders = {r["sender"] for r in results}
    assert "OldBill" in senders
    assert "NewBill" in senders


def test_category_override_type(tmp_path):
    _bill(tmp_path, category_override="Personal")
    results = search_mail(tmp_path, types=["Personal"])
    assert len(results) == 1
    assert results[0]["_type"] == "Personal"
