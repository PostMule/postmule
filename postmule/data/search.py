"""Mail search — spans all JSON files across years."""

from __future__ import annotations

from pathlib import Path

from postmule.data import bills as bills_data
from postmule.data import forward_to_me as ftm_data
from postmule.data import notices as notices_data


def _all_bill_notice_years(data_dir: Path) -> list[int]:
    """Find all years for which bill or notice JSON files exist."""
    years: set[int] = set()
    for p in data_dir.glob("bills_*.json"):
        try:
            years.add(int(p.stem.split("_")[1]))
        except (IndexError, ValueError):
            pass
    for p in data_dir.glob("notices_*.json"):
        try:
            years.add(int(p.stem.split("_")[1]))
        except (IndexError, ValueError):
            pass
    return sorted(years, reverse=True)


def search_mail(
    data_dir: Path,
    *,
    types: list[str] | None = None,
    entity_id: str | None = None,
    owner_id: str | None = None,
    lifecycle: str = "all",
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    tag: str | None = None,
) -> list[dict]:
    """Search all mail across all years.

    Args:
        data_dir: Path to the JSON data directory.
        types: List of type strings to include (e.g. ['Bill', 'Notice']).
               None means all types.
        entity_id: Filter by entity_override_id.
        owner_id: Filter to items where owner_ids contains this UUID.
        lifecycle: 'open' (not filed), 'filed', or 'all'.
        q: Free-text search against sender, summary, and filename.
        date_from: Inclusive lower bound on date_received (YYYY-MM-DD).
        date_to: Inclusive upper bound on date_received (YYYY-MM-DD).
        tag: Filter to items that have this tag (case-insensitive).

    Returns:
        List of mail dicts with an added ``_type`` key, sorted by
        date_received descending.
    """
    if not data_dir:
        return []

    q_lower = q.lower().strip() if q else None
    tag_lower = tag.strip().lower() if tag else None
    results: list[dict] = []

    for year in _all_bill_notice_years(data_dir):
        for bill in bills_data.load_bills(data_dir, year):
            item = {"_type": bill.get("category_override", "Bill"), **bill}
            if _matches(item, types=types, entity_id=entity_id, owner_id=owner_id,
                        lifecycle=lifecycle, q_lower=q_lower,
                        date_from=date_from, date_to=date_to, tag_lower=tag_lower):
                results.append(item)
        for notice in notices_data.load_notices(data_dir, year):
            item = {"_type": notice.get("category_override", "Notice"), **notice}
            if _matches(item, types=types, entity_id=entity_id, owner_id=owner_id,
                        lifecycle=lifecycle, q_lower=q_lower,
                        date_from=date_from, date_to=date_to, tag_lower=tag_lower):
                results.append(item)

    for ftm in ftm_data.load_forward_to_me(data_dir):
        item = {"_type": ftm.get("category_override", "ForwardToMe"), **ftm}
        if _matches(item, types=types, entity_id=entity_id, owner_id=owner_id,
                    lifecycle=lifecycle, q_lower=q_lower,
                    date_from=date_from, date_to=date_to, tag_lower=tag_lower):
            results.append(item)

    results.sort(key=lambda x: x.get("date_received", ""), reverse=True)
    return results


def _matches(
    item: dict,
    *,
    types: list[str] | None,
    entity_id: str | None,
    owner_id: str | None,
    lifecycle: str,
    q_lower: str | None,
    date_from: str | None,
    date_to: str | None,
    tag_lower: str | None = None,
) -> bool:
    # lifecycle
    is_filed = bool(item.get("filed"))
    if lifecycle == "open" and is_filed:
        return False
    if lifecycle == "filed" and not is_filed:
        return False

    # type
    if types:
        if item.get("_type") not in types:
            return False

    # entity
    if entity_id:
        if item.get("entity_override_id") != entity_id:
            return False

    # owner
    if owner_id:
        if owner_id not in item.get("owner_ids", []):
            return False

    # date range
    dr = item.get("date_received", "")
    if date_from and dr and dr < date_from:
        return False
    if date_to and dr and dr > date_to:
        return False

    # tag
    if tag_lower:
        if tag_lower not in [t.lower() for t in item.get("tags", [])]:
            return False

    # free text
    if q_lower:
        searchable = " ".join([
            item.get("sender", ""),
            item.get("summary", ""),
            item.get("filename", ""),
        ]).lower()
        if q_lower not in searchable:
            return False

    return True
