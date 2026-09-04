"""Pure matching-service functions for REACH (docs/agent-1-reach.pdf).

REACH's own boundary: "Query the DB, compute counts, or run matching math"
belongs to the matching service, never the LLM. This module IS that
matching service's math — deterministic, no LLM, safe to unit-test.

Functions:
    fits_filters(user_a, user_b)     — does B satisfy every filter A stated?
    mutual_open(user_a, user_b)      — do A and B fit each other's filters?
    determine_match_count(...)       — docs/dating-stage-spec.md §2's honest
                                        weekly match count, incl. BGV lanes
                                        and the 8-week recent-match exclusion.
    reciprocity_counts(user, pool)   — REACH's `reciprocity` object.
    whatif_deltas(user, pool)        — REACH's `whatif[]` array.
    apply_lever_widen(user, lever)   — persist one whatif suggestion's step.
    set_range(user, lever, lo, hi)   — persist a person's own direct slider
                                        edit; unlike apply_lever_widen this
                                        MAY narrow (see set_range's docstring).
    suggest_range(pool, lever, ...)  — deterministic percentile-based
                                        "recommended range" for one lever.
    build_reach_input(user, pool)    — assembles the full §3 input JSON.

preferences.adjustable's numeric levers (age, height_cm, weight_kg,
waist_in, distance_km) are all [min, max] ranges — extended past REACH's
originally-documented single-threshold height_min_cm (docs/agent-1-
reach.pdf §3) at the user's explicit request for symmetric min/max control
on every one of them, including distance (see generate_users.py's
docstring for the reasoning on why a minimum distance is a real thing
someone might want).

Rules enforced throughout (docs/CLAUDE.md, docs/agent-1-reach.pdf §4):
    - whatif_deltas/apply_lever_widen only ever WIDEN a lever, never narrow
      it — set_range is the one exception, and only because it's the
      person editing their own filter directly, not REACH suggesting
      anything (see set_range's docstring for that distinction).
    - fixed.dealbreakers are never touched by whatif_deltas.
    - nationality/religion levers are marked "sensitive": true.
    - No appearance/skin-tone field is read or produced anywhere here —
      height_cm/weight_kg/waist_in are self-declared numeric STATS (like
      income band), not appearance data, and nothing in this module ever
      renders or infers what a person looks like.
    - fits_filters() only ever pairs opposite genders — the demo/testing
      scope is explicitly straight matching for now (no orientation field
      exists in Stats yet). This is a deliberate, temporary product-scope
      decision, not a technical limit; see fits_filters()'s own docstring.

Expects user records shaped like generate_users.py's output (or a User
table row's stats_json/vision_json/preferences_json, reassembled into that
same shape before calling in).
"""

from __future__ import annotations

from typing import Any

from generate_users import NATIONALITY_OPTIONS, RELIGION_OPTIONS

# Approximate straight-line distances (km, rounded) between the 7 cities
# generate_users.py draws from. Illustrative for this simulation, not
# survey-grade GIS data.
_CITY_DISTANCES_KM: dict[frozenset[str], int] = {
    frozenset({"Delhi", "Mumbai"}): 1150,
    frozenset({"Delhi", "Bangalore"}): 1740,
    frozenset({"Delhi", "Hyderabad"}): 1260,
    frozenset({"Delhi", "Chennai"}): 1760,
    frozenset({"Delhi", "Pune"}): 1180,
    frozenset({"Delhi", "Kolkata"}): 1300,
    frozenset({"Mumbai", "Bangalore"}): 840,
    frozenset({"Mumbai", "Hyderabad"}): 620,
    frozenset({"Mumbai", "Chennai"}): 1030,
    frozenset({"Mumbai", "Pune"}): 120,
    frozenset({"Mumbai", "Kolkata"}): 1650,
    frozenset({"Bangalore", "Hyderabad"}): 500,
    frozenset({"Bangalore", "Chennai"}): 290,
    frozenset({"Bangalore", "Pune"}): 700,
    frozenset({"Bangalore", "Kolkata"}): 1550,
    frozenset({"Hyderabad", "Chennai"}): 520,
    frozenset({"Hyderabad", "Pune"}): 500,
    frozenset({"Hyderabad", "Kolkata"}): 1200,
    frozenset({"Chennai", "Pune"}): 1000,
    frozenset({"Chennai", "Kolkata"}): 1360,
    frozenset({"Pune", "Kolkata"}): 1560,
}

