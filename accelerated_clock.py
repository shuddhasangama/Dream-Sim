"""Opt-in, deployment-wide rehearsal timeline; never advances anyone's decisions.

An absolute UTC start keeps all workers/devices on the same timeline, including
after a restart. Reads do not write clock files, plans or outcomes.
"""
import os
from datetime import datetime, timedelta, timezone

import clock

INTERVAL_SECONDS = 180
POINTS = (("Mon", 10), ("Mon", 12), ("Tue", 12), ("Wed", 12),
          ("Wed", 18), ("Thu", 12), ("Thu", 18))


def enabled():
    return clock.simulated() and os.environ.get("DHASHU_ACCELERATED_TEST", "").lower() == "true"


def settings():
    start = datetime.fromisoformat(os.environ["DHASHU_TEST_START_UTC"].replace("Z", "+00:00"))
    if start.tzinfo is None:
        raise ValueError("DHASHU_TEST_START_UTC must include a timezone, preferably Z (UTC).")
    week = int(os.environ["DHASHU_TEST_START_WEEK"])
    if week < 1:
        raise ValueError("DHASHU_TEST_START_WEEK must be positive.")
    return start, week


def position(now=None):
    start, week = settings()
    now = now or datetime.now(timezone.utc)
    elapsed = (now - start).total_seconds()
    step = min(10, max(0, int(elapsed // INTERVAL_SECONDS)))
    return week, step, elapsed


def read(plans=(), now=None):
    week, step, _ = position(now)
    if step < len(POINTS):
        return clock.SimulationClock.at(week, *POINTS[step])
    if step == 10:
        return clock.SimulationClock.at(week + 1, "Mon", 12)
    if step == 9:
        return clock.SimulationClock.at(week, "Sun", 21)

    # One shared clock cannot show Friday for one pair and Sunday for another.
    # Use the latest saved date this week; retain completed/cancelled plans so
    # resolving a date cannot move everyone else's clock backwards.
    monday = clock.WEEK_ONE_MONDAY + timedelta(weeks=week - 1)
    points = []
    for plan in plans:
        date = datetime.fromisoformat(plan["datetime"])
        day = (date.date() - monday).days
        if day not in (4, 5, 6):
            continue
        if step == 8:
            date += timedelta(hours=1)
        if date.minute or date.second or date.microsecond:
            date = date.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        points.append(clock.SimulationClock(week, day, min(date.hour, 23)))
    return max(points, default=clock.SimulationClock.at(week, "Thu", 18))


def metadata(now=None):
    if not enabled():
        return None
    week, step, elapsed = position(now)
    return {"enabled": True, "interval_seconds": INTERVAL_SECONDS,
            "step": step, "start_week": week, "finished": step == 10,
            "starts_in_seconds": max(0, int(-elapsed)),
            "next_jump_in_seconds": None if step == 10 else max(0, int((step + 1) * INTERVAL_SECONDS - elapsed)),
            "scope": "deployment", "date_policy": "latest_saved_weekend_plan",
            "decisions_automated": False}
