"""Vision layer at Relationship entry (docs/relationship-stage-spec.md
Part C) — the additive-only model (C1), the Stats/Chemistry prerequisite
gate checked at Gate step 5 (B2), and the Specific-tier playbook unlock
table (D5). Pure functions: the caller persists whatever's returned.

Guardrail (Part F): "Vision is additive-only. No delete operation
exists. Reversals require an explicit, partner-disclosed declaration."
Enforced structurally: this module defines add_vision_detail() (free)
and declare_vision_change() (gated on disclosure) — nothing else that
touches a VisionEntry's content. See test_vision.py's own AST-based
assertion that no function name here starts with "delete" or "remove".
"""

from __future__ import annotations

from typing import Any

import chemistry

# §C2: the mandatory-at-Relationship-entry Stats fields, mapped onto the
# keys generate_users.py's stats_json actually produces (profession/
# marital_history/languages/city added there on 2026-08-28 specifically
# so this list is fully satisfiable — "location" -> city, the field this
# project already tracks for that purpose).
MANDATORY_STATS_FIELDS = (
    "age",
    "height_cm",
    "profession",
    "income_band",
    "education",
    "diet",
    "marital_history",
    "city",
    "languages",
)

# Canonical Vision element keys this module's Specific-tier unlock table
# recognizes (§D5). add_vision_detail() itself doesn't enforce this list —
# element_key stays open-ended like GuruTopic.topic_key elsewhere in this
# project — but only entries using one of these feed unlocked_specific_topics().
VISION_ELEMENT_KEYS = ("children", "cohabitation", "relocation", "career", "intimacy", "travel")


def add_vision_detail(
    user_id: str, element_key: str, detail_text: str, added_at: str, parent_id: str | None = None
) -> dict[str, Any]:
    """C1: "ADD granular detail beneath an existing Vision element" —
    always allowed, never gated. `parent_id` chains a new detail beneath
    a prior VisionEntry.id for the same element_key (None for the first
    entry under a key), so a user's full detail history for that element
    reads as a chain, not a flat unordered pile."""
    return {
        "user_id": user_id,
        "element_key": element_key,
        "detail_text": detail_text,
        "added_at": added_at,
        "parent_id": parent_id,
    }


def declare_vision_change(
    user_id: str,
    element_key: str,
    from_value: str,
    to_value: str,
    declared_at: str,
    disclosed_to_partner: bool,
    guru_conversation_id: str | None = None,
) -> dict[str, Any]:
    """C1's material reversal path — the only way an existing Vision
    element can effectively change instead of just accumulate detail.
    Raises if `disclosed_to_partner` is falsy: an undisclosed reversal
    defeats the entire point of the guardrail, so this function refuses
    to even build the row rather than accept disclosed_to_partner=False.
    `guru_conversation_id` identifies the Guru conversation this routes
    to — created by the caller; this module has no Guru dependency."""
    if not disclosed_to_partner:
        raise ValueError("a Vision change must be disclosed to the partner — it cannot be declared silently")
    return {
        "user_id": user_id,
        "element_key": element_key,
        "from_value": from_value,
        "to_value": to_value,
        "declared_at": declared_at,
        "disclosed_to_partner": True,
        "guru_conversation_id": guru_conversation_id,
    }


def vision_history(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """"Full version history is retained and visible to both" (C1) — a
    trivial passthrough, kept as a named function so it's the one
    obvious place documenting that nothing is ever filtered or hidden
    here (no delete, no partner-specific redaction)."""
    return list(entries)


def stats_prerequisite_met(stats: dict[str, Any]) -> dict[str, Any]:
    """§C2's mandatory-at-entry check — every MANDATORY_STATS_FIELDS key
    must be present with a non-blank value. Returns {"met", "missing"}."""
    missing = [f for f in MANDATORY_STATS_FIELDS if not stats.get(f)]
    return {"met": not missing, "missing": missing}


def prerequisites_met(
    vision_entries_for_user: list[dict[str, Any]],
    stats: dict[str, Any],
    chemistry_entries_for_user: list[dict[str, Any]],
) -> dict[str, Any]:
    """B2 step 5, all three prerequisites in one call. Vision's own
    bar (C1's table: "Full detail required; granularity expected") has
    no fixed field checklist the way Stats/Chemistry do, so it's checked
    as "has the user actually added at least one VisionEntry" rather
    than against a specific set of keys."""
    vision_met = len(vision_entries_for_user) > 0
    stats_result = stats_prerequisite_met(stats)
    chemistry_result = chemistry.prerequisite_met(chemistry_entries_for_user)
    return {
        "met": vision_met and stats_result["met"] and chemistry_result["met"],
        "vision_met": vision_met,
        "stats_missing": stats_result["missing"],
        "chemistry_missing": chemistry_result["missing"],
    }


# ── Relationship playbook — Specific tier unlocks (§D5) ─────────────────

# Which VisionEntry.element_key unlocks which Specific-tier playbook
# topic — "only the ones their Vision selections unlock." A key may
# unlock more than one topic (cohabitation implies both shared space and
# shared expenses); a topic may be reachable from more than one key
# (career and relocation both feed the same combined topic, since D5
# names them as one item: "career & relocation").
SPECIFIC_TIER_UNLOCKS: dict[str, list[str]] = {
    "children": ["children"],
    "cohabitation": ["household_and_shared_space", "shared_expenses"],
    "relocation": ["career_and_relocation"],
    "career": ["career_and_relocation"],
}

# Fixed display order (§D5's own listing order), independent of the order
# a user happened to add Vision entries in — two couples' playbooks read
# the same way regardless of which topic they unlocked first.
_SPECIFIC_TIER_ORDER = ["household_and_shared_space", "shared_expenses", "children", "career_and_relocation"]


def unlocked_specific_topics(vision_entries_for_user: list[dict[str, Any]]) -> list[str]:
    """The subset of D5's four Specific-tier topics this user's own
    Vision entries actually unlock, deduplicated, in §D5's fixed order."""
    unlocked: set[str] = set()
    for entry in vision_entries_for_user:
        unlocked.update(SPECIFIC_TIER_UNLOCKS.get(entry["element_key"], []))
    return [topic for topic in _SPECIFIC_TIER_ORDER if topic in unlocked]
