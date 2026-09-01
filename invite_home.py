"""Invite home, with honest expectation disclosure
(docs/intimacy-expectations-spec.md Part C) — supersedes the simpler
"invite home" flow escalations.py originally shipped for
docs/relationship-stage-spec.md §A3 (that flow predates this richer
spec; its functions were removed from escalations.py on 2026-08-28 when
this module replaced them). Pure functions: the caller persists
whatever's returned.

`pair_id` is a LockIn.id, same invariant as escalations.py/stage_gate.py
— this unlocks after the Week-2 lock-in + feedback, still within Dating.

The governing distinction (the spec's own framing): expectation can be
disclosed in advance; consent cannot. Nothing in this module ever
represents, implies, or records consent to intimacy — see C3's
IMMUTABLE_ACKNOWLEDGEMENT_TEXT, which every acknowledgement stores
verbatim precisely so that stays true no matter what else changes.

Guardrails enforced by this module's design (Part F):
    - No advance consent, ever — acknowledge() has no parameter that
      could substitute for or edit IMMUTABLE_ACKNOWLEDGEMENT_TEXT.
    - Revocation is always free — revoke() works from any non-terminal
      status, records who revoked but never a reason or a fault.
    - Declining/ignoring has zero consequence: this module never imports
      outcomes.py (see test_invite_home.py's own import-boundary check),
      and status_for_requester() collapses declined/ignored into the
      same neutral phrase a still-pending invite would show.
    - No address stored — proposed_datetime is the only location/time
      field this module's rows ever carry.
"""

from __future__ import annotations

from typing import Any

EXPECTATION_FLAGS = ("social_only", "open_ended", "intimacy_expected")

# C2 — shown to the recipient as this exact copy, before they respond.
EXPECTATION_FLAG_COPY = {
    "social_only": "Time together at home — no expectation of physical intimacy",
    "open_ended": "Time together at home — where things go is open, and we'll each decide in the moment",
    "intimacy_expected": "This invitation includes an expectation of physical intimacy",
}

# §A3 (docs/relationship-stage-spec.md) — reused verbatim; this spec
# doesn't redefine the rules of engagement, only adds the expectation
# flag and richer acknowledgement on top of them.
RULES_OF_ENGAGEMENT = [
    "Either person may change their mind at any time, before or during — no explanation owed",
    "The stated physical-boundary preference carries over and still applies",
    "No recording or photography without consent",
    "Either may leave at any point",
    "Share the plan with a trusted contact outside the platform",
    "In-app reporting and an emergency check-in remain available throughout",
]

ACKNOWLEDGEMENT_VERSION = "v1"

# C3 — mandatory immutable text, verbatim, prominent, not editable or
# shortenable. Every acknowledgement stores this exact string plus
# ACKNOWLEDGEMENT_VERSION, so it's always clear precisely what was shown
# — see test_invite_home.py's ImmutableTextTests for the tamper-proofing
# this buys: acknowledge() takes no text parameter at all.
IMMUTABLE_ACKNOWLEDGEMENT_TEXT = (
    "This records a planned visit and the expectations that were disclosed before it. "
    "It is not consent to physical intimacy, and it cannot be. Consent is given in the "
    "moment, for a specific thing, by a person who is free to change their mind — and it "
    "can be withdrawn at any time, by either person, no matter what was said or agreed "
    "before. Changing your mind is not a broken promise. It is your right, always. "
    "Either person may cancel this visit, or end it once it has begun, without explanation."
)

# C4 — shown to both parties before either acknowledges, only when
# expectation_flag == 'intimacy_expected'.
INTIMACY_EXPECTED_GUIDANCE = [
    "Disclosing an expectation is honest and welcome. It is not, and can never be, agreement in advance — the other person decides in the moment, and so do you",
    "If either of you is unsure, this is the moment to say so. Postponing costs nothing",
    "Talk about protection and sexual health beforehand, not after",
    "If there is any ambiguity on the night, stop. Ambiguity is a reason not to proceed",
    "Alcohol changes the picture; a person who is heavily intoxicated cannot meaningfully agree",
    "Either of you may leave, or ask the other to leave, at any point",
]

_TERMINAL_STATUSES = ("declined", "ignored", "revoked", "completed")


def propose_invite(
    pair_id: str, requester_id: str, proposed_datetime: str, expectation_flag: str, existing_invites: list[dict[str, Any]]
) -> dict[str, Any]:
    """C1/C5 step 1: propose a visit and honestly state what it includes.
    Raises if `existing_invites` (every prior HomeInvite for this pair)
    already has one in 'pending' or 'accepted' status — one at a time,
    same rate-limit convention as escalations.py's."""
    if expectation_flag not in EXPECTATION_FLAGS:
        raise ValueError(f"expectation_flag must be one of {EXPECTATION_FLAGS}, got {expectation_flag!r}")
    if any(inv["status"] in ("pending", "accepted") for inv in existing_invites):
        raise ValueError("a pending or accepted invite already exists for this pair — one at a time")
    return {
        "pair_id": pair_id,
        "requester_id": requester_id,
        "proposed_datetime": proposed_datetime,
        "expectation_flag": expectation_flag,
        "flag_seen_by_recipient_at": None,
        "status": "pending",
        "guidance_shown_a": False,
        "guidance_shown_b": False,
        "ack_signed_a": False,
        "ack_signed_b": False,
        "face_verified_a": False,
        "face_verified_b": False,
        "trusted_contact_notified_a": False,
        "trusted_contact_notified_b": False,
        "revoked_by": None,
        "revoked_at": None,
        "acknowledgement_version": None,
    }