# Coarse family grouping used only to resolve the "related" religion tier
# below — not a theological or product judgement. A real product would need
# this reviewed rather than inherited from a simulation fixture.
_RELIGION_FAMILY = {
    "Hindu": "dharmic",
    "Sikh": "dharmic",
    "Spiritual": "dharmic",
    "Muslim": "abrahamic",
    "Christian": "abrahamic",
    "None": "unaffiliated",
}

_VEG_COMPATIBLE_DIETS = {"Vegetarian", "Vegan", "Jain"}

# Every one of these is a [min, max] range in preferences.adjustable,
# checked directly against the matching stats.KEY on the candidate.
# distance_km is also a range but isn't a stats field (it's derived from
# both users' cities), so it's handled separately in fits_filters().
RANGE_LEVERS = ["age", "height_cm", "weight_kg", "waist_in"]

# Step size each lever's quick "Widen" action expands both min and max by
# (min -= step, max += step). Chosen to feel like a gentle nudge, not a
# jump straight to the recommended range — see suggest_range() for that.
_WIDEN_STEP = {"age": 3, "height_cm": 3, "weight_kg": 4, "waist_in": 2, "distance_km": 12}
_LEVER_FLOOR = {"age": 18, "height_cm": 0, "weight_kg": 0, "waist_in": 0, "distance_km": 0}


def city_distance_km(city_a: str, city_b: str) -> int:
    """Approximate distance between two cities; 0 for the same city."""
    if city_a == city_b:
        return 0
    return _CITY_DISTANCES_KM[frozenset({city_a, city_b})]


def _has_vision(user: dict[str, Any], key: str) -> bool:
    return any(v["key"] == key for v in user["visions"])


def _dealbreaker_satisfied(tag: str, candidate: dict[str, Any]) -> bool:
    """Check one of user_a's fixed.dealbreakers tags against candidate B.

    Only tags backed by a modeled attribute are enforced. "non_smoker" and
    "non_drinker" have no corresponding field in this simulation's Stats
    (deliberately scoped to age/height/income/diet/education/nationality/
    religion) and are treated as vacuously satisfied rather than invented.

    wants_kids/no_kids_wanted check the Kids vision's PRESENCE, not a
    stance — generate_users.py no longer decides a Kids stance at Dating
    signup (that's deferred to the /road/vision step, once a couple is
    actually together), so at match time "wants kids" is exactly what a
    candidate having "Kids" among their selected visions means; its
    absence is what "no_kids_wanted" checks for.
    """
    if tag == "veg_only":
        # An undeclared diet cannot satisfy a veg-only dealbreaker. Same
        # rule as the range levers: a hard exclusion is not waived just
        # because the other person left the field blank.
        return candidate["stats"].get("diet") in _VEG_COMPATIBLE_DIETS
    if tag == "wants_kids":
        return _has_vision(candidate, "Kids")
    if tag == "no_kids_wanted":
        return not _has_vision(candidate, "Kids")
    return True


def _nationality_fits(accepted: list[str], candidate_nationality: str | None) -> bool:
    if any(n.lower() == "any" for n in accepted):
        return True
    return candidate_nationality is not None and candidate_nationality in accepted


def _religion_fits(tiers: list[str], own_religion: str, candidate_religion: str | None) -> bool:
    if any(t.lower() == "any" for t in tiers):
        return True
    if candidate_religion is None:
        return False
    if "same" in tiers and candidate_religion == own_religion:
        return True
    if "related" in tiers and _RELIGION_FAMILY.get(candidate_religion) == _RELIGION_FAMILY.get(own_religion):
        return True
    return False


