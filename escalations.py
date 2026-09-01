"""Progressive disclosure during Dating (docs/relationship-stage-spec.md
Part A) — contact exchange, consequence-free to decline and gated behind
the Week-2 unlock. Pure functions: the caller persists whatever's
returned.

(§A3's original "invite home" flow used to live in this module too —
propose_home_invite()/respond_to_home_invite()/etc. It was rebuilt as its
own module, invite_home.py, on 2026-08-28 per
docs/intimacy-expectations-spec.md Part C's richer expectation-disclosure
model; see that module for the current invite-home flow.)

`pair_id` on every function/table here is a `LockIn.id`, not a
`Couple.id` — these escalations fire while a pair is still in Dating (a
locked-in pair going through repeat date cycles via outcomes.py's "keep
dating" loop), not after Relationship entry. A Couple record doesn't
exist yet at this point, the same invariant every other Dating-stage
table in this project already relies on.

Guardrails enforced by this module's own design (Part F):
    - Declining/ignoring a ContactRequest has ZERO consequence — no
      rating, no flag, no visibility to the requester as a rejection.
      Enforced structurally: this module never imports outcomes.py (no
      path to a ComplianceEvent exists from here — see
      test_escalations.py's own import-boundary assertion, same pattern
      as guru_dating.py's), and contact_status_for_requester() collapses
      "declined"/"ignored" into the same neutral phrase a "still
      pending" request would show.
    - Guru never nudges — this module has no narrative/suggestion
      functions at all, only state transitions.
    - Rate-limited — one ContactRequest per channel per week. Checked
      here, not just in the UI, by raising ValueError if the caller
      ignores the limit.
"""

from __future__ import annotations

from typing import Any

# §A1: contact exchange unlocks once a pair has completed this many full
# date-feedback cycles — not before. (Invite-home's own unlock check now
# lives in invite_home.py, but shares this same threshold conceptually.)
WEEK_2_DATES_REQUIRED = 2

CONTACT_CHANNELS = ("phone", "whatsapp", "instagram", "linkedin")


def unlocks_available(dates_completed: int) -> bool:
    """§A1's unlock ladder: contact exchange unlocks once `dates_completed`
    (a LockIn's own counter — see
    lockin.increment_dates_completed()) reaches WEEK_2_DATES_REQUIRED.
    That counter only ever advances once both partners' feedback for a
    date is in, so this single check already covers the spec's full
    "completed_dates >= 2 and feedback_complete_both" condition."""
    return dates_completed >= WEEK_2_DATES_REQUIRED


# ── Contact exchange (§A2) ──────────────────────────────────────────────


def request_contact(
    pair_id: str,
    requester_id: str,
    channel: str,
    week: int,
    requested_at: str,
    existing_requests: list[dict[str, Any]],
) -> dict[str, Any]:
    """The ContactRequest row to persist for a new request.

    `existing_requests` is every prior ContactRequest for this pair+
    channel the caller already has (DB-free, like everything else in
    this project's business-logic modules) — used to enforce "one
    request per channel per week" (§A2): raises ValueError if one
    already exists for this exact (channel, week). Doesn't check
    `unlocks_available()` itself — that's a separate, one-line caller
    check, same split of responsibility as cadence.py/matching.py."""
    if channel not in CONTACT_CHANNELS:
        raise ValueError(f"channel must be one of {CONTACT_CHANNELS}, got {channel!r}")
    if any(r["channel"] == channel and r["week"] == week for r in existing_requests):
        raise ValueError(f"a {channel} request already exists for week {week} — one per channel per week")
    return {
        "pair_id": pair_id,
        "requester_id": requester_id,
        "channel": channel,
        "week": week,
        "status": "pending",
        "requested_at": requested_at,
        "responded_at": None,
    }


def respond_to_contact_request(request: dict[str, Any], response: str, responded_at: str) -> dict[str, Any]:
    """`response` is 'accepted' | 'declined' | 'ignored' — any of the
    three, returned as a plain status update. Declining/ignoring changes
    nothing beyond this row: no compliance event, no flag, nothing else
    to call (§A2/Part F's zero-consequence rule)."""
    if response not in ("accepted", "declined", "ignored"):
        raise ValueError(f"response must be accepted/declined/ignored, got {response!r}")
    return {**request, "status": response, "responded_at": responded_at}


def contact_status_for_requester(request: dict[str, Any]) -> str:
    """What the REQUESTER is shown — collapses 'declined'/'ignored'/
    'pending' into the same neutral phrase (§A2: "no visibility to the
    other party beyond 'not shared yet'"). Only 'accepted' looks any
    different, since sharing is the one outcome worth surfacing."""
    return "shared" if request["status"] == "accepted" else "not shared yet"
