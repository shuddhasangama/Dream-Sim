"""Front-door onboarding: sign-up, Vision, Stats, Chemistry (Segment A).

The simulation harness has always been seeded by generate_users.py — there
was no way for a person to create themselves. This module is the missing
half: it turns three screens of form input into exactly the record shape
generate_users.to_user_row() produces, so everything downstream (matching,
cadence, journey, REACH) sees a self-registered user as indistinguishable
from a generated one.

Pure functions only. The caller (app.py) persists — same convention as
chemistry.py and vision.py.

Naming rule (docs/CLAUDE.md): never use the word "contract" in identifiers
or messages — use "playbook" / "plan" / "agreement of understanding".

Deliberate scope for this segment: nothing here validates the email or
phone. Case 1 asks for an unvalidated front door so the walkthrough can
run; real credential handling is Phase 3 of the roadmap, and Account.* is
shaped to receive it without a migration.
"""

from __future__ import annotations

import random
import re
import uuid
from typing import Any

from generate_users import (
    AGE_BANDS,
    COHABIT_FOCUS,
    CUISINES,
    DIETS,
    DRINKING,
    ETHNICITIES,
    FITNESS_ROUTINES,
    EDUCATION,
    INCOME_BANDS,
    INTIMACY_KINDS,
    KIDS_STANCES,
    LANGUAGES_POOL,
    MARITAL_HISTORY,
    OTHER_VISION_KEYS,
    OWN_NATIONALITIES,
    OWN_RELIGIONS,
    PROFESSIONS,
    RESTAURANT_BUDGETS,
    SMOKING,
)

# ── Step 3: Chemistry as the mock-up models it ────────────────────────────
# NOTE this is NOT chemistry.py. That module is the Relationship-entry
# intimacy-expectations layer (docs/relationship-stage-spec.md §C3) and is
# unrelated. The mock-up's "chemistry" step is an activity/skill sort, and
# it lands in User.skills_json — a column the schema has always declared
# and nothing has ever written to.

ACTIVITIES = [
    "Cooking", "Hiking", "Salsa", "Tennis", "Yoga", "Photography",
    "Board games", "Live gigs", "Cycling", "Pottery", "Stand-up", "Scuba diving",
]

BUCKETS = [
    ("good", "★", "Already good at it"),
    ("improve", "↑", "Want to improve"),
    ("maybe", "?", "Never considered, so maybe"),
    ("no", "✕", "Not my cup of tea"),
]
BUCKET_IDS = {b[0] for b in BUCKETS}

# The mock-up gates step 3 on at least four activities sorted, not all
# twelve — sorting everything is a chore and the pool only needs enough
# overlap to say something useful.
MIN_SORTED = 4


# ── Step 2: salary → income band ──────────────────────────────────────────
# Thresholds chosen to land exactly on generate_users.INCOME_BANDS, so a
# self-registered user's income_band is directly comparable with the
# generated population's. Changing these without changing INCOME_BANDS
# would silently split the pool in two.

SALARY_THRESHOLDS = [1_200_000, 2_500_000, 5_000_000]


def bracket_for(annual_inr: Any) -> str | None:
    """Map a declared annual salary in rupees to one of INCOME_BANDS.
    Returns None for blank or unparseable input rather than guessing."""
    if annual_inr is None:
        return None
    text = str(annual_inr).strip().replace(",", "").replace("₹", "")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if value <= 0:
        return None
    for index, threshold in enumerate(SALARY_THRESHOLDS):
        if value < threshold:
            return INCOME_BANDS[index]
    return INCOME_BANDS[-1]


def age_band_for(age: int) -> str:
    """The AGE_BANDS label containing `age`, or the nearest band if the age
    falls outside the generated population's 28-48 span. age_band is a
    coarse bucket used for reporting; the precise `age` in stats is what
    matching filters on, so clamping here loses nothing."""
    for low, high in AGE_BANDS:
        if low <= age <= high:
            return f"{low}-{high}"
    if age < AGE_BANDS[0][0]:
        return f"{AGE_BANDS[0][0]}-{AGE_BANDS[0][1]}"
    return f"{AGE_BANDS[-1][0]}-{AGE_BANDS[-1][1]}"


# ── identifiers ───────────────────────────────────────────────────────────
# Generated users are u_0001..u_NNNN. Self-registered users take a
# distinct prefix so the two populations are always separable — you can
# delete every demo signup with one DELETE ... LIKE 'su_%' and leave the
# seeded pool intact (roadmap Phase 1: "separate synthetic users from any
# environment real users can reach").