def fits_filters(user_a: dict[str, Any], user_b: dict[str, Any]) -> bool:
    """True if candidate user_b satisfies every filter user_a has stated —
    both preferences.fixed.dealbreakers and preferences.adjustable.

    Demo-scope note: this simulation currently only models straight
    matching — a candidate of the same gender never fits, full stop, no
    adjustable lever overrides it. There's no orientation/seeking field in
    Stats yet; every user is implicitly "seeking the opposite gender."
    Opening this up to other orientations later means adding that real
    field and reading it here, not deleting this check."""
    if user_a["gender"] == user_b["gender"]:
        return False

    prefs = user_a["preferences"]

    for tag in prefs["fixed"]["dealbreakers"]:
        if not _dealbreaker_satisfied(tag, user_b):
            return False

    adj = prefs["adjustable"]
    b_stats = user_b["stats"]

    # 2026-09-04, user's rule: only filters the user actually keyed in
    # apply. Two separate absences, with deliberately different answers:
    #
    #   * user_a has no lever for this field — they never gave the stat, so
    #     they are not filtering on it and every candidate passes.
    #   * user_b has no such stat — user_a IS filtering on it and there is
    #     nothing to check against, so user_b does not pass. That is what
    #     makes filling your stats in worth doing: undeclared fields keep
    #     you out of granular searches rather than sailing through them.
    for field in RANGE_LEVERS:
        if field not in adj:
            continue
        lo, hi = adj[field]
        value = b_stats.get(field)
        if value is None:
            return False
        if not (lo <= value <= hi):
            return False

    dist_lo, dist_hi = adj["distance_km"]
    distance = city_distance_km(user_a["city"], user_b["city"])
    if not (dist_lo <= distance <= dist_hi):
        return False

    if "nationality" in adj:
        if not _nationality_fits(adj["nationality"], b_stats.get("nationality")):
            return False

    # A religion filter needs BOTH sides declared: "same" and "related" are
    # both relative to user_a's own, so with either missing there is no
    # question to answer and the filter simply does not apply.
    own_religion = user_a["stats"].get("religion")
    if "religion" in adj and own_religion:
        if not _religion_fits(adj["religion"], own_religion, b_stats.get("religion")):
            return False

    return True


def mutual_open(user_a: dict[str, Any], user_b: dict[str, Any]) -> bool:
    """True if each of user_a and user_b fits the other's stated filters."""
    return fits_filters(user_a, user_b) and fits_filters(user_b, user_a)


def eligible_candidates(
    user: dict[str, Any],
    pool: list[dict[str, Any]],
    locked_in_ids: set[str],
    recent_match_ids: set[str],
) -> list[dict[str, Any]]:
    """Every candidate in `pool` that could honestly be matched to `user`
    right now (docs/dating-stage-spec.md §2's determine_match_count
    pseudocode, minus the final min(3, ...) cap — cadence.py's match
    generator needs the actual candidates, not just a count). Empty
    immediately if `user`'s own bgv_status isn't 'verified' (Lane B gets
    no matches at all — see determine_match_count's docstring).

    `locked_in_ids`/`recent_match_ids` are plain sets the CALLER computes
    from persisted LockIn/Match rows — keeps this function DB-free and
    unit-testable like everything else in this module."""
    if user["bgv_status"] != "verified":
        return []
    return [
        c
        for c in _pool_excluding_self(user, pool)
        if mutual_open(user, c)
        and c["bgv_status"] == "verified"
        and c["user_id"] not in locked_in_ids
        and c["user_id"] not in recent_match_ids
    ]


def determine_match_count(
    user: dict[str, Any],
    pool: list[dict[str, Any]],
    locked_in_ids: set[str],
    recent_match_ids: set[str],
) -> int:
    """docs/dating-stage-spec.md §2's exact rule: up to 3 matches a week,
    sized to `user`'s honest available pool — never fabricated to fill a
    slot. Zero is a valid, honest outcome (§12's "honest counts" guardrail:
    "never pad match slots"). See eligible_candidates() for the filter
    itself (mutual_open, both sides bgv_status=='verified', not locked in,
    not a recent-8-week match) — this just caps its length at 3."""
    return min(3, len(eligible_candidates(user, pool, locked_in_ids, recent_match_ids)))


