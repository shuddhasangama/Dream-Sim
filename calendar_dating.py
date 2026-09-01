"""Dating-stage calendar process (docs/dating-stage-spec.md §5) — fixed
Fri/Sat/Sun meal-slot availability for a locked-in pair choosing their
first date. Entirely separate from the Relationship-stage RoadProfile/
CalendarEntry free-form-time-range system (a different stage's table, no
shared code — this one's slots are fixed meal windows, not derived gaps).

Opens Wed evening for locked-in pairs, closes Thu 12:00 (clock.py's
CALENDAR_OPENS/CALENDAR_CLOSES). Each partner submits Availability rows
(day, meal_slot); this module finds the overlap and offers a dietary-aware
venue suggestion for it, plus §5's two no-overlap options. Payment gating
(§5: "opens only once the calendar slot is confirmed") lives in
dateplan.py — that's about the DatePlan/Signature pipeline, not the
calendar itself.
"""

from __future__ import annotations

# Friday is a working day: Coffee and Dinner only. Weekend days get all
# four meal slots. Order here is the canonical display/overlap order.
DAY_SLOTS = {
    "Fri": ["coffee", "dinner"],
    "Sat": ["breakfast", "lunch", "coffee", "dinner"],
    "Sun": ["breakfast", "lunch", "coffee", "dinner"],
}


def valid_slots() -> list[tuple[str, str]]:
    """Every (day, meal_slot) pair a partner is allowed to submit, in
    canonical Fri->Sun, breakfast->dinner order."""
    return [(day, slot) for day, slots in DAY_SLOTS.items() for slot in slots]


def compute_overlap(slots_a: list[tuple[str, str]], slots_b: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The (day, meal_slot) pairs both partners submitted, in canonical
    order — §5: "system finds the overlap. If multiple overlaps, the pair
    picks one" (the picking itself is a caller/UI concern; this just finds
    the candidates)."""
    common = set(slots_a) & set(slots_b)
    return [slot for slot in valid_slots() if slot in common]


# Dietary tags, from most to least restrictive — a venue tagged "vegan"
# satisfies a Jain/Vegetarian/Halal/Everything diner too, but not the
# reverse, so suggest_venue() below picks whichever tag is the STRICTER of
# the two diners' needs.
_DIET_TAG_ORDER = ["vegan", "jain", "veg", "halal", "any"]
_DIET_TAG = {
    "Vegan": "vegan",
    "Jain": "jain",
    "Vegetarian": "veg",
    "Halal": "halal",
    "Eggetarian": "any",
    "No red meat": "any",
    "Everything": "any",
}
_VENUE_BY_TAG = {
    "vegan": {"venue": "Plant-forward café", "cuisine": "vegan"},
    "jain": {"venue": "Jain-friendly thali house", "cuisine": "Jain"},
    "veg": {"venue": "Vegetarian multi-cuisine", "cuisine": "vegetarian"},
    "halal": {"venue": "Halal-certified grill", "cuisine": "halal"},
    "any": {"venue": "Multi-cuisine bistro", "cuisine": "multi-cuisine"},
}


def suggest_venue(day: str, meal_slot: str, diet_a: str, diet_b: str) -> dict:
    """A dietary-aware venue suggestion for a confirmed (day, meal_slot) —
    §5: "dietary preferences drive venue suggestions". Picks the venue
    tagged for whichever of the two diets is stricter, so neither
    partner's dietary need is silently dropped. Purely a suggestion — §5
    also allows "decide together" instead; that choice is the caller's,
    not this function's."""
    tag_a = _DIET_TAG.get(diet_a, "any")
    tag_b = _DIET_TAG.get(diet_b, "any")
    tag = tag_a if _DIET_TAG_ORDER.index(tag_a) <= _DIET_TAG_ORDER.index(tag_b) else tag_b
    return {"day": day, "meal_slot": meal_slot, **_VENUE_BY_TAG[tag]}


def no_overlap_options(week: int) -> dict:
    """§5's two choices when no overlap exists between the two submitted
    availabilities: offer next weekend (same LockIn, a fresh Availability
    submission for `week + 1`) or return both to the pool
    (lockin.release()). Which one the pair takes is their choice, made
    through the UI — this just describes the two options."""
    return {"next_weekend_week": week + 1, "return_to_pool": True}