def mark_flag_seen(invite: dict[str, Any], seen_at: str) -> dict[str, Any]:
    """C2: "The recipient sees the flag before responding, always,
    prominently." Call before respond_to_invite() — that function
    refuses to proceed otherwise."""
    return {**invite, "flag_seen_by_recipient_at": seen_at}


def respond_to_invite(invite: dict[str, Any], response: str) -> dict[str, Any]:
    """C5 step 3: accept | decline | ignore, "all three free of
    consequence." Requires the recipient to have already seen the
    expectation flag (mark_flag_seen()) — C2's ordering enforced in
    code, not just by the UI showing things in the right sequence."""
    if invite["flag_seen_by_recipient_at"] is None:
        raise ValueError("the recipient must see the expectation flag before responding")
    if response not in ("accepted", "declined", "ignored"):
        raise ValueError(f"response must be accepted/declined/ignored, got {response!r}")
    if invite["status"] != "pending":
        raise ValueError(f"can only respond to a pending invite, this one is {invite['status']!r}")
    return {**invite, "status": response}


def show_guidance(invite: dict[str, Any], party: str) -> dict[str, Any]:
    """C4: shown to both parties before either acknowledges, only when
    expectation_flag == 'intimacy_expected'. Raises for any other flag —
    callers shouldn't need this step there, so a stray call signals a
    caller-side bug rather than real user input."""
    if invite["expectation_flag"] != "intimacy_expected":
        raise ValueError("guidance only applies to an 'intimacy_expected' invite")
    if party not in ("a", "b"):
        raise ValueError(f"party must be 'a' or 'b', got {party!r}")
    return {**invite, f"guidance_shown_{party}": True}


def acknowledge(invite: dict[str, Any], party: str, face_verified: bool) -> dict[str, Any]:
    """C3/C5 step 4: both partners see IMMUTABLE_ACKNOWLEDGEMENT_TEXT and
    acknowledge separately, face-verified — this function takes no text
    parameter, so there is no way to call it with anything other than
    that exact, unmodifiable copy. Refuses if expectation_flag is
    'intimacy_expected' and this party's C4 guidance hasn't been shown
    yet (C5 step 5: guidance precedes acknowledgement for that flag,
    never skippable)."""
    if invite["status"] != "accepted":
        raise ValueError(f"can only acknowledge an accepted invite, this one is {invite['status']!r}")
    if party not in ("a", "b"):
        raise ValueError(f"party must be 'a' or 'b', got {party!r}")
    if invite["expectation_flag"] == "intimacy_expected" and not invite.get(f"guidance_shown_{party}"):
        raise ValueError("C4 guidance must be shown before acknowledging an intimacy-expected invite")
    return {
        **invite,
        f"ack_signed_{party}": True,
        f"face_verified_{party}": bool(face_verified),
        "acknowledgement_version": ACKNOWLEDGEMENT_VERSION,
    }


def both_acknowledged(invite: dict[str, Any]) -> bool:
    return bool(invite["ack_signed_a"] and invite["ack_signed_b"])


def notify_trusted_contact(invite: dict[str, Any], party: str) -> dict[str, Any]:
    """C5 step 6, optional: either shares the plan with a trusted
    contact outside the platform."""
    if party not in ("a", "b"):
        raise ValueError(f"party must be 'a' or 'b', got {party!r}")
    return {**invite, f"trusted_contact_notified_{party}": True}


def revoke(invite: dict[str, Any], by_user_id: str, revoked_at: str) -> dict[str, Any]:
    """C5 step 7 / Part F: "Revocation is always free — before or
    during, by either party, no explanation, no penalty, no fault
    recorded." Works from any non-terminal status, including after both
    have acknowledged (the spec explicitly allows revoking "once it has
    begun"). `by_user_id` is recorded only for audit convenience — never
    interpreted anywhere in this module as fault."""
    if invite["status"] in _TERMINAL_STATUSES:
        raise ValueError(f"cannot revoke an invite that is already {invite['status']!r}")
    return {**invite, "status": "revoked", "revoked_by": by_user_id, "revoked_at": revoked_at}


def status_for_requester(invite: dict[str, Any]) -> str:
    """Same neutral-collapse pattern as escalations.py's own
    *_status_for_requester() functions — declined/ignored never surfaced
    as a rejection. 'revoked' is shown as-is: the spec frames revocation
    as blameless, not a rejection, so it isn't hidden behind the same
    phrase."""
    if invite["status"] in ("declined", "ignored"):
        return "not accepted yet"
    return invite["status"]
