"""Chemistry layer (docs/relationship-stage-spec.md §C3) — mandatory at
Relationship entry, freely editable at any time ("this is the one layer
that is freely editable, because chemistry genuinely evolves") — unlike
vision.py's additive-only model. Pure functions: the caller persists
ChemistryEntry rows.

Feeds Guru's Keep Romance Alive pillar and the Weekly Report's vibes
section (§D3/§D4). docs/intimacy-expectations-spec.md Part A later
extends this module with its own set of intimacy-expectation fields —
MANDATORY_KEYS below is deliberately not a closed enum enforced against
set_entry() (any key string is a valid ChemistryEntry, the same
open-ended design GuruTopic.topic_key already uses), so that extension
is additive, not a rebuild.
"""

from __future__ import annotations

from typing import Any

# §C3: "Captures: intimacy goals, vibes they want to keep alive,
# love-language style, communication preference, what makes them feel
# appreciated." — the set prerequisite_met() checks for. Not enforced as
# a whitelist in set_entry() itself.
MANDATORY_KEYS = (
    "intimacy_goals",
    "vibes_to_keep_alive",
    "love_language",
    "communication_preference",
    "appreciation_style",
)


def set_entry(user_id: str, key: str, value: str, updated_at: str) -> dict[str, Any]:
    """The ChemistryEntry row to persist for one key. Freely editable —
    the caller upserts by (user_id, key), overwriting any prior value,
    unlike vision.py's add-only/declare-only model."""
    return {"user_id": user_id, "key": key, "value": value, "updated_at": updated_at}


def prerequisite_met(entries_for_user: list[dict[str, Any]]) -> dict[str, Any]:
    """§C3's mandatory-at-Relationship-entry check — every MANDATORY_KEYS
    and INTIMACY_MANDATORY_KEYS key needs at least one non-blank entry
    (docs/intimacy-expectations-spec.md §A1 is itself headed "Mandatory
    at Relationship entry", so it joins C3's set rather than sitting
    beside it as optional). Returns {"met", "missing"}."""
    present = {e["key"] for e in entries_for_user if e.get("value")}
    missing = [k for k in (*MANDATORY_KEYS, *INTIMACY_MANDATORY_KEYS) if k not in present]
    return {"met": not missing, "missing": missing}


# ── Intimacy expectations (docs/intimacy-expectations-spec.md Part A) ────
# A1: "Mandatory at Relationship entry; editable at any time (chemistry
# genuinely evolves)." Same ChemistryEntry table/set_entry() as above —
# these are just further keys, not a new model.

INTIMACY_MANDATORY_KEYS = (
    "intimacy_pace",
    "intimacy_importance",
    "physical_boundary",
    "intimacy_notes",
    "health_openness",
)

INTIMACY_PACE_OPTIONS = ("open_to_physical_intimacy_early", "led_by_connection", "slow", "waiting_until_married")
HEALTH_OPENNESS_OPTIONS = ("yes", "when_relevant", "prefer_not_yet")
# "carried from Dating" — the same free-form greeting/physical-boundary
# vocabulary dateplan.py's partner selections already use (see
# guru_dating.pre_date_briefing's partner_greeting), reused verbatim
# rather than inventing a second taxonomy for the same concept.
PHYSICAL_BOUNDARY_OPTIONS = ("namaste", "bow", "handshake", "side-hug", "hug", "cheek-kiss")

# A2: "surfaced as soon as both have filled Chemistry" — the pace gap is
# material at this many steps apart in INTIMACY_PACE_OPTIONS's order
# (fastest-to-most-conservative). The spec leaves "MATERIAL" as an
# unspecified placeholder constant; 2 matches the same threshold
# stage_gate.py uses for its own readiness-scale divergence check, for
# consistency across the two gap-detection mechanisms in this project.
_MATERIAL_PACE_GAP = 2

MISMATCH_MESSAGE = (
    "You two have described different expectations about physical intimacy. "
    "That's common and workable — but worth talking about now rather than "
    "discovering it in the moment."
)


def intimacy_fields_complete(entries_for_user: list[dict[str, Any]]) -> bool:
    """Just the INTIMACY_MANDATORY_KEYS subset — used by
    on_chemistry_update() to know when a given partner's half of A1 is
    filled in, independent of whether the rest of C3's fields are done."""
    present = {e["key"] for e in entries_for_user if e.get("value")}
    return all(k in present for k in INTIMACY_MANDATORY_KEYS)


def on_chemistry_update(entries_a: list[dict[str, Any]], entries_b: list[dict[str, Any]]) -> dict[str, Any]:
    """§A2's on_chemistry_update(pair) pseudocode: surfaces a material
    pace mismatch to BOTH partners "as soon as both have filled
    Chemistry" — never before both sides' intimacy fields are complete,
    never blocking progression either way (the couple decides). Returns
    {"surfaced": bool, "message": str|None, "offer_next_level": bool}."""
    if not (intimacy_fields_complete(entries_a) and intimacy_fields_complete(entries_b)):
        return {"surfaced": False, "message": None, "offer_next_level": False}

    pace_a = next(e["value"] for e in entries_a if e["key"] == "intimacy_pace")
    pace_b = next(e["value"] for e in entries_b if e["key"] == "intimacy_pace")
    if pace_a == pace_b:
        return {"surfaced": False, "message": None, "offer_next_level": False}

    gap = abs(INTIMACY_PACE_OPTIONS.index(pace_a) - INTIMACY_PACE_OPTIONS.index(pace_b))
    if gap < _MATERIAL_PACE_GAP:
        return {"surfaced": False, "message": None, "offer_next_level": False}

    return {"surfaced": True, "message": MISMATCH_MESSAGE, "offer_next_level": True}
