"""Walkthrough scaffolding (Segment C).

Two things stop the Case 1 journey from being clickable end to end, and
neither is a feature — they are both scaffolding:

  1. THE CLOCK. The week machine gates on a simulated clock that only an
     admin screen can advance. A viewer walking the demo needs Monday to
     become Tuesday from inside the journey, or nothing past the first
     match is reachable.

  2. A PARTNER. Every agreement needs a counter-signature and every date
     needs matching availability. A freshly registered user is alone in a
     pool of strangers whose filters were drawn at random, so the honest
     outcome is usually no match at all — which is correct behaviour and
     useless for a demo. `build_partner_for()` constructs one counterpart
     who is guaranteed to match, in both directions.

Neither is a fudge of the matching rules. The partner is built to SATISFY
matching.fits_filters, not to bypass it — test_demo.py asserts the pairing
passes the real function in both directions, so if the filter logic ever
changes, this fails loudly instead of quietly faking a match.

Demo mode is opt-out, not opt-in: this repo is a simulation harness, and a
walkthrough that needs a hidden flag set is one nobody runs. Set
DEMO_MODE=0 to hide the clock control.
"""

from __future__ import annotations

import os
from typing import Any

import clock as clock_module
import matching
from generate_users import (
    COHABIT_FOCUS,
    ETHNICITIES,
    INCOME_BANDS,
    RESTAURANT_BUDGETS,
)

DEMO_PARTNER_PREFIX = "dp_"


def is_enabled() -> bool:
    return os.environ.get("DEMO_MODE", "1").strip().lower() not in ("0", "false", "no", "off")


# ── 1. the clock ──────────────────────────────────────────────────────────
# clock.SimulationClock already knows how to move; this only names the
# jumps a person walking the journey actually wants.

STEPS = [
    ("hour", "+1 hour", 1),
    ("day", "Next day", 24),
    ("week", "Next week", 24 * 7),
]
STEP_HOURS = {key: hours for key, _, hours in STEPS}


def advance(current: clock_module.SimulationClock, step: str) -> clock_module.SimulationClock:
    """Move the simulated clock forward by one named step. Forward only —
    a demo that can rewind invites questions about what happens to rows
    already written against a later time, and there is no good answer."""
    if step not in STEP_HOURS:
        raise ValueError(f"Unknown step {step!r}; expected one of {sorted(STEP_HOURS)}")
    return current.advance_hours(STEP_HOURS[step])


def clock_view(current: clock_module.SimulationClock) -> dict[str, Any]:
    """What the demo bar shows: where the week is now, and what it is
    waiting for."""
    return {
        "stamp": str(current),
        "week": current.week,
        "day": current.day,
        "hour": current.hour,
        "phase": clock_module.phase(current),
        "steps": [{"key": key, "label": label} for key, label, _ in STEPS],
    }


# ── 2. the scripted partner ───────────────────────────────────────────────


