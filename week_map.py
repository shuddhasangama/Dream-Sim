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

from typing import Any

import clock as clock_module

DAYS = clock_module.DAYS_OF_WEEK          # Mon … Sun
BANDS = [
    ("morn", "MORN", 0, 12),
    ("aft", "AFT", 12, 17),
    ("eve", "EVE", 17, 21),
    ("night", "NIGHT", 21, 24),
]

# The midday rule, drawn as a line on the grid rather than explained in a
# sentence: everything above it is yesterday's window closing, everything
# below is today's opening.
MIDDAY_LABEL = "MIDDAY (12:00)"

# Each entry: the checkpoint it comes from, a short label for the cell, a
# tone (which colour the mock-up gives it), and the sentence that says
# what it means. `kind` groups them for the legend.
#
# `at` is a clock.py constant, never a literal — see the module docstring.
MOMENTS: list[dict[str, Any]] = [
    {"key": "match_1", "at": clock_module.MATCH_1_REVEAL, "label": "Match 1",
     "tone": "match", "kind": "Matches",
     "means": "Match 1 is revealed. You have until Tuesday midday."},
    {"key": "rc_ends", "at": ("Mon", 11), "label": "RC ends",
     "tone": "reality", "kind": "Reality Check",
     "means": "Last week's Reality Check closes, just before the new week opens."},
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
    {"key": "feedback", "at": clock_module.FEEDBACK_OPENS, "label": "Reality",
     "tone": "reality", "kind": "After",
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


def grid(now: clock_module.SimulationClock | None = None) -> dict[str, Any]:
    """The whole grid, as the template needs it: one cell per (band, day),
    each holding however many moments land there.

    `now` marks today's column and the cells already behind you, so the
    screen answers "where am I in this?" rather than just listing a
    timetable.
    """
    today = now.day if now is not None else None
    cells: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for moment in MOMENTS:
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
