"""
Entity discovery agent — extracts names from OCR text and proposes alias matches.

Uses fuzzy matching to identify when a name in a new mail item is likely
an alias for an already-known entity.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz, process  # type: ignore[import]

from postmule.data import entities as entity_data

log = logging.getLogger("postmule.agents.entity_discovery")

# Minimum similarity score (0-100) to propose an alias match
_DEFAULT_THRESHOLD = 85.0


def run_entity_discovery(
    names_from_mail: list[str],
    data_dir: Path,
    fuzzy_threshold: float = _DEFAULT_THRESHOLD,
    auto_approve_days: int = 7,
) -> dict[str, Any]:
    """
    Process names extracted from a mail item:
      - If name exactly matches a known entity/alias, return that entity.
      - If name is fuzzy-similar to a known entity, propose an alias match.
      - If name is new, log it for manual review (don't auto-add entities).

    Args:
        names_from_mail:  List of names extracted from mail OCR (recipients + sender).
        data_dir:         Path to local JSON data directory.
        fuzzy_threshold:  Minimum similarity (0-100) to propose a match.
        auto_approve_days: Days before auto-approving a proposed match.

    Returns:
        Dict with 'matched', 'proposed', 'new' lists.
    """
    known_names = entity_data.get_all_known_names(data_dir)
    entities = entity_data.load_entities(data_dir)

    result: dict[str, Any] = {"matched": [], "proposed": [], "new": []}

    # Process auto-approvals first
    auto_approved = entity_data.process_auto_approvals(data_dir)
    if auto_approved:
        log.info(f"Auto-approved {len(auto_approved)} entity alias matches")

    for name in names_from_mail:
        name = name.strip()
        if not name or len(name) < 2:
            continue

        # Exact match
        matched_entity = _find_exact_match(name, entities)
        if matched_entity:
            result["matched"].append({"name": name, "entity": matched_entity["canonical_name"]})
            continue

        # Fuzzy match
        if known_names:
            match_result = process.extractOne(
                name,
                known_names,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=fuzzy_threshold,
            )
            if match_result:
                matched_name, score, _ = match_result
                entity = _find_exact_match(matched_name, entities)
                if entity and not entity_data.is_denied(data_dir, name, entity["id"]):
                    entity_data.propose_alias_match(
                        data_dir,
                        proposed_name=name,
                        entity_id=entity["id"],
                        similarity=score / 100.0,
                        auto_approve_days=auto_approve_days,
                    )
                    result["proposed"].append({
                        "name": name,
                        "likely_entity": entity["canonical_name"],
                        "similarity": round(score / 100.0, 3),
                    })
                    log.info(
                        f"Proposed alias: '{name}' -> '{entity['canonical_name']}' "
                        f"(similarity={score:.1f}%)"
                    )
                    continue

        # Unknown name
        result["new"].append(name)
        log.debug(f"New unrecognised name in mail: '{name}'")

    return result


def _find_exact_match(name: str, entities: list[dict]) -> dict | None:
    name_lower = name.lower()
    for entity in entities:
        if entity["canonical_name"].lower() == name_lower:
            return entity
        for alias in entity.get("aliases", []):
            if alias.lower() == name_lower:
                return entity
    return None


def seed_known_entities(data_dir: Path, known_names: list[str]) -> None:
    """
    Seed the entity database from the known_names list in config.yaml.
    Each name is added as type 'Person'. Safe to call multiple times — skips existing entities.
    """
    existing = {e["canonical_name"].lower() for e in entity_data.load_entities(data_dir)}

    for name in known_names:
        if name.lower() not in existing:
            entity_data.add_entity(data_dir, name, "Person")
            log.info(f"Seeded entity: {name}")
