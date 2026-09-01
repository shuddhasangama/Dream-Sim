"""SimulationClock — deterministic day+hour clock for the Dating stage's
weekly cadence (docs/dating-stage-spec.md §1: "Every user in a city is on
the same clock").

Pure, hashable, orderable — no wall-clock reads, no randomness, matching
docs/CLAUDE.md's rule that everything except Guru narration stays
deterministic. Stays week-relative (day index 0-6, hour 0-23); a real
calendar date/time is only derived where something genuinely needs one
(DatePlan.datetime), via app.py's existing WEEK_ONE_MONDAY + week_to_date()
epoch convention — not duplicated here.

Match/LockIn/Signature rows store clock stamps as "Day:Hour" text (e.g.
"Mon:12") alongside their own `week` column, round-tripped by str(clock)/
SimulationClock.parse(week, stamp).
"""

from __future__ import annotations

from dataclasses import dataclass

DAYS_OF_WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DAY_INDEX = {day: i for i, day in enumerate(DAYS_OF_WEEK)}


@dataclass(frozen=True, order=True)
class SimulationClock:
    """A point in simulated time: (week, day, hour). Orderable — comparing
    two clocks compares (week, day_index, hour) lexicographically, so a
    later week always sorts after an earlier one regardless of day/hour."""

    week: int
    day_index: int  # 0=Mon .. 6=Sun
    hour: int  # 0-23

    @classmethod
    def at(cls, week: int, day: str, hour: int) -> "SimulationClock":
        if day not in _DAY_INDEX:
            raise ValueError(f"Unknown day {day!r}; expected one of {DAYS_OF_WEEK}")
        if not (0 <= hour <= 23):
            raise ValueError(f"hour must be 0-23, got {hour}")
        return cls(week, _DAY_INDEX[day], hour)

    @property
    def day(self) -> str:
        return DAYS_OF_WEEK[self.day_index]

    def advance_hours(self, hours: int) -> "SimulationClock":
        """Move forward `hours` hours, rolling into later days and, past
        Sunday 23:00, into next week's Monday 00:00."""
        total = self.day_index * 24 + self.hour + hours
        week = self.week + total // (24 * 7)
        total %= 24 * 7
        return SimulationClock(week, total // 24, total % 24)

    def __str__(self) -> str:
        return f"{self.day}:{self.hour:02d}"

    @classmethod
    def parse(cls, week: int, stamp: str) -> "SimulationClock":
        """Inverse of str(clock) for a given week, e.g. parse(3, 'Mon:12')
        — reconstructs a clock from a stored revealed_at/window_closes_at/
        created_at/signed_at column."""
        day, hour = stamp.split(":")
        return cls.at(week, day, int(hour))


# ── §1's exact weekly timeline, as (day, hour) checkpoints ────────────────
# Match 3's window close and the calendar opening are the same moment
# ("Wed evening") per the spec's own table — both point at ("Wed", 18).
MATCH_1_REVEAL = ("Mon", 12)
MATCH_1_CLOSE = MATCH_2_REVEAL = ("Tue", 12)
MATCH_2_CLOSE = MATCH_3_REVEAL = ("Wed", 12)
MATCH_3_CLOSE = CALENDAR_OPENS = ("Wed", 18)
CALENDAR_CLOSES = ("Thu", 12)
DATES_LIVE = ("Thu", 18)
FEEDBACK_OPENS = ("Sun", 21)

MATCH_REVEAL_BY_SLOT = {1: MATCH_1_REVEAL, 2: MATCH_2_REVEAL, 3: MATCH_3_REVEAL}
MATCH_CLOSE_BY_SLOT = {1: MATCH_1_CLOSE, 2: MATCH_2_CLOSE, 3: MATCH_3_CLOSE}

PHASES = [
    "before_week_start",
    "match_1_open",
    "match_2_open",
    "match_3_open",
    "calendar_open",
    "calendar_closed",
    "dates_live",
    "feedback_open",
]


def checkpoint(week: int, point: tuple[str, int]) -> SimulationClock:
    """A named (day, hour) checkpoint resolved to a real clock for a
    specific week, e.g. checkpoint(3, MATCH_1_REVEAL)."""
    day, hour = point
    return SimulationClock.at(week, day, hour)


def phase(clock: SimulationClock) -> str:
    """Which part of the weekly cadence `clock` falls in (one of PHASES),
    per §1's table — lets a caller ask "what should be visible/open right
    now" without re-deriving the checkpoint comparisons by hand."""
    week = clock.week
    if clock < checkpoint(week, MATCH_1_REVEAL):
        return "before_week_start"
    if clock < checkpoint(week, MATCH_1_CLOSE):
        return "match_1_open"
    if clock < checkpoint(week, MATCH_2_CLOSE):
        return "match_2_open"
    if clock < checkpoint(week, MATCH_3_CLOSE):
        return "match_3_open"
    if clock < checkpoint(week, CALENDAR_CLOSES):
        return "calendar_open"
    if clock < checkpoint(week, DATES_LIVE):
        return "calendar_closed"
    if clock < checkpoint(week, FEEDBACK_OPENS):
        return "dates_live"
    return "feedback_open"
