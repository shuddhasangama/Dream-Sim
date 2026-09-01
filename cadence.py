"""Dating-stage weekly cadence (docs/dating-stage-spec.md §1, §2).

Supersedes this project's earlier simplified stand-in (a same-day Mon/Tue/
Wed multi-review model with no persisted state) now that the spec is
authoritative for Dating-stage mechanics. Built deterministically on top of
matching.py's fits_filters()/mutual_open()/determine_match_count() and
clock.py's SimulationClock — no LLM, no hidden state, pure functions
(docs/CLAUDE.md: everything except Guru narration stays deterministic).

The week (§1's exact timeline, see clock.py's named checkpoints):
    Mon 12:00   Match 1 revealed, ~22hr review window opens.
    Tue 12:00   Match 1 window closes. Match 2 revealed.
    Wed 12:00   Match 2 window closes. Match 3 revealed.
    Wed evening Match 3 window closes. Availability calendar opens
                (lockin.py/calendar_dating.py, for mutually-interested pairs).
    Thu 12:00   Calendar closes.
    Thu evening Matches go live — date plans generated (dateplan.py).
    Sun night   Date feedback opens (outcomes.py); REACH refreshes.

Generation model: generate_week_matches() picks a user's FULL (up to 3)
match set in one call, meant to be persisted immediately by the caller —
every later request for that (user, week) should read the persisted Match
rows back rather than calling this again, so the set stays fixed at week
start ("everyone sees Match 1 on Monday", §1) and only *visibility*
staggers through the week, gated by comparing the current SimulationClock
to each row's revealed_at (match_status() below does that gating).

A user who never acts within their window is "no response", tracked
separately from an explicit pass (§1: "not a pass" — feeds outcomes.py's
compliance signal, not a dealbreaker-style rejection).
"""

from __future__ import annotations

import random
from typing import Any

from clock import MATCH_CLOSE_BY_SLOT, MATCH_REVEAL_BY_SLOT, SimulationClock, checkpoint
from matching import determine_match_count, eligible_candidates


def generate_week_matches(
    user: dict[str, Any],
    pool: list[dict[str, Any]],
    week: int,
    locked_in_ids: set[str],
    recent_match_ids: set[str],
) -> list[dict[str, Any]]:
    """`user`'s full (up to 3) match set for `week` — see the module
    docstring's "Generation model" for why this is a generate-once, not a
    recompute-every-request, function.

    No parallel dating while locked in (§4): if `user["user_id"]` is in
    `locked_in_ids`, returns [] immediately, before any candidate
    selection happens.

    Sizing is matching.determine_match_count()'s honest count; WHICH
    candidates fill the slots is a random.Random(f"{week}:{user_id}")
    seeded shuffle of eligible_candidates() — same reproducibility
    convention this project's earlier weekly_schedule() used, so
    regenerating for the same (week, user) before anything is persisted
    always picks the same candidates.

    Each returned dict has candidate_id/slot/revealed_at/window_closes_at
    (the latter two as real SimulationClock instances — the caller
    serializes with str() when persisting a Match row)."""
    if user["user_id"] in locked_in_ids:
        return []

    candidates = eligible_candidates(user, pool, locked_in_ids, recent_match_ids)
    count = min(3, len(candidates))
    rng = random.Random(f"{week}:{user['user_id']}")
    rng.shuffle(candidates)
    chosen = candidates[:count]

    return [
        {
            "candidate_id": candidate["user_id"],
            "slot": slot,
            "revealed_at": checkpoint(week, MATCH_REVEAL_BY_SLOT[slot]),
            "window_closes_at": checkpoint(week, MATCH_CLOSE_BY_SLOT[slot]),
        }
        for slot, candidate in enumerate(chosen, start=1)
    ]


def match_status(match: dict[str, Any], clock: SimulationClock) -> str:
    """Where one persisted Match row stands right now:
        'not_yet_revealed' — clock is before revealed_at.
        'open'              — revealed, window still open, no action taken.
        'acted'             — user already recorded interest/pass.
        'no_response'       — window closed with no action (§1: NOT a pass
                               — a distinct, honest state that feeds
                               outcomes.py's compliance signal).
        'closed'            — window closed and the user did act (acted
                               takes priority over closed while a caller
                               only cares about "did they decide").
    `match` needs revealed_at/window_closes_at as SimulationClock instances
    (parse stored strings with SimulationClock.parse() first) and an
    `action` key ('interest' | 'pass' | 'none', matching the Match table's
    own default)."""
    if clock < match["revealed_at"]:
        return "not_yet_revealed"
    acted = match.get("action", "none") != "none"
    if clock < match["window_closes_at"]:
        return "acted" if acted else "open"
    return "acted" if acted else "no_response"


def no_response_matches(matches: list[dict[str, Any]], clock: SimulationClock) -> list[dict[str, Any]]:
    """Every match row whose window closed with no action taken — the
    honest "no response" signal §1 asks be tracked separately from a pass."""
    return [m for m in matches if match_status(m, clock) == "no_response"]