SELF_SIGNUP_PREFIX = "su_"


def new_user_id() -> str:
    return f"{SELF_SIGNUP_PREFIX}{uuid.uuid4().hex[:12]}"


def is_self_signup(user_id: str) -> bool:
    return str(user_id).startswith(SELF_SIGNUP_PREFIX)


# ── Step 1: sign-up ───────────────────────────────────────────────────────

_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalise_identifiers(email: str | None, phone: str | None) -> dict[str, Any]:
    """Tidy the two identifiers and report whether each *looks* right.

    Deliberately advisory: `ok` is true as long as at least one identifier
    was supplied. The shape flags are surfaced to the user as a hint, never
    enforced — Case 1 specifies an unvalidated front door. When Phase 3
    adds OTP and email verification, this is the function that stops
    returning advice and starts returning a verdict.
    """
    email_clean = (email or "").strip().lower()
    phone_digits = re.sub(r"\D", "", phone or "")

    return {
        "email": email_clean or None,
        "phone": phone_digits or None,
        "email_looks_valid": bool(email_clean) and bool(_EMAIL_SHAPE.match(email_clean)),
        "phone_looks_valid": len(phone_digits) in (10, 11, 12),
        "ok": bool(email_clean or phone_digits),
        "error": None if (email_clean or phone_digits) else "Enter an email address or a phone number to continue.",
    }


def account_row(user_id: str, email: str | None, phone: str | None, created_at: str) -> dict[str, Any]:
    """The Account row to persist. password_hash stays NULL for now —
    the column exists so Phase 3 can fill it without a schema change."""
    return {
        "id": f"acct_{user_id}",
        "user_id": user_id,
        "email": email,
        "phone": phone,
        "password_hash": None,
        "verified_email": 0,
        "verified_phone": 0,
        "created_at": created_at,
    }


# ── Step 1b: Vision ───────────────────────────────────────────────────────
# Mirrors generate_users._generate_visions() exactly, so a self-registered
# vision list is the same shape the matching and journey code already read:
#   - Intimacy is mandatory, with Emotional, Physical, or both
#   - at least one more of Kids / Cohabitate / Travel together
#   - Cohabitate carries its focus — Chores split, Expenses sharing, or
#     both — chosen here at signup (revised 2026-09-03)
#   - Kids and Travel together carry no detail at signup; Kids' stance is
#     decided later at /road/vision, once the couple reaches Relationship
#   - Kids requires Physical intimacy (2026-08-28 rule, still in force —
#     generate_users and test_generate_users both enforce it)

VISION_STANCE_AT_SIGNUP = None

# Goals that take no detail at signup, in the order they are offered.
SIMPLE_GOALS = ["Travel together", "Kids"]
DETAILED_GOALS = {"Cohabitate": COHABIT_FOCUS}


def validate_vision(
    intimacy_kinds: list[str],
    other_keys: list[str],
    cohabit_focus: list[str] | None = None,
) -> dict[str, Any]:
    """Check a submitted vision against the rules above.

    cohabit_focus is only consulted when Cohabitate is among other_keys;
    picking a focus and then unticking Cohabitate discards it rather than
    storing a preference for a goal the user did not choose.
    """
    kinds = [k for k in INTIMACY_KINDS if k in (intimacy_kinds or [])]
    others = [k for k in OTHER_VISION_KEYS if k in (other_keys or [])]
    focus = [f for f in COHABIT_FOCUS if f in (cohabit_focus or [])]

    if not kinds:
        return {"ok": False, "error": "Pick at least one kind of intimacy — every vision includes it."}
    if not others:
        return {"ok": False, "error": "Pick at least one more end goal alongside Intimacy."}
    if "Kids" in others and "Physical" not in kinds:
        return {"ok": False, "error": "Kids needs Physical intimacy selected too. Add it, or drop Kids."}
    if "Cohabitate" in others and not focus:
        return {"ok": False, "error": "Cohabitating means chores, expenses, or both — say which."}

    return {
        "ok": True,
        "error": None,
        "intimacy_kinds": sorted(kinds),
        "other_keys": others,
        "cohabit_focus": sorted(focus) if "Cohabitate" in others else [],
    }


