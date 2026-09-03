"""Fees and entitlements (Segment D).

The mock-up charges at four points; the deployed app has never charged at
any of them — "payment" appears once, as the word "payment is open" on the
plan page. This module is the entitlement layer the roadmap asks for: ONE
place that answers "is this paid for", so every gated screen reads the
same source and none of them invents its own rule.

No gateway. `simulate_gateway_callback()` is a stub sitting exactly where
Razorpay's webhook will land. Wiring a real gateway replaces that one
function plus the order-creation call; the fee table, the scoping rules and
every caller stay as they are.

Scope matters more than it looks. A fee is not "paid once, forever" — the
availability fee is per date, so the second date must charge again. Every
entitlement is therefore keyed on (user, purpose, scope_id), and choosing
the right scope_id is the caller's job:

    availability  -> the LockIn id      (one fee per date arranged)
    agreement     -> the DatePlan id    (one fee per agreement signed)
    stage_gate    -> the pair id        (one fee per checkpoint crossed)
    guru          -> the billing period (a subscription, not a one-off)

Pure functions; the caller persists Payment rows.
"""

from __future__ import annotations

import os
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
}
PURPOSES = tuple(FEES)

PAID = "paid"
FAILED = "failed"
PENDING = "pending"
STATUSES = (PENDING, PAID, FAILED)


def is_enabled() -> bool:
    """Whether fees are enforced at all.

    Default ON, because a walkthrough that skips the money is not the
    product's walkthrough. Set PAYMENTS_ENABLED=0 to run the older
    play-test flow with no paywall in the way — useful when you are
    testing the journey rules rather than demoing the funnel.
    """
    return os.environ.get("PAYMENTS_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


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


def has_paid(rows: list[dict[str, Any]], user_id: str, purpose: str, scope_id: str) -> bool:
    """The entitlement question, answered in one place.

    When fees are disabled everything is entitled — the gate disappears
    rather than silently letting unpaid rows through, which would be the
    same behaviour with a worse audit trail.
    """
    if not is_enabled():
        return True
    return any(
        r["user_id"] == user_id
        and r["purpose"] == purpose
        and str(r["scope_id"]) == str(scope_id)
        and r["status"] == PAID
        for r in rows
    )


def simulate_gateway_callback(row: dict[str, Any], succeeded: bool = True) -> dict[str, Any]:
    """Stub for the gateway webhook. THIS IS THE ONE FUNCTION A REAL
    INTEGRATION REPLACES.

    A real webhook must also verify the signature and be idempotent — the
    same callback can arrive twice, and charging twice for one date is the
    failure mode people remember. Keying Payment on
    (user, purpose, scope_id) already makes the write idempotent.
    """
    return {**row, "status": PAID if succeeded else FAILED}


def checkout_view(purpose: str, scope_id: str, paid: bool) -> dict[str, Any]:
    """What the payment screen renders. Being explicit that no money moves
    is a product decision, not a disclaimer: anyone walking this demo
    should be able to see that the gateway is not wired in."""
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
