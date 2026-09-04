"""Date plan generation and signing (docs/dating-stage-spec.md §6).

On calendar confirmation, generate the date plan — a Dating-scoped, single-
instance slice of the full playbook structure (agent-2-playbook.pdf), not
the Relationship-stage Playbook table. Auto-fills date/time, meal/venue/
cuisine, bill split, fee, and cancellation terms from a small config dict;
both partners' greeting/dietary/dress selections are folded in so each has
explicitly seen the other's (§6's "selections carried into the plan"
table). Scope is always a single date instance, expiring on completion —
nothing here carries state across dates.

Signing flow (§6):
    1. Plan rendered for review
    2. Acknowledgement checkboxes: code of conduct & courtesies,
       cancellation policy, "this is not a relationship or a contract",
       platform liability
    3. Face verification + digital signature — per partner, independently
    4. Neither party is bound until both have signed
    5. Dual signature -> date confirmed, payment opens

verify_face() is a stub per the spec's explicit instruction not to
implement real biometrics — seeded-random so it's reproducible in tests.
"""

from __future__ import annotations

import random
from typing import Any

DEFAULT_CONFIG = {
    "cancel_notice_hrs": 24,
    "cancel_fee": 0.0,
    "fee": 0.0,
    "budget_estimate": "₹1,500–2,500 for the evening",
}

# The four acknowledgement checkboxes §6 step 2 lists, by name.
ACK_FIELDS = ("ack_conduct", "ack_cancellation", "ack_not_a_relationship", "ack_liability")

# 2026-08-28, user's explicit rule: only two bill-split options — no
# 50/50, no host-pays, no alternate-treats.
BILL_SPLIT_OPTIONS = ("pay-your-own", "one-third-two-thirds")
BILL_SPLIT_LABELS = {"pay-your-own": "Pay your own", "one-third-two-thirds": "1/3 – 2/3 split"}


# ── when a slot actually happens, and what follows it ─────────────────────
# The single definition of what time each meal slot starts. app.py's
# slot_datetime() and the debrief's timing both read it here, because two
# copies of this map is how the calendar and the debrief end up disagreeing
# about when a date was.

MEAL_SLOT_TIMES = {
    "breakfast": (9, 0),
    "lunch": (13, 0),
    "coffee": (17, 0),
    "dinner": (19, 30),
}

# 2026-09-04, user's rule: the debrief opens an hour after the date starts,
# NOT on Sunday night. That is what makes a no-show reportable while the
# evening is still happening, instead of days later.
DEBRIEF_OPENS_AFTER_HOURS = 1


def slot_start(meal_slot: str) -> tuple[int, int]:
    if meal_slot not in MEAL_SLOT_TIMES:
        raise ValueError(f"Unknown meal slot {meal_slot!r}; expected one of {sorted(MEAL_SLOT_TIMES)}")
    return MEAL_SLOT_TIMES[meal_slot]