def build_visions(
    intimacy_kinds: list[str],
    other_keys: list[str],
    cohabit_focus: list[str] | None = None,
) -> list[dict[str, Any]]:
    """The vision_json payload. Call only after validate_vision() passes."""
    focus = sorted(f for f in COHABIT_FOCUS if f in (cohabit_focus or []))
    visions = [{"key": "Intimacy", "stance": sorted(intimacy_kinds)}]
    for key in OTHER_VISION_KEYS:
        if key not in other_keys:
            continue
        stance = focus if key == "Cohabitate" else VISION_STANCE_AT_SIGNUP
        visions.append({"key": key, "stance": stance})
    return visions


# ── Step 2: Stats ─────────────────────────────────────────────────────────
# Field list and value vocabularies are generate_users._generate_stats()'s,
# so a self-registered user is filterable by matching.py on day one.

NUMERIC_STATS = [
    # key, label, unit, min, max, placeholder
    ("age", "Age", "years", 21, 75, "31"),
    ("height_cm", "Height", "cm", 140, 210, "178"),
    ("weight_kg", "Weight", "kg", 40, 150, "74"),
    ("waist_in", "Waist", "in", 20, 55, "32"),
]

CHOICE_STATS = [
    ("budget", "Restaurant budget", RESTAURANT_BUDGETS),
    ("diet", "Dietary preference", DIETS),
    ("smoking", "Smoking", SMOKING),
    ("drinking", "Drinking", DRINKING),
    ("fitness_routine", "Fitness routine", FITNESS_ROUTINES),
    ("education", "Education", EDUCATION),
    ("profession", "Profession", PROFESSIONS),
    ("marital_history", "Marital history", MARITAL_HISTORY),
    ("nationality", "Nationality", OWN_NATIONALITIES),
    ("ethnicity", "Ethnicity", ETHNICITIES),
    ("religion", "Religion", OWN_RELIGIONS),
]

# Multi-select stats. Kept separate from CHOICE_STATS because the form
# posts them as a list and validate_stats has to read them differently —
# collapsing the two would mean a truthy check that silently accepts one
# value where the field means "all of these".
MULTI_STATS = [
    ("languages", "Languages you speak", LANGUAGES_POOL, "pick at least one"),
    ("cuisine", "Cuisine you enjoy", CUISINES, "pick at least one"),
]

# budget is what someone spends on one meal out, not what they earn — it
# feeds the date playbook's bill-split clause, where a mismatch actually
# bites. ethnicity is self-declared and NEVER a matching filter: declaring
# your own descent and screening other people by theirs are different
# products, and only the first was asked for. "Prefer not to say" is a
# real answer, so the field is required but never forces a disclosure.

CITIES_FOR_SIGNUP = ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Pune", "Chennai", "Kolkata"]
GENDERS_FOR_SIGNUP = ["female", "male"]

# Every stat above is mandatory except languages, which needs at least one.
REQUIRED_STAT_KEYS = (
    [k for k, _, _, _, _, _ in NUMERIC_STATS]
    + [k for k, _, _ in CHOICE_STATS]
    + [k for k, _, _, _ in MULTI_STATS]
)


def validate_stats(form: dict[str, Any]) -> dict[str, Any]:
    """Validate and coerce the Stats step. Returns {"ok", "error", "stats"}.

    `form` is a plain dict; "languages" may be a list or a single string.
    In app.py, build it as:
        {**request.form.to_dict(), "languages": request.form.getlist("languages")}

    `stats` on success is the exact dict _generate_stats() returns, plus
    the derived income_band — ready to be folded into stats_json.
    """
    stats: dict[str, Any] = {}

    for key, label, _unit, low, high, _ph in NUMERIC_STATS:
        raw = str(form.get(key, "")).strip()
        if not raw:
            return {"ok": False, "error": f"{label} is needed to match you on it.", "stats": None}
        try:
            value = int(round(float(raw)))
        except ValueError:
            return {"ok": False, "error": f"{label} should be a number.", "stats": None}
        if not low <= value <= high:
            return {"ok": False, "error": f"{label} should be between {low} and {high} {_unit}.", "stats": None}
        stats[key] = value

    for key, label, options in CHOICE_STATS:
        value = str(form.get(key, "")).strip()
        if value not in options:
            return {"ok": False, "error": f"Choose a {label.lower()}.", "stats": None}
        stats[key] = value

    for key, label, options, _hint in MULTI_STATS:
        raw = form.get(key) or []
        if isinstance(raw, str):
            raw = [raw]
        chosen = [value for value in options if value in raw]
        if not chosen:
            return {"ok": False, "error": f"{label} — pick at least one.", "stats": None}
        stats[key] = sorted(chosen)

    band = bracket_for(form.get("salary"))
    if band is None:
        return {"ok": False, "error": "Enter your annual salary in rupees — it derives your bracket, and only the bracket is ever shown.", "stats": None}
    stats["income_band"] = band

    city = str(form.get("city", "")).strip()
    if city not in CITIES_FOR_SIGNUP:
        return {"ok": False, "error": "Choose your city.", "stats": None}

    gender = str(form.get("gender", "")).strip()
    if gender not in GENDERS_FOR_SIGNUP:
        return {"ok": False, "error": "Choose a gender — matching uses it to pick the candidate pool.", "stats": None}

    return {"ok": True, "error": None, "stats": stats, "city": city, "gender": gender}


