"""Mutual lock-in (docs/dating-stage-spec.md §4) — the pivotal Dating-stage
event. Pure functions: the caller persists whatever's returned and does the
actual clearing/updating of Match/LockIn rows.

Guardrails enforced by this module's design (§4, §12):
    - Only MUTUAL interest triggers a lock-in — one-sided interest never
      does. This module doesn't re-derive "mutual" itself (that's the
      caller's job, checking both sides' Match.action against each other);
      on_mutual_interest() is what happens once mutuality is established.
    - Once locked in, both users' remaining match slots are cleared for
      the week — candidates_to_clear() below.
    - REACH sunsets for both locked-in users — asserted in app.py's
      reach_locked(), which this module has no dependency on (kept
      standalone/testable), see that function's docstring for the tie-in.
    - No parallel dating while locked in — enforced in cadence.py's
      generate_week_matches() via its locked_in_ids parameter, which the
      caller builds from LockIn rows with status='active'.
"""

from __future__ import annotations

from typing import Any

from clock import SimulationClock


def on_mutual_interest(user_a_id: str, user_b_id: str, week: int, created_at: SimulationClock) -> dict[str, Any]:
    """The LockIn row to persist for a newly-mutual pair."""
    return {
        "user_a": user_a_id,
        "user_b": user_b_id,
        "week": week,
        "created_at": str(created_at),
        "status": "active",
    }


def candidates_to_clear(
    user_a_matches: list[dict[str, Any]],
    user_b_matches: list[dict[str, Any]],
    locked_a_id: str,
    locked_b_id: str,
) -> dict[str, list[str]]:
    """Which OTHER match candidate ids get cleared for each user this week
    once they lock in together — every match that isn't the pair they just
    locked with (§4: "clear all other candidates for BOTH users this week
    — short-circuits the week"). Returns {"user_a": [...], "user_b": [...]}
    of candidate_ids — the caller matches those back to actual Match rows
    to update/delete."""
    return {
        "user_a": [m["candidate_id"] for m in user_a_matches if m["candidate_id"] != locked_b_id],
        "user_b": [m["candidate_id"] for m in user_b_matches if m["candidate_id"] != locked_a_id],
    }


def release(lockin: dict[str, Any], reason: str) -> dict[str, Any]:
    """The date never happened (cancelled, no-show, no calendar overlap
    and the pair chose to return to the pool, ...) — releases this LockIn
    so both users are eligible again at the next week boundary, with the
    reason recorded (§4: "with the reason recorded"). Returns an updated
    copy; doesn't mutate the input."""
    return {**lockin, "status": "released", "release_reason": reason}


def complete(lockin: dict[str, Any]) -> dict[str, Any]:
    """The date happened and ran its course to a recorded outcome (either
    partner's decision) — marks the LockIn no longer active. Distinct from
    release(), which is specifically the "never made it to a date" path.
    Returns an updated copy; doesn't mutate the input."""
    return {**lockin, "status": "completed"}


def is_locked_in(user_id: str, active_lockins: list[dict[str, Any]]) -> bool:
    """True if `user_id` appears as either side of any status='active'
    LockIn in `active_lockins` — the caller's one-line check for "is this
    user currently locked in" before, e.g., letting them act on a
    different match or open REACH."""
    return any(user_id in (l["user_a"], l["user_b"]) for l in active_lockins)


def increment_dates_completed(lockin: dict[str, Any]) -> dict[str, Any]:
    """Call once a date's feedback fully resolves — i.e. once
    outcomes.resolution() stops returning 'pending' for it, meaning BOTH
    partners have given a decision. Feeds
    escalations.unlocks_available()'s "completed_dates >= 2" check
    (docs/relationship-stage-spec.md §A1) with a single counter that can
    only ever advance once both halves of that condition are true.
    Returns an updated copy; doesn't mutate the input."""
    return {**lockin, "dates_completed": lockin.get("dates_completed", 0) + 1}
