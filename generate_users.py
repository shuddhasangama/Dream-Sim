"""Synthetic user population generator for the DREAM simulation harness.

Produces N users with demographics (city/gender/age band), Visions
(values/long-term alignment), Stats, and preferences split into fixed
(dealbreakers) and adjustable filters. preferences.adjustable extends
REACH's original documented shape (docs/agent-1-reach.pdf §3: age,
height_min_cm, distance_km, nationality, religion) with full [min, max]
ranges on every numeric lever — height_cm, weight_kg, waist_in and
distance_km all became ranges instead of one-sided thresholds, and
weight_kg/waist_in are new. This is a deliberate divergence from that PDF,
made at the user's explicit request (2026-08-27) for symmetric min/max
control on all four body/distance levers.

Stats carries each user's own height_cm/weight_kg/waist_in, nationality
and religion in addition to age/income/diet/education — these are
self-declared numeric/categorical STATS (the same kind of thing as income
band or education), not appearance data: nothing here is inferred from an
image, and no visual/appearance representation of a person is ever
produced anywhere in this project (docs/CLAUDE.md, brief cross-cutting
rules, guardrail DTD-XCT-001 — see test_generate_users.py's
NoAppearanceFieldsTests). A user's *preference* about a partner's
nationality/religion/height/weight/waist is a separate field; see
preferences.adjustable below.

Preferred-partner-gender assumption: each user's adjustable filters (age,
height_cm, weight_kg, waist_in) are computed against the OPPOSITE gender,
since neither the brief nor this task specifies an orientation field.
Documented here rather than silently assumed.

Usage:
    python generate_users.py --count 500 --seed 42 --out data/synthetic_users.json
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_OUT_PATH = Path(__file__).parent / "data" / "synthetic_users.json"

# ── demographics (weighted, not uniform) ──────────────────────────────────

CITIES = ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Pune", "Chennai", "Kolkata"]
CITY_WEIGHTS = [0.20, 0.20, 0.20, 0.12, 0.12, 0.10, 0.06]

GENDERS = ["female", "male"]
GENDER_WEIGHTS = [0.49, 0.51]

AGE_BANDS = [(28, 34), (35, 41), (42, 48)]
AGE_BAND_WEIGHTS = [0.45, 0.35, 0.20]

# Reuses the DREAM app's own Vision goal taxonomy (dream-contract-app's
# src/data/goals.ts) so this generator stays consistent with the product.
VISION_KEYS = ["Kids", "Intimacy", "Cohabitate", "Travel together"]

# Every user's vision must include Intimacy (with 1-2 of its own kinds
# below) plus at least one of these three (2026-08-28, user's explicit
# rule: "one definitely being Intimacy... others one among Kids,
# Cohabitate, Travel Together"). See _generate_visions().
OTHER_VISION_KEYS = ["Kids", "Cohabitate", "Travel together"]

# Kids' stance detail is deliberately NOT decided at Dating signup — per
# the user's framing, "just the vision needs to be mentioned... how part
# of it will be figured out along the way." Kids starts at stance=None
# (same as Travel together always has) and only gets a real stance once
# the couple reaches Relationship and visits the /road/vision step
# (app.py's road_vision route).
#
# Cohabitate is the exception, revised 2026-09-03 at the user's request:
# choosing to cohabit without saying whether you mean chores, expenses or
# both says almost nothing, so its focus IS captured at signup. It stays
# in VISION_STANCE_OPTIONS so it can still be revised at Relationship.
KIDS_STANCES = ["Have kids & want more", "Have kids & don't want more", "Want kids", "Don't want kids"]
INTIMACY_KINDS = ["Emotional", "Physical"]  # 2026-08-28: Sexual removed at the user's request
COHABIT_FOCUS = ["Chores split", "Expenses sharing"]

INCOME_BANDS = ["₹ · under 12L", "₹₹ · 12L – 25L", "₹₹₹ · 25L – 50L", "₹₹₹₹ · 50L+"]
INCOME_BAND_WEIGHTS = [0.15, 0.40, 0.30, 0.15]

# Per-person spend on one meal out — distinct from INCOME_BANDS, which is
# what someone earns. Two people can share an income band and still be
# uncomfortable in each other's restaurants, which is the friction the
# date playbook's bill-split clause exists to prevent.
RESTAURANT_BUDGETS = ["₹ · under 800", "₹₹ · 800 – 2,000", "₹₹₹ · 2,000 – 4,500", "₹₹₹₹ · 4,500+"]
RESTAURANT_BUDGET_WEIGHTS = [0.22, 0.42, 0.26, 0.10]

# Self-declared descent, at the coarse level people describe themselves.
# Deliberately NOT caste, and deliberately not a matching filter — see
# matching.py's lever list, which this is absent from. "Prefer not to say"
# is a first-class value, not a gap to be filled in later.
ETHNICITIES = [
    "Indian", "South Asian (other)", "East Asian", "Southeast Asian",
    "Middle Eastern", "African", "European", "Latin American",
    "Mixed", "Prefer not to say",
]
ETHNICITY_WEIGHTS = [0.74, 0.06, 0.02, 0.02, 0.02, 0.02, 0.03, 0.01, 0.03, 0.05]

DIETS = ["Vegetarian", "Vegan", "Eggetarian", "Halal", "Jain", "No red meat", "Everything"]
DIET_WEIGHTS = [0.30, 0.05, 0.10, 0.08, 0.07, 0.10, 0.30]

EDUCATION = ["High school", "Bachelor's", "Master's", "Doctorate"]
EDUCATION_WEIGHTS = [0.10, 0.55, 0.30, 0.05]

# Each user's OWN declared nationality/religion — distinct from the
# nationality/religion *preference* lists below, which describe what a user
# will accept in a partner. matching.py needs both: the preference list to
# filter with, and this identity value to filter against.
OWN_NATIONALITIES = ["IN", "NRI"]
OWN_NATIONALITY_WEIGHTS = [0.92, 0.08]

OWN_RELIGIONS = ["Hindu", "Muslim", "Christian", "Sikh", "Spiritual", "None"]
OWN_RELIGION_WEIGHTS = [0.55, 0.14, 0.12, 0.08, 0.07, 0.04]

# Added 2026-08-28 (docs/relationship-stage-spec.md §C2 — "All mandatory:
# age, height, profession, income band, education, diet, marital history,
# location, languages") so every generated user already has real values for
# the three Stats fields this project didn't previously track. Purely
# additive — folded into stats_json alongside the existing fields, no
# existing key changes shape or weighting.
PROFESSIONS = ["Engineering", "Medicine", "Finance", "Law", "Design", "Education", "Business/Entrepreneur", "Government/Public sector", "Arts/Media", "Other"]
PROFESSION_WEIGHTS = [0.20, 0.08, 0.14, 0.06, 0.08, 0.09, 0.13, 0.08, 0.06, 0.08]

MARITAL_HISTORY = ["Never married", "Divorced", "Widowed"]
MARITAL_HISTORY_WEIGHTS = [0.82, 0.15, 0.03]

LANGUAGES_POOL = ["English", "Hindi", "Marathi", "Tamil", "Telugu", "Kannada", "Bengali", "Gujarati", "Punjabi", "Malayalam"]

# BGV (background verification) status drives Dating's two-lane gating
# (docs/dating-stage-spec.md §2): Lane A ("verified") gets full weekly
# matches, Lane B (everything else) is vision-level browse only. Biased
# toward 'verified' so Lane A has real depth to test matching against —
# a population that's mostly unverified would make the whole Dating stage
# trivially empty. Matches db.py's User.bgv_status CHECK values exactly.
BGV_STATUSES = ["verified", "pending", "declared", "partially_verified", "unverifiable"]
BGV_STATUS_WEIGHTS = [0.65, 0.15, 0.10, 0.07, 0.03]

HEIGHT_CM_BY_GENDER = {"female": (160.0, 6.0), "male": (172.0, 6.5)}  # (mean, sd)
WEIGHT_KG_BY_GENDER = {"female": (58.0, 8.0), "male": (72.0, 10.0)}
WAIST_IN_BY_GENDER = {"female": (30.0, 3.5), "male": (34.0, 4.0)}

DEALBREAKER_POOL = ["veg_only", "non_smoker", "non_drinker", "wants_kids", "no_kids_wanted"]
DEALBREAKER_COUNT_WEIGHTS = [0.35, 0.35, 0.20, 0.10]  # P(0), P(1), P(2), P(3)

NATIONALITY_OPTIONS = [["IN"], ["IN", "NRI"], ["IN", "NRI", "Any"]]
NATIONALITY_WEIGHTS = [0.70, 0.22, 0.08]

RELIGION_OPTIONS = [["same"], ["same", "related"], ["same", "related", "any"]]
RELIGION_WEIGHTS = [0.75, 0.18, 0.07]

# "Most people set moderately narrow filters, a minority set very narrow
# ones": each numeric adjustable lever draws from a two-component mixture —
# 80% land in the moderate band, 20% in the tighter/narrower band.
NARROW_FILTER_PROBABILITY = 0.2


def _weighted_choice(rng: random.Random, options: list[Any], weights: list[float]) -> Any:
    return rng.choices(options, weights=weights, k=1)[0]


def _clipped_normal(rng: random.Random, mean: float, sd: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, rng.normalvariate(mean, sd)))


def _mixture_draw(
    rng: random.Random,
    moderate: tuple[float, float, float, float],  # mean, sd, lo, hi
    narrow: tuple[float, float, float, float],
) -> float:
    """Draw from the moderate component 80% of the time, the narrow one 20%."""
    params = narrow if rng.random() < NARROW_FILTER_PROBABILITY else moderate
    return _clipped_normal(rng, *params)


def _opposite_gender(gender: str) -> str:
    return "male" if gender == "female" else "female"


def _generate_visions(rng: random.Random) -> list[dict[str, Any]]:
    """Every user gets Intimacy (mandatory, with 1-2 of its own kinds)
    plus at least one — up to all three — of Kids/Cohabitate/Travel
    together, so every vision list has 2-4 entries and always includes
    Intimacy. Cohabitate carries its focus (chores, expenses or both)
    from signup; Kids starts at stance=None — that detail isn't decided
    at signup (see KIDS_STANCES' comment above) — and Travel together
    never has one.

    Kids requires Physical intimacy (2026-08-28, user's explicit rule:
    "Kids cannot be selected if Intimacy - Physical is not selected") —
    Intimacy's kinds are drawn first, and Kids is only ever eligible to be
    picked as one of the "other" keys when Physical is among them."""
    intimacy_kinds = sorted(rng.sample(INTIMACY_KINDS, k=rng.randint(1, len(INTIMACY_KINDS))))
    eligible_others = OTHER_VISION_KEYS if "Physical" in intimacy_kinds else [k for k in OTHER_VISION_KEYS if k != "Kids"]
    other_keys = rng.sample(eligible_others, k=rng.randint(1, len(eligible_others)))

    visions = [{"key": "Intimacy", "stance": intimacy_kinds}]
    for key in other_keys:
        if key == "Cohabitate":
            # Chores split, Expenses sharing, or both — decided at signup.
            stance = sorted(rng.sample(COHABIT_FOCUS, k=rng.randint(1, len(COHABIT_FOCUS))))
        else:
            stance = None  # Kids and Travel together carry no detail at signup
        visions.append({"key": key, "stance": stance})
    return visions


def _generate_stats(rng: random.Random, gender: str, age: int) -> dict[str, Any]:
    height_mean, height_sd = HEIGHT_CM_BY_GENDER[gender]
    weight_mean, weight_sd = WEIGHT_KG_BY_GENDER[gender]
    waist_mean, waist_sd = WAIST_IN_BY_GENDER[gender]
    return {
        "age": age,
        "height_cm": round(_clipped_normal(rng, height_mean, height_sd, 140, 210)),
        "weight_kg": round(_clipped_normal(rng, weight_mean, weight_sd, 40, 150)),
        "waist_in": round(_clipped_normal(rng, waist_mean, waist_sd, 20, 55)),
        "income_band": _weighted_choice(rng, INCOME_BANDS, INCOME_BAND_WEIGHTS),
        "budget": _weighted_choice(rng, RESTAURANT_BUDGETS, RESTAURANT_BUDGET_WEIGHTS),
        "ethnicity": _weighted_choice(rng, ETHNICITIES, ETHNICITY_WEIGHTS),
        "diet": _weighted_choice(rng, DIETS, DIET_WEIGHTS),
        "education": _weighted_choice(rng, EDUCATION, EDUCATION_WEIGHTS),
        "nationality": _weighted_choice(rng, OWN_NATIONALITIES, OWN_NATIONALITY_WEIGHTS),
        "religion": _weighted_choice(rng, OWN_RELIGIONS, OWN_RELIGION_WEIGHTS),
        "profession": _weighted_choice(rng, PROFESSIONS, PROFESSION_WEIGHTS),
        "marital_history": _weighted_choice(rng, MARITAL_HISTORY, MARITAL_HISTORY_WEIGHTS),
        "languages": sorted(rng.sample(LANGUAGES_POOL, k=rng.randint(1, 3))),
    }


def _range_around(rng: random.Random, center: float, moderate: tuple, narrow: tuple, floor: float, ceil: float) -> list[int]:
    """A [min, max] range centered near `center`, with the total width drawn
    from the moderate/narrow mixture (docs/CLAUDE.md-style "most people set
    moderately narrow filters, a minority set very narrow ones") and split
    unevenly below/above center so the range isn't perfectly symmetric."""
    width = _mixture_draw(rng, moderate=moderate, narrow=narrow)
    below = width * rng.uniform(0.4, 0.6)
    above = width - below
    lo = max(floor, center - below)
    hi = min(ceil, center + above)
    if hi <= lo:
        hi = min(ceil, lo + 1)
    return [round(lo), round(hi)]


def _generate_preferences(rng: random.Random, gender: str, age: int) -> dict[str, Any]:
    dealbreaker_count = _weighted_choice(rng, [0, 1, 2, 3], DEALBREAKER_COUNT_WEIGHTS)
    dealbreakers = sorted(rng.sample(DEALBREAKER_POOL, k=dealbreaker_count))

    age_range = _range_around(rng, age, moderate=(8, 2, 4, 14), narrow=(3, 1, 1, 5), floor=18, ceil=99)

    # height/weight/waist preferences are centered on the target gender's
    # population mean — "what's typical for the partner I'm looking for",
    # not this user's own stats.
    partner_gender = _opposite_gender(gender)
    height_mean, _ = HEIGHT_CM_BY_GENDER[partner_gender]
    weight_mean, _ = WEIGHT_KG_BY_GENDER[partner_gender]
    waist_mean, _ = WAIST_IN_BY_GENDER[partner_gender]

    height_range = _range_around(rng, height_mean, moderate=(16, 3, 8, 26), narrow=(6, 2, 3, 10), floor=140, ceil=210)
    weight_range = _range_around(rng, weight_mean, moderate=(24, 5, 12, 40), narrow=(8, 2, 4, 14), floor=40, ceil=150)
    waist_range = _range_around(rng, waist_mean, moderate=(10, 2, 5, 16), narrow=(4, 1, 2, 6), floor=20, ceil=55)

    # Distance is asymmetric: almost everyone's minimum is 0 (no lower
    # bound on closeness), a minority want at least some buffer — small
    # towns/shared social circles are a real reason to set one.
    distance_min = round(_mixture_draw(rng, moderate=(0, 0, 0, 0), narrow=(8, 3, 3, 15)))
    distance_max = round(_mixture_draw(rng, moderate=(20, 7, 8, 45), narrow=(6, 2, 3, 9)))
    distance_max = max(distance_max, distance_min + 5)

    return {
        "fixed": {"dealbreakers": dealbreakers},
        "adjustable": {
            "age": age_range,
            "height_cm": height_range,
            "weight_kg": weight_range,
            "waist_in": waist_range,
            "distance_km": [distance_min, distance_max],
            "nationality": _weighted_choice(rng, NATIONALITY_OPTIONS, NATIONALITY_WEIGHTS),
            "religion": _weighted_choice(rng, RELIGION_OPTIONS, RELIGION_WEIGHTS),
        },
    }


def generate_users(count: int, seed: int) -> list[dict[str, Any]]:
    """Generate `count` synthetic users, seeded for reproducibility. Uses a
    private random.Random instance so calling this repeatedly (or alongside
    other code that also uses `random`) never changes the result."""
    rng = random.Random(seed)
    users = []
    for i in range(count):
        city = _weighted_choice(rng, CITIES, CITY_WEIGHTS)
        gender = _weighted_choice(rng, GENDERS, GENDER_WEIGHTS)
        band = _weighted_choice(rng, AGE_BANDS, AGE_BAND_WEIGHTS)
        age = rng.randint(band[0], band[1])

        users.append(
            {
                "user_id": f"u_{i + 1:04d}",
                "city": city,
                "gender": gender,
                "age_band": f"{band[0]}-{band[1]}",
                "bgv_status": _weighted_choice(rng, BGV_STATUSES, BGV_STATUS_WEIGHTS),
                "stats": _generate_stats(rng, gender, age),
                "visions": _generate_visions(rng),
                "preferences": _generate_preferences(rng, gender, age),
            }
        )
    return users


def to_user_row(user: dict[str, Any], journey_state: str = "dating") -> dict[str, Any]:
    """Map one generate_users() record to a db.py User table row.

    city/gender/age_band aren't separate User columns (the brief's §7 struct
    only gives User a general `stats` bucket), so they're folded into
    stats_json alongside age/height/income/diet/education.
    """
    stats = {"city": user["city"], "gender": user["gender"], "age_band": user["age_band"], **user["stats"]}
    return {
        "id": user["user_id"],
        "journey_state": journey_state,
        "bgv_status": user.get("bgv_status", "declared"),
        "stats_json": json.dumps(stats, ensure_ascii=False),
        "vision_json": json.dumps(user["visions"], ensure_ascii=False),
        "preferences_json": json.dumps(user["preferences"], ensure_ascii=False),
    }


def from_user_row(row: dict[str, Any]) -> dict[str, Any]:
    """The inverse of to_user_row(): reconstruct a generate_users()-shaped
    record from a User table row (e.g. sqlite3.Row -> dict via db.fetch_one),
    so matching.py/cadence.py/journey.py — which all expect that shape —
    can be called on data loaded straight out of the database. Adds
    journey_state as an extra key; the matching/cadence functions ignore
    keys they don't use, so this doesn't break anything that consumes it."""
    stats_all = json.loads(row["stats_json"])
    stats = {k: v for k, v in stats_all.items() if k not in ("city", "gender", "age_band")}
    return {
        "user_id": row["id"],
        "city": stats_all.get("city"),
        "gender": stats_all.get("gender"),
        "age_band": stats_all.get("age_band"),
        "bgv_status": row["bgv_status"],
        "stats": stats,
        "visions": json.loads(row["vision_json"]),
        "preferences": json.loads(row["preferences_json"]),
        "journey_state": row["journey_state"],
    }


def seed_db(conn: sqlite3.Connection, users: list[dict[str, Any]], journey_state: str = "dating") -> None:
    """Insert generated users into the User table via db.py's insert_row.
    journey_state defaults to 'dating' — REACH's searching phase, which is
    where this generator's population is meant to be used."""
    import db  # local import: keeps `python generate_users.py --out ...` usable with no db.py/sqlite3 setup needed

    for user in users:
        db.insert_row(conn, "User", to_user_row(user, journey_state))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=100, help="number of users to generate (default: 100)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducible runs (default: 42)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH, help=f"output JSON path (default: {DEFAULT_OUT_PATH})")
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="also insert the generated users into the configured database",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="local SQLite path to use when DATABASE_URL is not configured",
    )
    args = parser.parse_args()

    users = generate_users(args.count, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(users, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(users)} synthetic users to {args.out} (seed={args.seed})")

    if args.write_db:
    	import db

    	conn = db.get_connection(args.db_path or db.DEFAULT_DB_PATH)
    	db.init_db(conn)
    	seed_db(conn, users)
    	conn.close()
    	print(f"Inserted {len(users)} rows into the configured database")


if __name__ == "__main__":
    main()
