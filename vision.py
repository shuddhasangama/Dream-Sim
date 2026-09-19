"""Vision layer at Relationship entry (docs/relationship-stage-spec.md
Part C) — the additive-only model (C1), the Stats/Chemistry prerequisite
gate checked at Gate step 5 (B2), and the Specific-tier playbook unlock
table (D5). Pure functions: the caller persists whatever's returned.

round3-fixes-spec.md §7 rewrote the structure itself: exactly four
pillars (Intimacy mandatory; Travel together, Kids, Cohabitate optional,
Relocation and Career gone entirely), each with its own strict rules —
see PILLAR_OPTIONS/validate_pillars() below. "Add Detail" (§7.2) and
"Declare a Change" (§7.3) used to be free-text notes attached to an
open-ended element_key that never touched the real vision_json state at
all — genuinely decorative, not additive. They now operate on the SAME
structured pillars/sub-selections vision_json itself holds, and actually
write it.

Guardrail (Part F): "Vision is additive-only. No delete operation
exists. Reversals require an explicit, partner-disclosed declaration."
Still enforced structurally: add_detail() only ever adds; declare_change()
is the one function that can remove a sub-selection, gated on disclosure
AND on rc_open() (§7.3: "Only editable while RC is open"). See
test_vision.py's own AST-based assertion that no function name here
starts with "delete" or "remove".
"""

from __future__ import annotations

from typing import Any

import chemistry
import clock as clock_module
from generate_users import COHABIT_FOCUS, INTIMACY_KINDS, KIDS_ROUTES, OTHER_VISION_KEYS

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

# round3-fixes-spec.md §7.1's exact four pillars and their sub-selections
# — the same vocabulary onboarding.py's signup flow uses (INTIMACY_KINDS/
# OTHER_VISION_KEYS/COHABIT_FOCUS/KIDS_ROUTES, all imported from
# generate_users.py, never redefined here), so a pillar name typed at
# Relationship entry can never drift from the one chosen at sign-up.
# Travel together maps to an empty tuple — no sub-selection exists.
PILLAR_OPTIONS: dict[str, tuple[str, ...]] = {
    "Intimacy": tuple(INTIMACY_KINDS),
    **{key: (tuple(COHABIT_FOCUS) if key == "Cohabitate" else tuple(KIDS_ROUTES) if key == "Kids" else ())
       for key in OTHER_VISION_KEYS},
}

# Every pillar this module recognizes, Intimacy first (build_visions()'s
# own convention) then OTHER_VISION_KEYS' order — the display order for
# anything that lists all four together.
VISION_ELEMENT_KEYS = ("Intimacy", *OTHER_VISION_KEYS)

# Sub-selections that carry a prerequisite of their own — mirrors
# onboarding.NEEDS_PHYSICAL exactly (same 2026-09-09 rule: Surrogacy and
# Adoption do not require Physical intimacy; only Naturally does).
NEEDS_PHYSICAL = {"Naturally"}

VISION_DETAIL_EXPLANATION = (
    "Travel together takes no detail now. Kids and Cohabitate do, because picking "
    "either without saying what you mean says almost nothing — and they are "
    "revisited together, at the Relationship stage, once it is a decision rather "
    "than a preference."
)


def _as_pillars(vision_json: list[dict[str, Any]]) -> dict[str, list[str]]:
    """[{"key":.., "stance":[..]|str|None}, ...] -> {"Intimacy": [...], ...}
    — vision_json's own on-disk shape, normalized so every value here is
    a plain list, present only for a pillar that is actually selected."""
    out: dict[str, list[str]] = {}
    for entry in vision_json or []:
        stance = entry.get("stance")
        if stance is None:
            stance = []
        elif isinstance(stance, str):
            stance = [stance]
        out[entry["key"]] = list(stance)
    return out


def _as_vision_json(pillars: dict[str, list[str]]) -> list[dict[str, Any]]:
    """The inverse of _as_pillars(), in VISION_ELEMENT_KEYS' fixed order
    — a rebuilt vision_json never reorders itself depending on which
    pillar was touched last. An empty sub-selection list becomes None,
    matching onboarding.build_visions()'s own convention (Travel
    together, or — only ever transiently, mid-validation — an emptied
    Intimacy)."""
    return [{"key": key, "stance": sorted(pillars[key]) if pillars[key] else None}
            for key in VISION_ELEMENT_KEYS if key in pillars]


