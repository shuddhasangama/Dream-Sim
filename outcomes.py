"""Post-date outcomes (docs/dating-stage-spec.md §9) — what happens once
Sunday night's feedback window opens.

Each partner picks one of three decisions (2026-08-28, user's explicit
rule — a 3-way split of what used to be a plain continue/pass):
    1. Accept — continue dating   ('continue': repeat the date cycle with
                                    the SAME LockIn — no stage change)
    2. Reject — back to REACH     ('pass': release the LockIn, back to
                                    the pool, REACH opens up again)
    3. Accept — go to relationship ('relationship': Dating->Relationship,
                                    but ONLY when BOTH partners pick this
                                    exact value — journey.advance_stage()'s
                                    own mutual opt-in rule still applies;
                                    one 'relationship' + one 'continue'
                                    is treated as "keep dating", not
                                    forced into a relationship one side
                                    didn't actually choose)
    Ghosting (no response)         -> 'ghosted', flagged after the closure
                                       window; counts toward compliance
    Safety incident reported       -> Routed to trust & safety; both flagged
    Fake date claim                 -> Flagged for review

Compliance rating (§9): each partner rates conduct/plan adherence; a
pattern of low ratings / verified misconduct / plan violations ->
warning -> temporary suspension -> permanent removal, independent of any
single match's romantic outcome. Late cancellations and no-shows feed the
same signal.

Pure functions: the caller (app.py) persists DateOutcome/ComplianceEvent
rows and calls journey.advance_stage()/lockin.release()/lockin.complete()
— or, for "keep dating", clears the completed DatePlan/Signature rows so
the pair can go through the calendar again — based on what's returned
here.
"""

from __future__ import annotations

from typing import Any

_CONTINUE = "continue"
_RELATIONSHIP = "relationship"
_PASS = "pass"
_GHOSTED = "ghosted"

_COMPLIANCE_EVENT_TYPES = {"rating", "no_show", "late_cancel", "report", "violation"}


def record_outcome(
    dateplan_id: str,
    happened: bool,
    a_decision: str | None,
    b_decision: str | None,
    a_reason: str | None = None,
    b_reason: str | None = None,
    a_green_flags: list[str] | None = None,
    a_red_flags: list[str] | None = None,
    b_green_flags: list[str] | None = None,
    b_red_flags: list[str] | None = None,
    together_photo: bool = False,
    bill_photo: bool = False,
) -> dict[str, Any]:
    """The DateOutcome row to persist. `a_decision`/`b_decision` are each
    'continue' | 'relationship' | 'pass' | 'ghosted' | None (None =
    feedback window hasn't closed / this partner hasn't acted yet).
    `*_green_flags`/`*_red_flags` are each partner's guru_dating.
    capture_flags() picks — collected separately, before the decision
    (app.py's job; this just gives them a default empty-list shape).
    together_photo/bill_photo default False — consent-gated, never
    mandatory (§9/§12: "default off"), and never enter any scoring or
    inference either way."""
    return {
        "dateplan_id": dateplan_id,
        "happened": happened,
        "together_photo": together_photo,
        "bill_photo": bill_photo,
        "a_green_flags": a_green_flags or [],
        "a_red_flags": a_red_flags or [],
        "b_green_flags": b_green_flags or [],
        "b_red_flags": b_red_flags or [],
        "a_decision": a_decision,
        "b_decision": b_decision,
        "a_reason": a_reason,
        "b_reason": b_reason,
    }


def resolution(outcome: dict[str, Any]) -> str:
    """Which branch of the decision table `outcome` falls into:
    'both_relationship' | 'keep_dating' | 'rejected' | 'ghosted' | 'pending'
    (either decision still None). Doesn't trigger anything itself —
    apply_resolution() below turns this into caller actions.

    'rejected' fires the moment EITHER side picks 'pass', regardless of
    the other's answer — one real "no" is enough to end it, same as the
    old both_passed/one_passed split collapsed into a single outcome
    (the two never needed different consequences)."""
    a, b = outcome["a_decision"], outcome["b_decision"]
    if a is None or b is None:
        return "pending"
    if a == _GHOSTED or b == _GHOSTED:
        return "ghosted"
    if a == _PASS or b == _PASS:
        return "rejected"
    if a == _RELATIONSHIP and b == _RELATIONSHIP:
        return "both_relationship"
    return "keep_dating"  # both accepted in some form, but not both 'relationship'