def debrief_opens_hour(meal_slot: str) -> int:
    """The whole hour at which the debrief opens for this slot.

    Rounded UP, never down: dinner starts at 19:30, so an hour later is
    20:30, and the debrief opens at 21:00. Opening at 20:00 would put the
    "how was it?" screen in front of someone who is still at the table.
    """
    hour, minute = slot_start(meal_slot)
    total_minutes = hour * 60 + minute + DEBRIEF_OPENS_AFTER_HOURS * 60
    return min(23, -(-total_minutes // 60))


# ── cancellation ──────────────────────────────────────────────────────────
# 2026-09-04, user's rule: dates are set on Thursday for the weekend, so a
# free cancellation is an invitation to change your mind at everyone else's
# expense. Inside the notice window it costs something and it is recorded.

CANCELLATION_NOTICE_HOURS = 24


def hours_between(earlier: tuple[int, int], later: tuple[int, int]) -> int:
    """Whole hours between two (day_index, hour) points in the same week.
    Negative if `later` is actually earlier."""
    return (later[0] * 24 + later[1]) - (earlier[0] * 24 + earlier[1])


def cancellation(hours_notice: int, fee_inr: int) -> dict[str, Any]:
    """What cancelling with this much notice costs.

    Outside the window it is free and unrecorded — people's plans change,
    and a policy that punishes honest early notice teaches people to
    no-show instead, which is the outcome this is trying to prevent.
    Inside it, the fee applies and a late_cancel strike is recorded.
    """
    late = hours_notice < CANCELLATION_NOTICE_HOURS
    return {
        "late": late,
        "hours_notice": hours_notice,
        "fee_inr": fee_inr if late else 0,
        "compliance_event": "late_cancel" if late else None,
        "reason": (
            f"Cancelled with {max(hours_notice, 0)}h notice — inside the "
            f"{CANCELLATION_NOTICE_HOURS}h window, so the fee applies."
            if late else
            f"Cancelled with {hours_notice}h notice — outside the "
            f"{CANCELLATION_NOTICE_HOURS}h window, so nothing is charged."
        ),
    }


def verify_face(user_id: str, success_rate: float = 0.95, seed: str | int | None = None) -> bool:
    """Stubbed biometric check — NOT real face verification (the spec is
    explicit: "do not implement real biometrics"). Deterministic given
    `seed` (defaults to `user_id`, so a given user's default-seeded
    attempt is reproducible); pass a distinct seed to simulate a retry
    that isn't stuck repeating the same outcome."""
    rng = random.Random(seed if seed is not None else user_id)
    return rng.random() < success_rate


def generate_plan(
    lockin_id: str,
    confirmed_slot: dict[str, str],
    venue: dict[str, Any],
    datetime_str: str,
    bill_split: str,
    selections_a: dict[str, Any],
    selections_b: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The DatePlan row to persist, per §6.

    `confirmed_slot` is a {"day","meal_slot"} from
    calendar_dating.compute_overlap(); `venue` is
    calendar_dating.suggest_venue()'s result, or a caller-built
    {"venue": None, "cuisine": None} stand-in for "decide together".
    `datetime_str` is the real calendar date/time the caller derived from
    the confirmed slot — this module never touches real dates itself
    (app.py's existing WEEK_ONE_MONDAY epoch owns that, same as
    CalendarEntry elsewhere in this project). `bill_split` must be one of
    BILL_SPLIT_OPTIONS. `selections_a`/`selections_b` are each
    {"greeting", "dietary", "dress"} — the per-partner selections that get
    carried into the plan so each has explicitly seen the other's.

    Cuisine (from `venue`), budget, and bill split are the plan's "rules
    of engagement" — auto-filled here from the confirmed venue and
    `config`/defaults, never something either partner types in by hand,
    so they're already settled by the time the plan is presented for
    signing (2026-08-28, user's explicit rule)."""
    if bill_split not in BILL_SPLIT_OPTIONS:
        raise ValueError(f"bill_split must be one of {BILL_SPLIT_OPTIONS}, got {bill_split!r}")
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    keep = ("greeting", "dietary", "dress")
    return {
        "lockin_id": lockin_id,
        "datetime": datetime_str,
        "meal": confirmed_slot["meal_slot"],
        "venue": venue.get("venue"),
        "cuisine": venue.get("cuisine"),
        "budget_estimate": cfg["budget_estimate"],
        "bill_split": bill_split,
        "fee": cfg["fee"],
        "cancel_notice_hrs": cfg["cancel_notice_hrs"],
        "cancel_fee": cfg["cancel_fee"],
        "status": "pending_signatures",
        "selections_a_json": {k: selections_a.get(k) for k in keep},
        "selections_b_json": {k: selections_b.get(k) for k in keep},
    }


def sign(dateplan_id: str, user_id: str, ack_flags: dict[str, bool], signed_at: str, face_verified: bool) -> dict[str, Any]:
    """The Signature row to persist for one partner's independent sign-off
    (§6 step 3). A partial `ack_flags` (missing or False entries) still
    gets recorded as-is — so the UI can show exactly what's outstanding —
    but is_confirmed()/is_fully_acknowledged() will correctly treat it as
    not-yet-binding."""
    return {
        "dateplan_id": dateplan_id,
        "user_id": user_id,
        "signed_at": signed_at,
        "face_verified": face_verified,
        **{field: bool(ack_flags.get(field, False)) for field in ACK_FIELDS},
    }


def is_fully_acknowledged(signature: dict[str, Any]) -> bool:
    """True if one partner's Signature row has every ack checked AND
    passed face verification."""
    return bool(signature.get("face_verified")) and all(signature.get(f) for f in ACK_FIELDS)


def is_confirmed(signatures: list[dict[str, Any]], user_a_id: str, user_b_id: str) -> bool:
    """§6 step 4: "neither party is bound until both have signed" —
    `signatures` is every Signature row recorded for one DatePlan; both
    partners need a fully-acknowledged, face-verified row."""
    by_user = {s["user_id"]: s for s in signatures}
    return (
        user_a_id in by_user
        and user_b_id in by_user
        and is_fully_acknowledged(by_user[user_a_id])
        and is_fully_acknowledged(by_user[user_b_id])
    )


def payment_open(signatures: list[dict[str, Any]], user_a_id: str, user_b_id: str) -> bool:
    """§5/§6/§12: payment opens ONLY once the date is confirmed by both
    signatures — never before, never on a single partner's say-so."""
    return is_confirmed(signatures, user_a_id, user_b_id)