def _pool_excluding_self(user: dict[str, Any], pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in pool if p["user_id"] != user["user_id"]]


def reciprocity_counts(user: dict[str, Any], pool: list[dict[str, Any]]) -> dict[str, Any]:
    """REACH's `reciprocity` object: how many candidates fit the user's own
    filters, and how many of those are mutually open."""
    candidates = _pool_excluding_self(user, pool)
    fits = sum(1 for c in candidates if fits_filters(user, c))
    mutual = sum(1 for c in candidates if mutual_open(user, c))
    return {
        "fits_user_filters": fits,
        "mutual_open": mutual,
        "no_realistic_matches": mutual == 0,
    }


def _next_wider_option(options: list[list[str]], current: list[str]) -> list[str]:
    """Find `current` in the tiered `options` sequence and return the next
    wider tier, or `current` unchanged if it's already the widest (or
    unrecognized) — never narrows, never invents a tier."""
    for i, option in enumerate(options):
        if option == current:
            return options[i + 1] if i + 1 < len(options) else current
    return current


def _widened_user(user: dict[str, Any], lever: str) -> tuple[dict[str, Any], Any, Any]:
    """Return (widened_copy, from_value, to_value) for one lever. Only the
    named adjustable field changes; fixed.dealbreakers is never touched."""
    adj = user["preferences"]["adjustable"]
    widened = {
        **user,
        "preferences": {
            "fixed": user["preferences"]["fixed"],
            "adjustable": dict(adj),
        },
    }
    new_adj = widened["preferences"]["adjustable"]

    if lever in LEVERS and lever not in adj:
        raise ValueError(
            f"Lever {lever!r} has no filter to widen — this user never gave "
            f"their {LEVER_STAT.get(lever, lever)}. Check available_levers() first."
        )

    if lever in _WIDEN_STEP:  # age, height_cm, weight_kg, waist_in, distance_km — all [min,max]
        lo, hi = adj[lever]
        step = _WIDEN_STEP[lever]
        floor = _LEVER_FLOOR[lever]
        from_value, to_value = [lo, hi], [max(floor, lo - step), hi + step]
    elif lever == "nationality":
        from_value = adj["nationality"]
        to_value = _next_wider_option(NATIONALITY_OPTIONS, adj["nationality"])
    elif lever == "religion":
        from_value = adj["religion"]
        to_value = _next_wider_option(RELIGION_OPTIONS, adj["religion"])
    else:
        raise ValueError(f"Unknown lever: {lever!r}")

    new_adj[lever] = to_value
    return widened, from_value, to_value


_SENSITIVE_LEVERS = {"nationality", "religion"}
LEVERS = ["age", "height_cm", "weight_kg", "waist_in", "distance_km", "nationality", "religion"]

# 2026-09-04, user's rule: REACH filters on what the user actually keyed
# in. A lever exists only where the backing stat does, so the whole lever
# machinery has to ask before it reaches.
LEVER_STAT = {
    "height_cm": "height_cm",
    "weight_kg": "weight_kg",
    "waist_in": "waist_in",
    "religion": "religion",
}


def available_levers(user: dict[str, Any]) -> list[str]:
    """The levers this user can actually move."""
    adj = user["preferences"]["adjustable"]
    return [lever for lever in LEVERS if lever in adj]


def locked_levers(user: dict[str, Any]) -> list[dict[str, str]]:
    """The levers they cannot move yet, and the stat that would unlock
    each. This is the honest half of the rule: rather than hiding a filter
    someone has not earned, REACH names it and says what to fill in."""
    adj = user["preferences"]["adjustable"]
    return [
        {"lever": lever, "needs": LEVER_STAT.get(lever, lever)}
        for lever in LEVERS
        if lever not in adj
    ]


def apply_lever_widen(user: dict[str, Any], lever: str) -> dict[str, Any]:
    """Public entry point for actually applying one lever's widen step —
    the same computation whatif_deltas() uses internally to preview a
    delta, exposed so a caller (e.g. the Flask app, when a user acts on a
    what-if suggestion) can persist it. Never narrows, never touches
    fixed.dealbreakers; returns a new user dict, doesn't mutate the input."""
    widened, _from_value, _to_value = _widened_user(user, lever)
    return widened


