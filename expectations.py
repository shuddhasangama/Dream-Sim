"""When each expectations question opens, and what it hangs off.

2026-09-09, user's rule:

    "'How much it matters to you' section under 'After your first date'
    within Guru - somehow seems misplaced. Doesn't tie it to Pace of
    physical intimacy.

    Also 'Openness to discussing sexual health and contraception' let it
    be subheading after someone chooses 'Pace of physical Intimacy' -
    maybe a day later or something where in what has been selected is
    choose and then this can open up. We don't want to burden the user,
    not corner them to answer, but help them pace out details to be
    answered."

THE SHAPE OF THE PROBLEM
Five questions about physical intimacy, all on one screen, all visible
the day after a first meeting. Every one of them is answerable — that is
not the objection. The objection is that presenting them together turns
a conversation into a form, and a form after one date is something to
get through rather than something to think about.

So the questions are a SEQUENCE, not a page:

  1. Pace          asked first, on its own, answerable in one tap
  2. How much it   a follow-up to the pace just chosen, and phrased as
     matters       one — it is the "why" of the answer above it, which is
                   what made it read as misplaced when it floated free
  3. Health        held back until a pace exists AND a day has passed
     openness

WHY A DAY
The same reasoning as the stage gate's reflection pause. A question that
appears the moment you answer the previous one is a form advancing; a
question that is not there yet, and then is, is a conversation resuming.
The delay is what makes the difference, and it costs nothing — none of
this is required before a second date.

NOTHING HERE IS MANDATORY. A locked question is not a blocked user: they
can go on dating, go to the next stage gate, do anything else. The lock
only decides what the screen SHOWS, so that it never shows more than the
next reasonable thing.
"""

from __future__ import annotations

from typing import Any

# The answer everything else hangs off.
PACE = "intimacy_pace"

# Asked as a follow-up to PACE, on the same card, as soon as PACE exists.
FOLLOWS_PACE = ("intimacy_importance", "intimacy_notes")

# Held back until PACE has been answered and this many hours have passed
# since. A day, not an hour: it has to be long enough that the person is
# doing something else when it opens.
HEALTH = "health_openness"
HEALTH_OPENS_AFTER_HOURS = 24


def has_pace(answers: dict[str, Any]) -> bool:
    return bool((answers or {}).get(PACE))


def hours_since_pace(pace_answered_at: float | None, now_hours: float | None) -> float | None:
    """How long a pace answer has been on the record. None when either
    end is unknown, which callers treat as "not yet" rather than
    guessing — under-opening is the safe direction here."""
    if pace_answered_at is None or now_hours is None:
        return None
    return max(now_hours - pace_answered_at, 0.0)


def health_open(answers: dict[str, Any], pace_answered_at: float | None,
                now_hours: float | None) -> bool:
    """Whether the sexual-health question is showing yet.

    Already answered counts as open — otherwise editing your own answer
    would vanish on the next page load, which is worse than showing it
    early.
    """
    if (answers or {}).get(HEALTH):
        return True
    if not has_pace(answers):
        return False
    elapsed = hours_since_pace(pace_answered_at, now_hours)
    return elapsed is not None and elapsed >= HEALTH_OPENS_AFTER_HOURS


def hours_until_health(answers: dict[str, Any], pace_answered_at: float | None,
                       now_hours: float | None) -> float | None:
    """Hours left before it opens, or None when there is nothing to wait
    for — either it is open already, or no pace has been set so the wait
    has not started."""
    if health_open(answers, pace_answered_at, now_hours):
        return None
    if not has_pace(answers):
        return None
    elapsed = hours_since_pace(pace_answered_at, now_hours)
    if elapsed is None:
        return None
    return max(HEALTH_OPENS_AFTER_HOURS - elapsed, 0.0)


def visible_keys(answers: dict[str, Any], pace_answered_at: float | None,
                 now_hours: float | None) -> list[str]:
    """The keys the screen should show right now, in order."""
    keys = [PACE]
    if has_pace(answers):
        keys.extend(FOLLOWS_PACE)
    if health_open(answers, pace_answered_at, now_hours):
        keys.append(HEALTH)
    return keys


def state(answers: dict[str, Any], pace_answered_at: float | None,
          now_hours: float | None) -> dict[str, Any]:
    """Everything the screen needs, in one call."""
    waiting = hours_until_health(answers, pace_answered_at, now_hours)
    return {
        "has_pace": has_pace(answers),
        "follows_pace": list(FOLLOWS_PACE),
        "health_open": health_open(answers, pace_answered_at, now_hours),
        "hours_until_health": waiting,
        "health_opens_after_hours": HEALTH_OPENS_AFTER_HOURS,
        "visible": visible_keys(answers, pace_answered_at, now_hours),
    }
