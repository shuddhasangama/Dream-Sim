"""THE WEEK — the grid on the mock-up's Week screen.

2026-09-10, user's rule: "Once the users are registered and bgv
verification is completed I would want to show the Calendar process which
is available in the mock-up to give the brief summary of the calendar
days and respective stages."

The product is time-gated at every step — matches reveal at midday, the
calendar shuts Thursday noon, feedback opens Sunday night — and until now
none of that was visible anywhere except one word in the demo bar. A
person could not answer "what happens tomorrow?", which in a product
whose whole premise is pacing is the wrong thing not to know.

DERIVED, NOT RETYPED. Every moment below reads its (day, hour) from
clock.py, which is the same table cadence.py schedules against. Typing
"Tue 12:00" here would be a second copy of the timeline, and the two
would drift the first time a checkpoint moved — the bill-clause mistake
in a new place. test_week_map.py asserts every entry agrees with clock.

The mock-up's grid is days across, four bands down, with the midday line
drawn between MORN and AFT because midday is when matches turn over.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import clock as clock_module
import dateplan

DAYS = clock_module.DAYS_OF_WEEK          # Mon … Sun
BANDS = [
    ("morn", "MORN", 0, 12),
    ("aft", "AFT", 12, 17),
    ("eve", "EVE", 17, 19),
    ("night", "NIGHT", 19, 24),
]

# The midday rule, drawn as a line on the grid rather than explained in a
# sentence: everything above it is yesterday's window closing, everything
# below is today's opening.
MIDDAY_LABEL = "MIDDAY (12:00)"

def _just_before(at: tuple[str, int]) -> tuple[str, int]:
    """The hour before a midday checkpoint — where the grid draws a window
    CLOSING (above the midday line: "yesterday's window closing"), the way
    "Rank" and "RC Closes" already sit. Derived from the clock.py constant,
    never a second literal."""
    return (at[0], at[1] - 1)


# Each entry: the checkpoint it comes from, a short label for the cell, a
# tone (which colour the mock-up gives it), and the sentence that says
# what it means. `kind` groups them for the legend.
#
# `at` is a clock.py constant, never a literal — see the module docstring.
MOMENTS: list[dict[str, Any]] = [
    {"key": "match_1", "at": clock_module.MATCH_1_REVEAL, "label": "Match 1",
     "tone": "match", "kind": "Matches",
     "means": "Match 1 is revealed. You have until Tuesday midday."},
    # round3-fixes-spec.md §5.1: "RC Opens"/"RC Closes" inside the grid's
    # own small cells — "Reality Check" spelled out doesn't fit and reads
    # as noise at that size. The full term stays in the legend, via
    # `kind` below, which is what actually names it for anyone reading
    # cold rather than skimming the grid.
    {"key": "rc_ends", "at": clock_module.RC_ENDS, "label": "RC Closes",
     "tone": "reality", "kind": "Reality Check",
     "means": "Last week's Reality Check closes, just before the new week opens."},
    # round4-fixes-spec.md §6: each window's CLOSE reads as its own pair to
    # the reveal above, in the morning band just above the midday line.
    # `label` is the short cell text ("M1 closes" — the cell is ~40px wide
    # and never truncates mid-word); `full_label` is the full wording, used
    # wherever there is room (the "What each one means" list, tooltips).
    #
    # Match 3 is NOT drawn on Thursday morning: docs/dating-stage-spec.md
    # §1 and clock.MATCH_3_CLOSE close it Wednesday EVENING (the same
    # moment the calendar opens). Thursday 12:00 is the CALENDAR closing
    # ("Publish"), a different event.
    {"key": "match_1_closes", "at": _just_before(clock_module.MATCH_1_CLOSE),
     "label": "M1 closes", "full_label": "Match 1 closes",
     "tone": "match", "kind": "Matches",
     "means": "Match 1's window closes at midday, and Match 2 is revealed."},
    {"key": "match_2_closes", "at": _just_before(clock_module.MATCH_2_CLOSE),
     "label": "M2 closes", "full_label": "Match 2 closes",
     "tone": "match", "kind": "Matches",
     "means": "Match 2's window closes at midday, and Match 3 is revealed."},
    {"key": "match_3_closes", "at": clock_module.MATCH_3_CLOSE,
     "label": "M3 closes", "full_label": "Match 3 closes",
     "tone": "match", "kind": "Matches",
     "means": "Match 3's window closes in the evening — the last of the week."},
    {"key": "rank", "at": ("Tue", 11), "label": "Rank",
     "tone": "muted", "kind": "Matches",
     "means": "Keenness from Match 1 is counted before Match 2 is drawn."},
    {"key": "match_2", "at": clock_module.MATCH_2_REVEAL, "label": "Match 2",
     "tone": "match", "kind": "Matches",
     "means": "Match 1's window closes and Match 2 is revealed."},
    {"key": "match_3", "at": clock_module.MATCH_3_REVEAL, "label": "Match 3",
     "tone": "match", "kind": "Matches",
     "means": "Match 2's window closes and Match 3 is revealed — the last of the week."},
    {"key": "slots", "at": clock_module.CALENDAR_OPENS, "label": "Slots",
     "tone": "calendar", "kind": "Calendar",
     "means": "Match 3 closes and the calendar opens. Offer the weekend slots that suit you."},
    {"key": "calendar_closes", "at": clock_module.CALENDAR_CLOSES, "label": "Publish",
     "tone": "publish", "kind": "Calendar",
     "means": "The calendar closes and the overlap is published to you both."},
    {"key": "sign", "at": clock_module.DATES_LIVE, "label": "Sign",
     "tone": "publish", "kind": "Agreement",
     "means": "The date agreement opens. It needs both signatures; one on its own confirms nothing."},
    {"key": "date_fri", "at": ("Fri", 21), "label": "Dinner",
     "tone": "date", "kind": "Dates",
     "means": "A confirmed slot can fall anywhere across the weekend."},
    {"key": "date_fri_eve", "at": ("Fri", 17), "label": "Coffee",
     "tone": "date", "kind": "Dates"},
    {"key": "date_sat_m", "at": ("Sat", 9), "label": "Bkfst", "tone": "date", "kind": "Dates"},
    {"key": "date_sat_a", "at": ("Sat", 13), "label": "Lunch", "tone": "date", "kind": "Dates"},
    {"key": "date_sat_e", "at": ("Sat", 19), "label": "Dinner", "tone": "date", "kind": "Dates"},
    {"key": "date_sun_m", "at": ("Sun", 9), "label": "Bkfst", "tone": "date", "kind": "Dates"},
    {"key": "date_sun_a", "at": ("Sun", 13), "label": "Lunch", "tone": "date", "kind": "Dates"},
    {"key": "date_sun_e", "at": ("Sun", 17), "label": "Coffee", "tone": "date", "kind": "Dates"},
    {"key": "debrief", "at": ("Sat", 21), "label": "Debrief",
     "tone": "debrief", "kind": "After",
     "means": "The debrief opens an hour after a date, not before it."},
    {"key": "feedback", "at": clock_module.FEEDBACK_OPENS, "label": "RC Opens",
     "tone": "reality", "kind": "Reality Check",
     "means": "Feedback closes the week, and next week's Reality Check is drawn from it."},
]

# What each phase means, in a sentence, for the line under the clock.
PHASE_COPY = {
    "before_week_start": "The week has not opened yet. Match 1 is revealed Monday midday.",
    "match_1_open": "Match 1 is live. You have until Tuesday midday.",
    "match_2_open": "Match 2 is live. You have until Wednesday midday.",
    "match_3_open": "Match 3 is live — the last of this week. It closes Wednesday evening.",
    "calendar_open": "The calendar is open. Offer your weekend slots before Thursday midday.",
    "calendar_closed": "Slots are in. The overlap publishes Thursday evening, with the agreement to sign.",
    "dates_live": "Dates are live this weekend.",
    "feedback_open": "Feedback is open. It closes the week and shapes the next one.",
}


def _band_for(hour: int) -> str:
    for key, _label, start, end in BANDS:
        if start <= hour < end:
            return key
    return BANDS[-1][0]


def grid(now: clock_module.SimulationClock | None = None, *,
         personal_debrief: dict[str, Any] | None = None,
         personal_pool_return: dict[str, Any] | None = None) -> dict[str, Any]:
    """The whole grid, as the template needs it: one cell per (band, day),
    each holding however many moments land there.

    `now` marks today's column and the cells already behind you, so the
    screen answers "where am I in this?" rather than just listing a
    timetable.

    round3-fixes-spec.md §5.3 ("replace in place"): with no personalized
    moments, this is exactly the fixed, same-for-everyone timetable it has
    always been. Pass `personal_debrief` (from personal_debrief_moment())
    to swap out the generic Saturday-21:00 "Debrief" placeholder for
    where THIS person's actual date really put it; pass
    `personal_pool_return` (from pool_return_moment()) to add a moment
    that only exists for someone whose pair has actually been released.
    Each substituted/added moment carries `"personal": True` so a
    template can mark it as theirs rather than the general rhythm.
    """
    today = now.day if now is not None else None
    cells: dict[tuple[str, str], list[dict[str, Any]]] = {}

    moments = list(MOMENTS)
    if personal_debrief is not None:
        moments = [m for m in moments if m["key"] != "debrief"]
        moments.append({**personal_debrief, "personal": True})
    if personal_pool_return is not None:
        moments = [m for m in moments if m["key"] != "feedback"]
        moments.append({**personal_pool_return, "personal": True})

    for moment in moments:
        day, hour = moment["at"]
        band = _band_for(hour)
        past = False
        if now is not None:
            past = (DAYS.index(day), hour) < (DAYS.index(now.day), now.hour)
        cells.setdefault((band, day), []).append({
            **moment, "hour": hour, "day": day, "past": past,
            "time": f"{hour:02d}:00",
        })

    rows = []
    for key, label, _start, _end in BANDS:
        rows.append({
            "key": key, "label": label,
            "days": [{"day": d, "is_today": d == today,
                      "moments": cells.get((key, d), [])} for d in DAYS],
        })
    return {
        "days": [{"day": d, "is_today": d == today} for d in DAYS],
        "rows": rows,
        "midday_after": "morn",     # the line is drawn under this band
        "midday_label": MIDDAY_LABEL,
    }


def legend() -> list[dict[str, str]]:
    """One entry per kind, in the order they happen. The grid is dense by
    design; this is what stops it being a puzzle."""
    seen: dict[str, dict[str, str]] = {}
    for moment in MOMENTS:
        if moment["kind"] not in seen:
            seen[moment["kind"]] = {"kind": moment["kind"], "tone": moment["tone"]}
    return list(seen.values())


def explained() -> list[dict[str, str]]:
    """The moments that carry a meaning, in the order they occur — the
    read-it-once version of the grid, for anyone who would rather have
    sentences than a timetable."""
    out = [m for m in MOMENTS if m.get("means")]
    return sorted(out, key=lambda m: (DAYS.index(m["at"][0]), m["at"][1]))


def phase_copy(phase: str) -> str:
    return PHASE_COPY.get(phase, "")


# ── round3-fixes-spec.md §5.2/§5.3: personalized, conditional moments ──────
#
# Everything above is one fixed timetable — the same for every user, every
# week, on purpose (it is the general rhythm, not any one person's
# calendar). Debrief is different: it only applies to someone who
# actually had a date, at the actual time THEIR date happened, not a
# generic placeholder — §5.2's fix. "Back in the pool" is conditional in
# a different way: RC's own clock time is already fixed and synchronized
# for the whole population (matches are drawn together, the week turns
# over together — there is no per-couple time to compute), so what is
# personal here is not WHEN, only WHETHER it applies to this viewer at
# all — decided in grid(), which is what §5.3 asked to build ("replace in
# place") once a treatment was chosen.


def plan_slot(plan: dict[str, Any]) -> tuple[int, int] | None:
    """Where a confirmed DatePlan's debrief actually opens, as
    (day_index, hour) — derived from the plan's own stored datetime and
    meal slot via dateplan.debrief_opens_hour(), the same real scheduling
    app.py's web debrief screen and the JSON debrief API already use.
    None if the plan has no readable slot yet."""
    stamp = plan.get("datetime")
    if not stamp or "T" not in stamp:
        return None
    try:
        day_index = date.fromisoformat(stamp.split("T")[0]).weekday()
    except ValueError:
        return None
    return day_index, dateplan.debrief_opens_hour(plan["meal"])


def personal_debrief_moment(plan: dict[str, Any]) -> dict[str, Any] | None:
    """The one real 'Debrief' moment for the person who actually has this
    date — not the fixed Saturday-21:00 entry in MOMENTS above, which is
    only ever a placeholder for the general shape of a week.

    round3-fixes-spec.md §5.2: "If a date is scheduled Saturday dinner,
    the debrief appears after that, not on a generic Sunday marker" — this
    is the function that makes that true, given the plan actually confirmed.
    """
    slot = plan_slot(plan)
    if slot is None:
        return None
    day_index, hour = slot
    return {"key": "debrief", "at": (DAYS[day_index], hour), "label": "Debrief",
            "tone": "debrief", "kind": "After",
            "means": "Opens an hour after your actual date — this date's real time, not a fixed slot."}


def pool_return_moment(released: bool) -> dict[str, Any] | None:
    """round3-fixes-spec.md §5.3: 'After a date: Debrief opens → if the
    pair returns to the pool, RC opens.' RC's own timing is already fixed
    and synchronized for everyone (the "feedback" MOMENTS entry, at
    clock.FEEDBACK_OPENS — matches are drawn and the week turns over for
    the whole population together, not per couple), so there is no new
    time to compute — this reuses that exact moment. What IS conditional
    is whether RC is relevant to THIS person at all this week: only once
    their LockIn has actually been released (outcomes.release_lockin),
    never while they are still locked in or have moved to Relationship.
    `released` is that one fact, from the caller.
    """
    if not released:
        return None
    feedback = next(m for m in MOMENTS if m["key"] == "feedback")
    # Same key as the generic entry on purpose — grid() replaces it in
    # place rather than adding a second marker in the same cell.
    return {**feedback, "means": "You're back in the pool — Reality Check for the coming week applies to you."}