def set_range(user: dict[str, Any], lever: str, lo: float, hi: float) -> dict[str, Any]:
    """Directly set one range lever (age/height_cm/weight_kg/waist_in/
    distance_km) to [lo, hi] — for a slider the person drags themselves,
    distinct from apply_lever_widen()'s gentle nudge. This is the user
    re-editing their OWN stated preference, not an AI-suggested widen, so
    unlike whatif_deltas() it's allowed to narrow — REACH's "never narrows"
    rule governs what the *simulator* proactively suggests, not what a
    person can do to their own filter by hand."""
    if lever not in _WIDEN_STEP or lever in _SENSITIVE_LEVERS:
        raise ValueError(f"set_range doesn't apply to lever {lever!r}")
    lo, hi = min(lo, hi), max(lo, hi)
    adj = user["preferences"]["adjustable"]
    return {
        **user,
        "preferences": {
            "fixed": user["preferences"]["fixed"],
            "adjustable": {**adj, lever: [lo, hi]},
        },
    }


def suggest_range(pool: list[dict[str, Any]], lever: str, gender: str | None = None, lo_percentile: float = 25, hi_percentile: float = 75) -> tuple[float, float] | None:
    """A deterministic, explainable "recommended range" for one range lever
    — the interquartile range (25th-75th percentile by default) of that
    stat across `pool`, optionally filtered to one gender. Not an LLM call:
    docs/CLAUDE.md is explicit that matching/reciprocity/cadence stay
    deterministic and only agent NARRATION (a later phase, not built yet)
    touches the API — this is that same principle applied to
    "recommendation". Returns None if the filtered pool is empty.

    Only meaningful for the body/age levers (RANGE_LEVERS); distance_km
    doesn't have a population "typical value" the same way, so it isn't
    supported here."""
    if lever not in RANGE_LEVERS:
        raise ValueError(f"suggest_range only supports {RANGE_LEVERS}, not {lever!r}")
    values = sorted(u["stats"][lever] for u in pool if gender is None or u["gender"] == gender)
    if not values:
        return None

    def percentile(p: float) -> float:
        if len(values) == 1:
            return values[0]
        rank = (p / 100) * (len(values) - 1)
        lo_idx, frac = int(rank), rank - int(rank)
        hi_idx = min(lo_idx + 1, len(values) - 1)
        return values[lo_idx] + (values[hi_idx] - values[lo_idx]) * frac

    return round(percentile(lo_percentile)), round(percentile(hi_percentile))


def whatif_deltas(user: dict[str, Any], pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """REACH's `whatif[]` array: for each adjustable lever, widen it alone
    and report how many MORE candidates become mutually open. Matches
    docs/agent-1-reach.pdf §3/§4 exactly — only ever widens, never touches
    fixed.dealbreakers, flags nationality/religion as sensitive."""
    candidates = _pool_excluding_self(user, pool)
    baseline = sum(1 for c in candidates if mutual_open(user, c))

    results = []
    for lever in available_levers(user):
        widened, from_value, to_value = _widened_user(user, lever)
        new_mutual = sum(1 for c in candidates if mutual_open(widened, c))
        entry = {
            "lever": lever,
            "from": from_value,
            "to": to_value,
            "delta_mutual_open": new_mutual - baseline,
        }
        if lever in _SENSITIVE_LEVERS:
            entry["sensitive"] = True
        results.append(entry)
    return results


def build_reach_input(user: dict[str, Any], pool: list[dict[str, Any]], phase: str = "searching") -> dict[str, Any]:
    """Assemble the full REACH input payload (docs/agent-1-reach.pdf §3)."""
    return {
        "user_id": user["user_id"],
        "phase": phase,
        "preferences": user["preferences"],
        "reciprocity": reciprocity_counts(user, pool),
        "whatif": whatif_deltas(user, pool),
        "locked": locked_levers(user),
    }
