"""Which stats can be changed, and when.

2026-09-09, user's rules:

    "There is no way to edit or update the Stats. Please make this
    available."

    "if someone is working on diet who can change their weight or waist
    or dietary etc. This should be editable until there is no matches
    available or keenness expressed. Cause we don't want stats to change
    between the match and date. So take cognizance of it. While they are
    in relationship or dating stats can change. Which can be captured and
    also notified to their match."

THE PROBLEM
Somebody training or changing their diet has stats that go stale in
weeks, and there was no way to correct them at all. But a stat is also
what a stranger said yes to. Letting it move between the yes and the
evening is a bait-and-switch, however innocently meant.

So editing is not one permission. It is three, decided per field:

  NEVER          The BGV-verified fields — age, education, nationality,
                 profession, salary band. A verified badge that the
                 holder can retype is not a verified badge. Changing one
                 is a support request, not a form.

  WHILE NOBODY   The soft stats a candidate can SEE on a match card or
  IS LOOKING     FILTER on in REACH. Editable freely, but frozen while a
                 match is live, because somebody is deciding on them
                 right now.

  ALWAYS         Everything else — soft stats nobody screens you on.
  (while dating) Editable whenever, because no decision rests on them.

And over all of it: once EITHER of you has expressed keenness, everything
freezes until the date is done. That is the window the user called out.

IN A RELATIONSHIP the freeze lifts entirely and the rule inverts: stats
change, and the change is disclosed to the partner — the same shape
VisionChange already uses, where a declared change is always disclosed.
Nothing is hidden and nothing is blocked.

This module decides. It reads no database and no clock; app.py hands it
the situation.
"""

from __future__ import annotations

from typing import Any

# ── the three groups ──────────────────────────────────────────────────────

# Verified at sign-up and re-checked by BGV. Never editable in-app.
VERIFIED = ("age", "education", "nationality", "profession", "income_band")

# Soft, but a candidate sees these on the match card or screens on them
# through a REACH lever (matching.LEVERS). Frozen while a match is live.
#
# weight_kg and waist_in are here because they are RANGE_LEVERS — someone
# else's filter runs against them. That is exactly the "working on their
# diet" case, and it means those edits land between match windows rather
# than during one.
CANDIDATE_FACING = ("height_cm", "weight_kg", "waist_in", "diet", "religion")

# Soft and nobody screens on them. Editable whenever.
FREE = ("smoking", "drinking", "fitness_routine", "marital_history",
        "ethnicity", "languages", "cuisine", "budget")

EDITABLE = CANDIDATE_FACING + FREE
ALL_FIELDS = VERIFIED + EDITABLE

# The stats key and the BGV key are not always the same word: a person
# declares a salary, and what gets checked is the BAND. Anything absent
# here is checked under its own name.
BGV_FIELD = {"income_band": "salary_bracket"}


def bgv_field(field: str) -> str:
    """The verification key for a stats field."""
    return BGV_FIELD.get(field, field)


# Why each group is what it is, in words a person should read.
VERIFIED_REASON = (
    "Vouched for by a background check, so it is not typed over. If one "
    "has genuinely changed, send it back to be re-checked — the value "
    "moves when the check clears, not when you say so."
)
LIVE_MATCH_REASON = (
    "Someone is looking at your profile this week. This one is on your "
    "match card, so it holds until the window closes."
)
KEENNESS_REASON = (
    "One of you has said yes. Nothing changes between that and the date."
)


def situation(*, in_relationship: bool = False, keenness: bool = False,
              live_match: bool = False) -> dict[str, bool]:
    """The three facts this module needs, named."""
    return {"in_relationship": bool(in_relationship),
            "keenness": bool(keenness),
            "live_match": bool(live_match)}


def editable(field: str, state: dict[str, bool]) -> dict[str, Any]:
    """Whether one field can be changed right now, and why not if not.

    Order matters. Verified is checked first because it outranks
    everything — being in a relationship does not make a badge editable.
    """
    if field in VERIFIED:
        return {"editable": False, "reason": VERIFIED_REASON, "why": "verified"}

    # In a relationship there is no pool, no match window and no date to
    # protect. Everything soft opens, and the disclosure rule takes over.
    if state.get("in_relationship"):
        return {"editable": True, "reason": None, "why": "relationship"}

    if state.get("keenness"):
        return {"editable": False, "reason": KEENNESS_REASON, "why": "keenness"}

    if state.get("live_match") and field in CANDIDATE_FACING:
        return {"editable": False, "reason": LIVE_MATCH_REASON, "why": "live_match"}

    return {"editable": True, "reason": None, "why": "open"}


def discloses_to_partner(state: dict[str, bool]) -> bool:
    """Whether a change made now has to be shown to the partner.

    Only in a relationship. While dating there is nobody with a standing
    expectation to correct — that is what the freeze is for instead.
    """
    return bool(state.get("in_relationship"))


def rows(stats: dict[str, Any], state: dict[str, bool]) -> list[dict[str, Any]]:
    """Every field with its current value and its verdict, in the order
    the screen shows them: what you can change, then what you cannot."""
    out = []
    for field in EDITABLE + VERIFIED:
        verdict = editable(field, state)
        out.append({"key": field, "value": stats.get(field), **verdict})
    return out


def coerce(field: str, raw: str, ranges: dict[str, tuple[int, int]]) -> dict[str, Any]:
    """Turn one submitted value into what belongs in stats_json.

    2026-09-09 (evening): the stats editor stored whatever the form sent,
    which is always a string. A saved weight landed as "70", and REACH's
    slider does `self_value - min` — so the very next screen after saving
    raised TypeError and returned a 500. The editor wrote a stat the rest
    of the app could not read.

    Numeric fields become ints and are bounds-checked here rather than
    trusting the input's min/max, which is a client-side courtesy.
    Everything else is text and passes through.

    Returns {"ok", "value", "error"}. An empty value clears the field,
    which is a legitimate thing to do and not an error.
    """
    raw = (raw or "").strip()
    if raw == "":
        return {"ok": True, "value": None, "error": None}

    if field not in ranges:
        return {"ok": True, "value": raw, "error": None}

    try:
        number = int(float(raw))
    except (TypeError, ValueError):
        return {"ok": False, "value": None, "error": f"{field} has to be a number."}

    low, high = ranges[field]
    if not low <= number <= high:
        return {"ok": False, "value": None,
                "error": f"{field} has to be between {low} and {high}."}
    return {"ok": True, "value": number, "error": None}


def change_record(user_id: str, field: str, before: Any, after: Any,
                  declared_at: str) -> dict[str, Any]:
    """The StatChange row for a change made inside a relationship.

    Modelled on VisionChange, including its rule that a change is always
    disclosed — there is no undisclosed variant to choose.
    """
    return {
        "user_id": user_id,
        "field": field,
        "from_value": "" if before is None else str(before),
        "to_value": "" if after is None else str(after),
        "declared_at": declared_at,
        "disclosed_to_partner": 1,
    }