# ── Step 3: Chemistry (activity sort) ─────────────────────────────────────


def validate_activities(sorted_map: dict[str, str]) -> dict[str, Any]:
    """Check the activity sort. Returns {"ok", "error", "activities"}."""
    clean = {
        activity: bucket
        for activity, bucket in (sorted_map or {}).items()
        if activity in ACTIVITIES and bucket in BUCKET_IDS
    }
    if len(clean) < MIN_SORTED:
        return {
            "ok": False,
            "error": f"Sort at least {MIN_SORTED} activities ({len(clean)}/{MIN_SORTED} so far).",
            "activities": None,
        }
    return {"ok": True, "error": None, "activities": clean}


def build_skills(activities: dict[str, str]) -> dict[str, Any]:
    """The skills_json payload: the raw sort plus a bucket index, so a
    match view can answer "what do we both want to improve at" without
    re-grouping on every render."""
    by_bucket: dict[str, list[str]] = {bucket_id: [] for bucket_id, _, _ in BUCKETS}
    for activity, bucket in sorted(activities.items()):
        by_bucket[bucket].append(activity)
    return {"activities": dict(sorted(activities.items())), "by_bucket": by_bucket}


# ── Preferences ───────────────────────────────────────────────────────────


def default_preferences(stats: dict[str, Any]) -> dict[str, Any]:
    """Starting REACH filters for a self-registered user.

    Every value is deliberately one step in from the widest option, so the
    REACH lever machinery has somewhere to widen to. nationality and
    religion MUST be exact members of generate_users.NATIONALITY_OPTIONS
    and RELIGION_OPTIONS — matching._next_wider_option() looks the current
    value up in those lists, and an off-list value would make the widen
    lever a no-op.

    No dealbreakers are assumed on the user's behalf. A dealbreaker is a
    hard exclusion of other people; the product should never invent one
    silently, so this starts empty and the user adds their own.
    """
    age = int(stats.get("age", 32))
    return {
        "fixed": {"dealbreakers": []},
        "adjustable": {
            "age": [max(21, age - 6), age + 6],
            "height_cm": [150, 195],
            "weight_kg": [45, 95],
            "waist_in": [24, 40],
            "distance_km": [0, 30],
            "nationality": ["IN", "NRI"],
            "religion": ["same", "related"],
        },
    }


# ── Assembly ──────────────────────────────────────────────────────────────


def build_user_row(
    user_id: str,
    city: str,
    gender: str,
    stats: dict[str, Any],
    visions: list[dict[str, Any]],
    activities: dict[str, str],
    journey_state: str = "onboarding",
    bgv_status: str = "declared",
) -> dict[str, Any]:
    """One User table row, in generate_users.to_user_row()'s exact shape.

    journey_state starts at 'onboarding' — the schema's own first state.
    Segment B (BGV) is what moves it to 'dating'; nobody reaches the
    weekly match rotation straight off the sign-up form.
    """
    import json

    stats_all = {
        "city": city,
        "gender": gender,
        "age_band": age_band_for(int(stats["age"])),
        **stats,
    }
    return {
        "id": user_id,
        "journey_state": journey_state,
        "bgv_status": bgv_status,
        "stats_json": json.dumps(stats_all, ensure_ascii=False),
        "vision_json": json.dumps(visions, ensure_ascii=False),
        "skills_json": json.dumps(build_skills(activities), ensure_ascii=False),
        "preferences_json": json.dumps(default_preferences(stats), ensure_ascii=False),
    }


def blank_draft() -> dict[str, Any]:
    """The empty onboarding draft held in the session between steps.

    Nothing is written to the database until the final step, so an
    abandoned sign-up leaves no half-built User row behind.
    """
    return {"email": None, "phone": None, "vision": None, "stats": None, "activities": {}}
