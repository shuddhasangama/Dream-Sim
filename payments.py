"""Historical fee labels and scope metadata (Segment D).

This module does not grant access. Fee gates use billing_service.fee_satisfied,
which accepts only an explicit fee waiver or a verified billing entitlement.

Scope matters more than it looks. A fee is not "paid once, forever" — the
availability fee is per date, so the second date must charge again. Every
entitlement is therefore keyed on (user, purpose, scope_id), and choosing
the right scope_id is the caller's job:

    availability  -> the LockIn id      (one fee per date arranged)
    agreement     -> the DatePlan id    (one fee per agreement signed)
    stage_gate    -> the pair id        (one fee per checkpoint crossed)
    guru          -> the billing period (a subscription, not a one-off)

Pure historical fee and formatting functions; no active route writes Payment rows.
"""

from __future__ import annotations

import uuid
from typing import Any

# ── the fee table ─────────────────────────────────────────────────────────
# Amounts are the mock-up's, in whole rupees. Stored in paise nowhere yet —
# there is no gateway to be precise for. When one arrives, convert here and
# nowhere else.

AVAILABILITY = "availability"
AGREEMENT = "agreement"
STAGE_GATE = "stage_gate"
GURU = "guru"
CANCELLATION = "cancellation"

FEES = {
    AVAILABILITY: {
        "amount_inr": 499,
        "label": "Weekend availability",
        "blurb": "Unlocks the calendar so your weekend slots go to the person you locked in.",
        "recurring": False,
    },
    AGREEMENT: {
        "amount_inr": 1499,
        "label": "Agreement of understanding",
        "blurb": "Drafts the terms for this date and puts them in front of both of you to sign.",
        "recurring": False,
    },
    STAGE_GATE: {
        "amount_inr": 2999,
        "label": "Stage checkpoint",
        "blurb": "The conversation that moves you both to the next stage, and the record of it.",
        "recurring": False,
    },
    GURU: {
        "amount_inr": 4999,
        "label": "Guru",
        "blurb": "The four pillars, the weekly report, and mediation when you want it.",
        "recurring": True,
    },
    # 2026-09-04, user's rule: a free cancellation is an invitation to
    # change your mind at everyone else's expense, and dates are set on
    # Thursday for the weekend. This is a PENALTY, not a service — it is
    # charged after the fact to whoever cancelled inside the 24h window,
    # never as a gate in front of something.
    #
    # THE AMOUNT IS A PLACEHOLDER. 999 sits deliberately between the
    # availability fee and the agreement fee: enough to be felt, less than
    # the cost of the date itself. Set it where you want it.
    CANCELLATION: {
        "amount_inr": 999,
        "label": "Late cancellation",
        "blurb": "Charged when a confirmed date is cancelled inside 24 hours of the slot.",
        "recurring": False,
    },
}
PURPOSES = tuple(FEES)

PAID = "paid"
FAILED = "failed"
PENDING = "pending"
STATUSES = (PENDING, PAID, FAILED)


def fee(purpose: str) -> dict[str, Any]:
    if purpose not in FEES:
        raise ValueError(f"Unknown purpose {purpose!r}; expected one of {PURPOSES}")
    return FEES[purpose]


def amount_label(purpose: str) -> str:
    return f"₹{fee(purpose)['amount_inr']:,}"


def payment_row(
    user_id: str,
    purpose: str,
    scope_id: str,
    created_at: str,
    status: str = PENDING,
) -> dict[str, Any]:
    """The Payment row to persist. `reference` stands in for the gateway's
    own order id — a real integration writes the gateway's value here
    instead of a generated one, and nothing else changes."""
    if status not in STATUSES:
        raise ValueError(f"Unknown status {status!r}; expected one of {STATUSES}")
    return {
        "id": f"{user_id}:{purpose}:{scope_id}",
        "user_id": user_id,
        "purpose": purpose,
        "scope_id": scope_id,
        "amount_inr": fee(purpose)["amount_inr"],
        "status": status,
        "reference": f"sim_{uuid.uuid4().hex[:16]}",
        "created_at": created_at,
    }


def checkout_view(purpose: str, scope_id: str, paid: bool) -> dict[str, Any]:
    """Legacy formatting only. No HTTP route renders this view."""
    f = fee(purpose)
    return {
        "purpose": purpose,
        "scope_id": scope_id,
        "label": f["label"],
        "blurb": f["blurb"],
        "amount": amount_label(purpose),
        "recurring": f["recurring"],
        "period": "per month" if f["recurring"] else "one-off",
        "paid": paid,
        "cta": "Paid ✓" if paid else f"Pay {amount_label(purpose)}",
    }
