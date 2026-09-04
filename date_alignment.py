"""The fields a date needs, asked when there is a date to need them.

2026-09-04, user's rule: "Dates alignment requires budget etc, so this
also needs to be shared at different times. But just want to make the sign
up little seamless."

Budget, diet and cuisine were all mandatory at sign-up, where they are
three more questions between a stranger and their first match, and where
the honest answer is often "it depends". They are genuinely needed — the
agreement's bill clause, the venue's diet, the cuisine — but only once two
people are actually arranging an evening.

So they are asked then. Two things follow from that timing, and both are
improvements rather than compromises:

  * the person answering has a reason to care, because a real date is
    waiting on it; and
  * the answer can be about THIS date rather than a permanent preference,
    which is what "it depends" was trying to say all along.

Answers are written back to the user's stats, so someone who fills them in
once is not asked again — but they can be changed per date, and the newest
answer is the one the agreement reads.

Pure functions. The caller persists.
"""

from __future__ import annotations

from typing import Any

import locale_defaults
from generate_users import CUISINES, DIETS

# The stats a date cannot be arranged without. Deliberately the same keys
# used in stats_json, so filling them in here is indistinguishable from
# having filled them in at sign-up.
FIELDS = ("budget", "diet", "cuisine")

LABELS = {
    "budget": "What you would like to spend",
    "diet": "What you eat",
    "cuisine": "Cuisines you enjoy",
}

BLURBS = {
    "budget": "Sets the band in the agreement's bill clause. The lower of the two applies, so "
              "neither of you is committed to the other's idea of an evening.",
    "diet": "Decides the venue. It has to carry something you both actually eat.",
    "cuisine": "Narrows the venue to something you would both choose, not merely tolerate.",
}


def options_for(field: str, city: str | None = None) -> list[str]:
    """The choices for one field, ordered for this city where that helps."""
    if field == "budget":
        return locale_defaults.budget_bands_for(city)
    if field == "diet":
        return locale_defaults.diets_for(city)
    if field == "cuisine":
        return list(CUISINES)
    raise ValueError(f"Unknown date-alignment field {field!r}; expected one of {FIELDS}")


def missing(stats: dict[str, Any]) -> list[str]:
    """Which of the three this user still has not answered."""
    return [field for field in FIELDS if not stats.get(field)]


def is_complete(stats: dict[str, Any]) -> bool:
    return not missing(stats)


def pending_for_pair(a_stats: dict[str, Any], b_stats: dict[str, Any]) -> dict[str, list[str]]:
    """What each side still owes. A date needs both halves — one person
    answering does not settle a bill split."""
    return {"a": missing(a_stats), "b": missing(b_stats)}


def ready_for_pair(a_stats: dict[str, Any], b_stats: dict[str, Any]) -> bool:
    pending = pending_for_pair(a_stats, b_stats)
    return not pending["a"] and not pending["b"]


def validate(form: dict[str, Any], city: str | None = None) -> dict[str, Any]:
    """Check one person's answers. Returns {"ok", "error", "stats"}.

    All three are required HERE, unlike at sign-up — by this point there is
    a date waiting on them, and a half-filled answer produces an agreement
    with a blank in it.
    """
    stats: dict[str, Any] = {}

    budget = str(form.get("budget", "")).strip()
    if budget not in options_for("budget", city):
        return {"ok": False, "error": "Pick a budget band — it sets the bill clause.", "stats": None}
    stats["budget"] = budget

    diet = str(form.get("diet", "")).strip()
    if diet not in DIETS:
        return {"ok": False, "error": "Pick what you eat, so the venue carries it.", "stats": None}
    stats["diet"] = diet

    raw = form.get("cuisine") or []
    if isinstance(raw, str):
        raw = [raw]
    chosen = sorted(value for value in CUISINES if value in raw)
    if not chosen:
        return {"ok": False, "error": "Pick at least one cuisine you enjoy.", "stats": None}
    stats["cuisine"] = chosen

    return {"ok": True, "error": None, "stats": stats}


def lower_budget(a_budget: str | None, b_budget: str | None, city: str | None = None) -> str | None:
    """The band that actually applies to a shared bill.

    The lower of the two, always. The alternative — averaging, or taking
    the higher — quietly commits the person with less money to an evening
    they did not choose, and the bill clause is precisely where that bites.
    """
    bands = options_for("budget", city)
    ranks = [bands.index(b) for b in (a_budget, b_budget) if b in bands]
    if not ranks:
        return None
    return bands[min(ranks)]


def shared_cuisines(a: list[str] | None, b: list[str] | None) -> list[str]:
    """What both of them named. Empty is a real answer — it means the venue
    has to be chosen on diet alone, and the agreement should say so rather
    than inventing an overlap."""
    return sorted(set(a or []) & set(b or []))