def validate_pillars(pillars: dict[str, list[str]]) -> dict[str, Any]:
    """round3-fixes-spec.md §7.1's five rules, checked against a FULL
    resulting vision state — used by both add_detail() and
    declare_change() so a mutation is only ever accepted if what it
    leaves behind is itself a valid Vision, never just a valid delta.
    """
    intimacy = pillars.get("Intimacy") or []
    if any(k not in PILLAR_OPTIONS for k in pillars):
        return {"ok": False, "error": "Unknown pillar."}
    if any(k not in INTIMACY_KINDS for k in intimacy):
        return {"ok": False, "error": "Unknown intimacy kind."}
    if not intimacy:
        return {"ok": False, "error": "Intimacy is mandatory — pick Emotional, Physical, or both."}

    selected_others = []
    for key in OTHER_VISION_KEYS:
        if key not in pillars:
            continue
        subs = pillars[key]
        if any(s not in PILLAR_OPTIONS[key] for s in subs):
            return {"ok": False, "error": f"Unknown sub-selection for {key}."}
        if key == "Travel together":
            selected_others.append(key)
            continue
        if not subs:
            return {"ok": False, "error": f"{key} needs at least one sub-selection — picking it alone says almost nothing."}
        if key == "Kids" and (set(subs) & NEEDS_PHYSICAL) and "Physical" not in intimacy:
            return {"ok": False,
                    "error": "Having kids naturally needs Physical intimacy selected too. "
                             "Add it, or choose surrogacy or adoption instead."}
        selected_others.append(key)

    if not selected_others:
        return {"ok": False, "error": "Pick at least one more pillar alongside Intimacy — Travel together, Kids, or Cohabitate."}

    return {"ok": True, "error": None}


def rc_open(clock: clock_module.SimulationClock) -> bool:
    """round3-fixes-spec.md §7.3: "Declare a Change" is only editable
    while RC is open — the same weekly Reality Check window week_map.py
    marks (clock.FEEDBACK_OPENS, Sunday 21:00, through clock.RC_ENDS, the
    following Monday 11:00). "Add Detail" carries no such gate — it never
    removes anything, so there is nothing about it RC needs to protect.
    """
    day, hour = clock.day, clock.hour
    if day == clock_module.FEEDBACK_OPENS[0]:
        return hour >= clock_module.FEEDBACK_OPENS[1]
    if day == clock_module.RC_ENDS[0]:
        return hour < clock_module.RC_ENDS[1]
    return False


def add_detail(vision_json: list[dict[str, Any]], pillar: str, sub_selection: str | None = None) -> dict[str, Any]:
    """round3-fixes-spec.md §7.2: "Add Detail captures a pillar or
    sub-selection not present in the original Vision... It is not a
    general edit affordance and must not allow removals." Adding a
    pillar that already exists with the SAME sub-selection (or, for
    Travel together, adding it when it is already present) is refused —
    there is nothing new to add, and this function never no-ops silently.
    """
    if pillar not in PILLAR_OPTIONS:
        return {"ok": False, "error": "Unknown pillar."}
    if sub_selection is not None and sub_selection not in PILLAR_OPTIONS[pillar]:
        return {"ok": False, "error": "Unknown sub-selection for this pillar."}
    if pillar == "Travel together" and sub_selection is not None:
        return {"ok": False, "error": "Travel together takes no sub-selection."}

    pillars = _as_pillars(vision_json)
    existing = list(pillars.get(pillar, []))
    already_present = pillar in pillars and (sub_selection is None or sub_selection in existing)
    if already_present:
        return {"ok": False, "error": "That is already part of your Vision."}

    new_pillars = dict(pillars)
    new_pillars[pillar] = existing + [sub_selection] if sub_selection is not None else existing

    check = validate_pillars(new_pillars)
    if not check["ok"]:
        return check
    return {"ok": True, "error": None, "vision_json": _as_vision_json(new_pillars),
            "pillar": pillar, "added": sub_selection}


