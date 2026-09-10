"""Confirming an email or phone actually belongs to the person, for
people who sign up from today onward.

2026-09-10, user's rule: "For the existing/simulated users can we leave
the email/phone verification for now. Can we do this as a process for the
new users signup."

So the rule has two halves, and the second one is the load-bearing one.

**Who it applies to.** A new sign-up, and nobody else. The two hundred
simulated users have no Account row at all, and the handful of real
accounts written before today have one with `verification_required = 0`.
Both read as grandfathered, which means turning this on changes nothing
for anyone already in the database — the column is additive and its
default is the old behaviour. That is the whole trick, and it is the same
one `reconcile_columns()` uses: never make an existing row wrong.

**What it costs you not to do it.** Not the whole product. An unverified
new account can finish signing up, look around and use REACH — being made
to prove your phone before you have seen anything is how a sign-up funnel
dies. What it cannot do is **lock in**: the step where two people commit
to meeting, money changes hands and an agreement gets signed. An
unreachable contact is exactly the thing that matters at that point and
nowhere earlier.

**What is honest about it today.** Nothing is sent. There is no email or
SMS channel in this product yet (build board block NT, not started), so
the code is shown on screen and labelled as such. A screen that claims to
have sent an SMS it did not send is worse than one that says it cannot
yet — and when the channel does exist, `deliver()` is the only function
that changes.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

CODE_LENGTH = 6
CODE_TTL_MINUTES = 15
MAX_ATTEMPTS = 5

# Resending should not be free — an unlimited resend button is an SMS bill
# and a way to spam a stranger's phone.
RESEND_COOLDOWN_SECONDS = 60

CHANNELS = ("email", "phone")

# Set once the product can actually send. Until then the code is shown on
# screen, and every piece of copy says so.
CAN_DELIVER = os.environ.get("VERIFICATION_DELIVERY", "").lower() in ("1", "true", "on")


def _pepper() -> bytes:
    """Codes are stored hashed, not in the clear. A six-digit number is
    trivially brute-forced offline, so the hash is peppered with the app
    secret — which is why this reads it at call time rather than import:
    the secret is an environment variable in production."""
    return (os.environ.get("SECRET_KEY") or "dream-sim-local-play-test-only").encode()


def hash_code(code: str) -> str:
    return hmac.new(_pepper(), code.encode(), hashlib.sha256).hexdigest()


def new_code(rng: random.Random | None = None) -> str:
    rng = rng or random.SystemRandom()
    return "".join(str(rng.randrange(10)) for _ in range(CODE_LENGTH))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def challenge_row(user_id: str, channel: str, destination: str,
                  code: str, now: datetime | None = None) -> dict[str, Any]:
    """The row to persist for one code. Note what is NOT in it: the code."""
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}")
    now = now or _now()
    return {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "channel": channel,
        "destination": destination,
        "code_hash": hash_code(code),
        "sent_at": now.isoformat(timespec="seconds"),
        "expires_at": (now + timedelta(minutes=CODE_TTL_MINUTES)).isoformat(timespec="seconds"),
        "attempts": 0,
        "consumed_at": None,
    }


def check(row: dict[str, Any] | None, submitted: str,
          now: datetime | None = None) -> dict[str, Any]:
    """Judge one attempt. Returns {ok, reason, message, attempts_left}.

    Deliberately says "that code is not right" for both a wrong code and
    a used one, and does not say how many digits were correct. The only
    thing it distinguishes out loud is expiry, because that one has a
    different action attached: ask for a new code.
    """
    now = now or _now()
    submitted = (submitted or "").strip()

    if row is None:
        return {"ok": False, "reason": "none",
                "message": "Ask for a code first.", "attempts_left": MAX_ATTEMPTS}

    if row.get("consumed_at"):
        return {"ok": False, "reason": "used",
                "message": "That code has already been used. Ask for a new one.",
                "attempts_left": 0}

    expires = _parse(row.get("expires_at"))
    if expires and now > expires:
        return {"ok": False, "reason": "expired",
                "message": f"That code expired — they last {CODE_TTL_MINUTES} minutes. "
                           "Ask for a new one.",
                "attempts_left": 0}

    attempts = int(row.get("attempts") or 0)
    if attempts >= MAX_ATTEMPTS:
        return {"ok": False, "reason": "locked",
                "message": "Too many tries on this code. Ask for a new one.",
                "attempts_left": 0}

    if hmac.compare_digest(row.get("code_hash") or "", hash_code(submitted)):
        return {"ok": True, "reason": "match", "message": "",
                "attempts_left": MAX_ATTEMPTS - attempts}

    left = MAX_ATTEMPTS - (attempts + 1)
    return {"ok": False, "reason": "wrong",
            "message": "That code is not right." + (f" {left} tries left." if left > 0
                                                    else " Ask for a new one."),
            "attempts_left": max(left, 0)}


def can_resend(row: dict[str, Any] | None, now: datetime | None = None) -> bool:
    if row is None:
        return True
    sent = _parse(row.get("sent_at"))
    if sent is None:
        return True
    return ((now or _now()) - sent).total_seconds() >= RESEND_COOLDOWN_SECONDS


def deliver(channel: str, destination: str, code: str) -> dict[str, Any]:
    """Send the code — or say plainly that it cannot be sent yet.

    The one function to change when block NT lands. Everything above it
    already works; only this is a placeholder, and it does not pretend
    otherwise.
    """
    if CAN_DELIVER:                                    # pragma: no cover
        raise NotImplementedError(
            "No email or SMS channel is wired up yet (build board block NT). "
            "Set VERIFICATION_DELIVERY only once deliver() actually sends.")
    return {
        "sent": False,
        "show_on_screen": code,
        "note": f"We cannot send to your {channel} yet, so here is the code. "
                "This is the simulation, not the finished product.",
    }


# ── who this applies to ───────────────────────────────────────────────────


def is_required(account: dict[str, Any] | None) -> bool:
    """True only for an account created once this existed.

    No Account row means a simulated user — the whole seeded pool — and
    they are not being asked to verify a phone they do not have. An
    Account row written before today has verification_required = 0 by
    column default, which is the same answer for the same reason.
    """
    if not account:
        return False
    return bool(account.get("verification_required"))


def is_satisfied(account: dict[str, Any] | None) -> bool:
    """Whether this account has cleared the bar.

    ONE of the two channels is enough. Someone who signed up with only an
    email cannot verify a phone they never gave, and demanding both would
    be a gate nobody can pass rather than a gate that keeps anyone out.
    """
    if not is_required(account):
        return True
    return bool(account.get("verified_email") or account.get("verified_phone"))


def pending_channels(account: dict[str, Any] | None) -> list[str]:
    """Channels this account gave us that are still unconfirmed."""
    if not account:
        return []
    out = []
    if account.get("email") and not account.get("verified_email"):
        out.append("email")
    if account.get("phone") and not account.get("verified_phone"):
        out.append("phone")
    return out


def status(account: dict[str, Any] | None) -> dict[str, Any]:
    """Everything a screen needs to say where this stands."""
    return {
        "required": is_required(account),
        "satisfied": is_satisfied(account),
        "pending": pending_channels(account),
        "email": (account or {}).get("email"),
        "phone": (account or {}).get("phone"),
        "verified_email": bool((account or {}).get("verified_email")),
        "verified_phone": bool((account or {}).get("verified_phone")),
        "can_deliver": CAN_DELIVER,
    }