_RELEASE_REASONS = {"rejected": "one partner passed", "ghosted": "no response by close"}


def apply_resolution(outcome: dict[str, Any]) -> dict[str, Any]:
    """What the caller should DO for `outcome`'s resolution:
        {"resolution": ..., "advance_to_relationship": bool,
         "release_lockin": bool, "continue_dating": bool,
         "release_reason": str | None}

    'both_relationship' is the ONLY path that ever calls for advancing to
    Relationship — this function doesn't call journey.advance_stage()
    itself (that needs a live DB connection and the mutual-opt-in re-check
    it already performs; both are app.py's job), it just tells the caller
    to. 'keep_dating' tells the caller to clear this date's
    DatePlan/Signature rows and let the SAME LockIn go through the
    calendar again — no journey-stage change, no release. Every other
    resolved outcome tells the caller to release the LockIn
    (lockin.release()) with a recorded reason so the pair returns to the
    pool at the next week boundary (§4/§9); 'pending' does none of the
    above, since the feedback window is still open."""
    res = resolution(outcome)
    if res == "both_relationship":
        return {"resolution": res, "advance_to_relationship": True, "release_lockin": False, "continue_dating": False, "release_reason": None}
    if res == "keep_dating":
        return {"resolution": res, "advance_to_relationship": False, "release_lockin": False, "continue_dating": True, "release_reason": None}
    if res == "pending":
        return {"resolution": res, "advance_to_relationship": False, "release_lockin": False, "continue_dating": False, "release_reason": None}
    return {
        "resolution": res,
        "advance_to_relationship": False,
        "release_lockin": True,
        "continue_dating": False,
        "release_reason": _RELEASE_REASONS[res],
    }


def record_compliance_event(
    user_id: str, event_type: str, week: int, value: str | None = None, notes: str | None = None
) -> dict[str, Any]:
    """The ComplianceEvent row to persist. `event_type` must be one of the
    schema's CHECK values (rating|no_show|late_cancel|report|violation)."""
    if event_type not in _COMPLIANCE_EVENT_TYPES:
        raise ValueError(f"event_type must be one of {sorted(_COMPLIANCE_EVENT_TYPES)}, got {event_type!r}")
    return {"user_id": user_id, "type": event_type, "value": value, "week": week, "notes": notes}


# Cumulative strike count -> status, checked from the top down so the
# highest threshold reached wins. Doesn't grade severity by event type —
# the spec grades by PATTERN ("pattern of low ratings / verified
# misconduct / plan violations"), not a type-specific weighting scheme it
# never specifies.
_ESCALATION_THRESHOLDS = [(10, "removed"), (6, "suspended"), (3, "warning")]

_LOW_RATING_CEILING = 2  # a rating value <= this counts as a strike


def compliance_status(events: list[dict[str, Any]]) -> str:
    """'ok' | 'warning' | 'suspended' | 'removed' — a pattern-based
    escalation over one user's ComplianceEvent rows. Every non-rating
    event (no_show/late_cancel/report/violation) is a strike; a 'rating'
    event only counts if its value is <= _LOW_RATING_CEILING (a good
    rating isn't a strike) — the caller is responsible for only ever
    passing in events it considers valid (e.g. a 'report' only after
    trust & safety review), this function just counts what it's given."""
    strikes = 0
    for e in events:
        if e["type"] == "rating":
            try:
                is_low = float(e.get("value") or 0) <= _LOW_RATING_CEILING
            except (TypeError, ValueError):
                is_low = False
            strikes += 1 if is_low else 0
        else:
            strikes += 1

    for threshold, status in _ESCALATION_THRESHOLDS:
        if strikes >= threshold:
            return status
    return "ok"