def _mid(bounds: list[int]) -> int:
    lo, hi = bounds
    return int((lo + hi) // 2)


def _opposite(gender: str) -> str:
    return "male" if gender == "female" else "female"


def _city_within_range(user: dict[str, Any]) -> str:
    """A city whose distance from the user's satisfies their own distance
    lever. Their own city is the obvious answer whenever 0 is in range,
    which it usually is; otherwise search for one that fits."""
    lo, hi = user["preferences"]["adjustable"]["distance_km"]
    own = user["city"]
    if lo <= matching.city_distance_km(own, own) <= hi:
        return own
    for city in matching.CITIES if hasattr(matching, "CITIES") else []:
        if lo <= matching.city_distance_km(own, city) <= hi:
            return city
    from generate_users import CITIES as ALL_CITIES

    for city in ALL_CITIES:
        if lo <= matching.city_distance_km(own, city) <= hi:
            return city
    return own


def _diet_for(user: dict[str, Any]) -> str:
    """Satisfy a veg_only dealbreaker if the user has one, otherwise mirror
    their own diet — a partner who eats what you eat is the least
    surprising default."""
    if "veg_only" in user["preferences"]["fixed"]["dealbreakers"]:
        return "Vegetarian"
    return user["stats"].get("diet", "Everything")


def _visions_for(user: dict[str, Any]) -> list[dict[str, Any]]:
    """Mirror the user's own vision, then honour their kids dealbreakers.

    Mirroring is the right default for a walkthrough: the product's whole
    premise is that end goals are matched first, so the demo should show
    two people who actually align rather than two who merely pass filters.
    """
    dealbreakers = user["preferences"]["fixed"]["dealbreakers"]
    mine = {v["key"]: v.get("stance") for v in user["visions"]}

    keys = [k for k in mine if k != "Kids"] or ["Intimacy"]
    if "Intimacy" not in keys:
        keys.append("Intimacy")

    wants_kids = "wants_kids" in dealbreakers or ("Kids" in mine and "no_kids_wanted" not in dealbreakers)
    if wants_kids and "no_kids_wanted" not in dealbreakers:
        keys.append("Kids")

    visions = []
    for key in keys:
        if key == "Intimacy":
            stance = mine.get("Intimacy") or ["Emotional"]
            # Kids requires Physical intimacy — the 2026-08-28 rule.
            if "Kids" in keys and "Physical" not in stance:
                stance = sorted(set(stance) | {"Physical"})
            visions.append({"key": "Intimacy", "stance": sorted(stance)})
        elif key == "Cohabitate":
            visions.append({"key": "Cohabitate", "stance": mine.get("Cohabitate") or [COHABIT_FOCUS[0]]})
        else:
            visions.append({"key": key, "stance": None})
    return visions


def build_partner_for(user: dict[str, Any], partner_id: str) -> dict[str, Any]:
    """A generate_users()-shaped record for one counterpart who is
    guaranteed to pass matching.fits_filters in BOTH directions.

    Built by construction, not by search: every value is taken from the
    middle of the range the user asked for, and the partner's own filters
    are drawn wide enough around the user's actual stats to accept them.
    """
    adj = user["preferences"]["adjustable"]
    u_stats = user["stats"]

    # Start from the user's OWN stats and override only what matching
    # actually reads. Listing the partner's fields explicitly meant every
    # new stat had to be remembered here; mirroring means a field added to
    # generate_users appears on the partner automatically, and the test
    # below asserts exactly that.
    stats = dict(u_stats)
    stats.update({
        # every range lever, answered from the middle of what they asked for
        **{lever: _mid(adj[lever]) for lever in matching.RANGE_LEVERS},
        "diet": _diet_for(user),
        "marital_history": "Never married",
        # nationality/religion chosen to satisfy the user's own filters
        "nationality": adj["nationality"][0],
        "religion": u_stats.get("religion", "Hindu"),
    })
    stats.setdefault("income_band", INCOME_BANDS[1])
    stats.setdefault("budget", RESTAURANT_BUDGETS[1])
    stats.setdefault("ethnicity", ETHNICITIES[0])

    user_age = int(u_stats["age"])
    partner_prefs = {
        "fixed": {"dealbreakers": []},
        "adjustable": {
            # wide enough to accept the user, whatever they entered
            "age": [max(18, user_age - 15), user_age + 15],
            **{
                lever: [max(1, int(u_stats[lever]) - 40), int(u_stats[lever]) + 40]
                for lever in matching.RANGE_LEVERS
                if lever != "age"
            },
            "distance_km": [0, 1600],
            "nationality": ["IN", "NRI", "Any"],
            "religion": ["same", "related", "any"],
        },
    }

    return {
        "user_id": partner_id,
        "city": _city_within_range(user),
        "gender": _opposite(user["gender"]),
        "age_band": user.get("age_band", "28-34"),
        "bgv_status": "verified",
        "stats": stats,
        "visions": _visions_for(user),
        "preferences": partner_prefs,
    }


def partner_id_for(user_id: str) -> str:
    """Deterministic, so re-running the walkthrough reuses one partner
    instead of littering the pool with a new stranger every time."""
    return f"{DEMO_PARTNER_PREFIX}{user_id}"


def is_demo_partner(user_id: str) -> bool:
    return str(user_id).startswith(DEMO_PARTNER_PREFIX)


def verify_pairing(user: dict[str, Any], partner: dict[str, Any]) -> dict[str, bool]:
    """Run the real matching rules over the pair. Used by the tests, and
    worth calling from a health check — if this ever returns False the
    walkthrough is broken and it is better to know at boot."""
    return {
        "a_accepts_b": matching.fits_filters(user, partner),
        "b_accepts_a": matching.fits_filters(partner, user),
        "mutual": matching.mutual_open(user, partner),
    }