def declare_change(
    vision_json: list[dict[str, Any]], pillar: str,
    add: list[str] | None = None, remove: list[str] | None = None,
    *, disclosed_to_partner: bool = False, clock: clock_module.SimulationClock | None = None,
) -> dict[str, Any]:
    """round3-fixes-spec.md §7.3: within an EXISTING pillar, add and/or
    remove sub-selections. Never a brand-new pillar (add_detail()'s job).
    Refuses unless `disclosed_to_partner` is true — an undisclosed
    reversal defeats the guardrail — and unless `clock` falls inside
    rc_open()'s window. The resulting FULL state must still satisfy
    every §7.1 rule; a removal that would break it (dropping Intimacy to
    nothing, falling below two pillars, emptying Kids/Cohabitate's own
    minimum) is refused with the same message validate_pillars() gives
    anywhere else, not a silent reset.
    """
    if not disclosed_to_partner:
        return {"ok": False, "error": "A change must be disclosed to your partner — it cannot be declared silently."}
    if clock is not None and not rc_open(clock):
        return {"ok": False, "error": "This is only editable while Reality Check is open."}

    add, remove = list(add or []), list(remove or [])
    if pillar not in PILLAR_OPTIONS:
        return {"ok": False, "error": "Unknown pillar."}
    if not add and not remove:
        return {"ok": False, "error": "Nothing to change."}
    if any(s not in PILLAR_OPTIONS[pillar] for s in (*add, *remove)):
        return {"ok": False, "error": "Unknown sub-selection for this pillar."}
    if pillar == "Travel together":
        return {"ok": False, "error": "Travel together has no sub-selections to change."}

    pillars = _as_pillars(vision_json)
    if pillar not in pillars:
        return {"ok": False, "error": "You have not set this pillar yet — use Add Detail instead."}

    before = list(pillars[pillar])
    after = sorted((set(before) | set(add)) - set(remove))
    new_pillars = dict(pillars)
    if after:
        new_pillars[pillar] = after
    elif pillar == "Intimacy":
        new_pillars[pillar] = after  # stays present, empty — validate_pillars() refuses this
    else:
        del new_pillars[pillar]  # nothing left under this pillar; it is no longer selected

    check = validate_pillars(new_pillars)
    if not check["ok"]:
        return check
    return {"ok": True, "error": None, "vision_json": _as_vision_json(new_pillars),
            "pillar": pillar, "from": sorted(before), "to": after}


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
# topic — "only the ones their Vision selections unlock." Keyed on the
# real pillar names now (round3-fixes-spec.md §7 — element_key IS the
# pillar since add_detail()/declare_change() write vision_json's own
# vocabulary, not a separate free-text one). A key may unlock more than
# one topic (Cohabitate implies both shared space and shared expenses).
#
# "career_and_relocation" is gone along with the two pillars that used
# to unlock it (§7.1: "Remove Relocation and Career entirely") — nothing
# can reach it any more, so it is not a topic rather than a permanently
# locked one.
SPECIFIC_TIER_UNLOCKS: dict[str, list[str]] = {
    "Kids": ["children"],
    "Cohabitate": ["household_and_shared_space", "shared_expenses"],
}

# Fixed display order (§D5's own listing order), independent of the order
# a user happened to add Vision entries in — two couples' playbooks read
# the same way regardless of which topic they unlocked first.
_SPECIFIC_TIER_ORDER = ["household_and_shared_space", "shared_expenses", "children"]


def unlocked_specific_topics(vision_entries_for_user: list[dict[str, Any]]) -> list[str]:
    """The subset of D5's four Specific-tier topics this user's own
    Vision entries actually unlock, deduplicated, in §D5's fixed order."""
    unlocked: set[str] = set()
    for entry in vision_entries_for_user:
        unlocked.update(SPECIFIC_TIER_UNLOCKS.get(entry["element_key"], []))
    return [topic for topic in _SPECIFIC_TIER_ORDER if topic in unlocked]
