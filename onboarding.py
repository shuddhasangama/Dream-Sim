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

import locale_defaults
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
    KIDS_ROUTES,
    KIDS_STANCES,
    TRAVEL_STYLES,
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


def duplicate_identifier(email: str | None, phone: str | None,
                         taken_emails: set[str] | None = None,
                         taken_phones: set[str] | None = None) -> str | None:
    """Which identifier is already somebody else's, if either is.

    2026-09-09 (evening), user's rule: "Hopefully there are tests to check
    that phone number and emails cannot be duplicate. Or same email or
    phone number not used with different phone number or emails. Avoiding
    duplicates is essential."

    There were no such tests, because there was no such rule — Account
    carried plain indexes on both columns, not unique ones, so nothing
    stopped two accounts sharing either.

    Each identifier is checked INDEPENDENTLY, which is the second half of
    what was asked. Someone who signs up with (E, P) blocks a later (E, Q)
    and a later (F, P) alike: pairing a taken email with a fresh phone
    does not make it fresh.

    Compares normalised values, so "  Foo@Bar.com " and "foo@bar.com" are
    the same address, and +91 98765 43210 and 919876543210 the same
    number. Pass the values normalise_identifiers() returned.

    Returns "email", "phone", or None.
    """
    if email and email in (taken_emails or set()):
        return "email"
    if phone and phone in (taken_phones or set()):
        return "phone"
    return None


DUPLICATE_MESSAGE = {
    "email": "That email address already has an account. Sign in instead, or use another address.",
    "phone": "That phone number already has an account. Sign in instead, or use another number.",
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
# 2026-09-09 (evening): every goal now carries sub-options, so there are
# no "simple" goals left. Kept as an empty tuple rather than deleted so a
# stale import fails loudly rather than silently importing something else.
SIMPLE_GOALS: list[str] = []

# The sub-options each goal carries. ONE table — the form, the validation
# and the payload all read it, so adding a goal's detail is one edit here
# rather than three in step.
DETAILED_GOALS = {
    "Cohabitate": COHABIT_FOCUS,
    "Kids": KIDS_ROUTES,
    "Travel together": TRAVEL_STYLES,
}

# The form field each goal's sub-options arrive under.
DETAIL_FIELD = {
    "Cohabitate": "cohabit_focus",
    "Kids": "kids_route",
    "Travel together": "travel_style",
}

# The question each goal's sub-options answer, on the form.
DETAIL_HINT = {
    "Cohabitate": "What are you actually agreeing about? Pick one or both.",
    "Kids": "How are you open to having them? Pick as many as apply.",
    "Travel together": "What kind of travelling do you mean? Pick as many as apply.",
}

# What to say when a goal is picked with none of its sub-options.
DETAIL_PROMPT = {
    "Cohabitate": "Cohabitating means chores, expenses, or both — say which.",
    "Kids": "Say how you are open to having kids — pick one or more.",
    "Travel together": "Say what kind of travelling you mean — pick one or more.",
}

# Sub-options that carry a prerequisite of their own.
#
# 2026-09-09 (evening), user's rule: "Kids with Surrogacy or Adoption
# doesn't require Physical Intimacy to be Mandatory." The rule was
# attached to the GOAL, which quietly assumed one route to children and
# made the other two unreachable for anyone who had not also ticked
# Physical. It belongs on the sub-option.
NEEDS_PHYSICAL = {"Naturally"}


def _details(**submitted: list[str] | None) -> dict[str, list[str]]:
    """Each goal's sub-options, filtered to values we actually offer."""
    return {
        goal: [o for o in options if o in (submitted.get(DETAIL_FIELD[goal]) or [])]
        for goal, options in DETAILED_GOALS.items()
    }


def selected_goals(other_keys: list[str] | None,
                   details: dict[str, list[str]]) -> list[str]:
    """Which goals are chosen, counting a sub-option as choosing its parent.

    2026-09-09 (evening), user's rule: "Ensure that if sub options are
    chose automatically parent option is chosen across all Visions."
    Ticking "Adoption" and not "Kids" is not an incomplete answer, it is
    an obvious one — and refusing it taught people the form was fussy
    rather than that they had missed something.
    """
    chosen = set(other_keys or [])
    return [k for k in OTHER_VISION_KEYS if k in chosen or details.get(k)]


def validate_vision(
    intimacy_kinds: list[str],
    other_keys: list[str],
    cohabit_focus: list[str] | None = None,
    kids_route: list[str] | None = None,
    travel_style: list[str] | None = None,
) -> dict[str, Any]:
    """Check a submitted vision against the rules above.

    A goal's sub-options are only kept when that goal ends up selected;
    picking a detail and then unticking the goal discards it rather than
    storing a preference for something the user did not choose. But note
    selected_goals(): ticking only the detail SELECTS the goal, so the
    discard applies to unticking, not to never having ticked.
    """
    kinds = [k for k in INTIMACY_KINDS if k in (intimacy_kinds or [])]
    details = _details(cohabit_focus=cohabit_focus, kids_route=kids_route,
                       travel_style=travel_style)
    others = selected_goals(other_keys, details)

    if not kinds:
        return {"ok": False, "error": "Pick at least one kind of intimacy — every vision includes it."}
    if not others:
        return {"ok": False, "error": "Pick at least one more end goal alongside Intimacy."}

    needs_physical = {o for goal in others for o in details[goal]} & NEEDS_PHYSICAL
    if needs_physical and "Physical" not in kinds:
        return {"ok": False,
                "error": "Having kids naturally needs Physical intimacy selected too. "
                         "Add it, or choose surrogacy or adoption instead."}

    for goal in others:
        if not details[goal]:
            return {"ok": False, "error": DETAIL_PROMPT[goal]}

    return {
        "ok": True,
        "error": None,
        "intimacy_kinds": sorted(kinds),
        "other_keys": others,
        "cohabit_focus": sorted(details["Cohabitate"]) if "Cohabitate" in others else [],
        "kids_route": sorted(details["Kids"]) if "Kids" in others else [],
        "travel_style": sorted(details["Travel together"]) if "Travel together" in others else [],
    }


def build_visions(
    intimacy_kinds: list[str],
    other_keys: list[str],
    cohabit_focus: list[str] | None = None,
    kids_route: list[str] | None = None,
    travel_style: list[str] | None = None,
) -> list[dict[str, Any]]:
    """The vision_json payload. Call only after validate_vision() passes."""
    details = _details(cohabit_focus=cohabit_focus, kids_route=kids_route,
                       travel_style=travel_style)
    visions = [{"key": "Intimacy", "stance": sorted(intimacy_kinds)}]
    for key in selected_goals(other_keys, details):
        visions.append({"key": key,
                        "stance": sorted(details[key]) or VISION_STANCE_AT_SIGNUP})
    return visions


# ── Step 2: Stats ─────────────────────────────────────────────────────────
# Field list and value vocabularies are generate_users._generate_stats()'s,
# so a self-registered user is filterable by matching.py on day one.

# 2026-09-04, user's rule: five mandatory fields, everything else optional
# and visibly separated. The sign-up form was asking seventeen questions of
# a stranger who has not yet seen a single match, and the exhaustive list
# is what people abandon.
#
# The five are the ones the product cannot work without: Age and
# Profession are matched on, Nationality and Salary are verified, and
# Education is the one stat almost everyone filters by. Everything else
# earns its place later — see DATE_ALIGNMENT_KEYS, which are asked once
# there is an actual date to align.

NUMERIC_STATS = [
    # key, label, unit, min, max, placeholder
    ("age", "Age", "years", 21, 75, "31"),
]

OPTIONAL_NUMERIC_STATS = [
    ("height_cm", "Height", "cm", 140, 210, "178"),
    ("weight_kg", "Weight", "kg", 40, 150, "74"),
    ("waist_in", "Waist", "in", 20, 55, "32"),
]

CHOICE_STATS = [
    ("education", "Education", EDUCATION),
    ("nationality", "Nationality", OWN_NATIONALITIES),
    ("profession", "Profession", PROFESSIONS),
]

OPTIONAL_CHOICE_STATS = [
    ("diet", "Dietary preference", DIETS),
    ("smoking", "Smoking", SMOKING),
    ("drinking", "Drinking", DRINKING),
    ("fitness_routine", "Fitness routine", FITNESS_ROUTINES),
    ("marital_history", "Marital history", MARITAL_HISTORY),
    ("religion", "Religion", OWN_RELIGIONS),
]

# Asked when a date is being arranged, not at sign-up. Budget only means
# anything once there is a bill to split; diet only once there is a venue
# to pick. Both are still collected — just at the moment they are needed,
# which is also the moment someone is motivated to answer.
DATE_ALIGNMENT_KEYS = ("budget", "diet", "cuisine")

# Multi-select stats. Kept separate from CHOICE_STATS because the form
# posts them as a list and validate_stats has to read them differently —
# collapsing the two would mean a truthy check that silently accepts one
# value where the field means "all of these".
MULTI_STATS: list[tuple[str, str, list[str], str]] = []

OPTIONAL_MULTI_STATS = [
    ("ethnicity", "Ethnicity", ETHNICITIES, "choose up to 2"),
    ("languages", "Languages you speak", LANGUAGES_POOL, "pre-filled from your city"),
    ("cuisine", "Cuisine you enjoy", CUISINES, "used to pick a venue you both eat at"),
    ("budget", "Restaurant budget", RESTAURANT_BUDGETS, "choose one or more acceptable bands"),
]

# budget is what someone spends on one meal out, not what they earn — it
# feeds the date playbook's bill-split clause, where a mismatch actually
# bites. ethnicity is self-declared and NEVER a matching filter: declaring
# your own descent and screening other people by theirs are different
# products, and only the first was asked for. "Prefer not to say" is a
# real answer, so the field is required but never forces a disclosure.

CITIES_FOR_SIGNUP = ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Pune", "Chennai", "Kolkata"]
GENDERS_FOR_SIGNUP = ["female", "male"]

REQUIRED_STAT_KEYS = (
    [k for k, _, _, _, _, _ in NUMERIC_STATS]
    + [k for k, _, _ in CHOICE_STATS]
    + [k for k, _, _, _ in MULTI_STATS]
)

OPTIONAL_STAT_KEYS = (
    [k for k, _, _, _, _, _ in OPTIONAL_NUMERIC_STATS]
    + [k for k, _, _ in OPTIONAL_CHOICE_STATS]
    + [k for k, _, _, _ in OPTIONAL_MULTI_STATS]
)

# Salary is mandatory but never stored raw — only the derived band is.
MANDATORY_FIELD_LABELS = ("Age", "Education", "Nationality", "Salary", "Profession")


# 2026-09-09: the stats editor needs a label and an option list per field.
# DERIVED from the group tuples above rather than retyped, so a field
# added to one of them cannot go missing from the editor — that class of
# hand-kept second list is what let drift-check.sql go stale.

STAT_LABELS: dict[str, str] = {
    **{key: label for key, label, *_ in NUMERIC_STATS + OPTIONAL_NUMERIC_STATS},
    **{key: label for key, label, _opts in CHOICE_STATS + OPTIONAL_CHOICE_STATS},
    **{key: label for key, label, _opts, _hint in MULTI_STATS + OPTIONAL_MULTI_STATS},
    "income_band": "Salary band",
    "budget": "Restaurant budget",
}

STAT_OPTIONS: dict[str, list[str]] = {
    **{key: list(opts) for key, _label, opts in CHOICE_STATS + OPTIONAL_CHOICE_STATS},
    **{key: list(opts) for key, _label, opts, _hint in MULTI_STATS + OPTIONAL_MULTI_STATS},
    "income_band": list(INCOME_BANDS),
    "budget": list(RESTAURANT_BUDGETS),
}

# Fields typed rather than picked, with their bounds — the editor renders
# a number input for these and a select for everything in STAT_OPTIONS.
STAT_RANGES: dict[str, tuple[int, int]] = {
    key: (lo, hi) for key, _label, _unit, lo, hi, _ph
    in NUMERIC_STATS + OPTIONAL_NUMERIC_STATS
}
STAT_UNITS: dict[str, str] = {
    key: unit for key, _label, unit, _lo, _hi, _ph
    in NUMERIC_STATS + OPTIONAL_NUMERIC_STATS
}


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
        if key == "ethnicity" and len(chosen) > 2:
            return {"ok": False, "error": "Ethnicity — choose at most 2.", "stats": None}
        stats[key] = sorted(chosen)

    # ── the optional half ───────────────────────────────────────────────
    # A field left blank is OMITTED, never stored as "" or 0. The absence
    # is load-bearing: REACH offers a lever only for a stat that is
    # actually there, so an empty string would quietly hand someone a
    # filter they never filled in.

    for key, label, unit, low, high, _ph in OPTIONAL_NUMERIC_STATS:
        raw = str(form.get(key, "")).strip()
        if not raw:
            continue
        try:
            value = int(round(float(raw)))
        except ValueError:
            return {"ok": False, "error": f"{label} should be a number, or left blank.", "stats": None}
        if not low <= value <= high:
            return {"ok": False, "error": f"{label} should be between {low} and {high} {unit}.", "stats": None}
        stats[key] = value

    for key, label, options in OPTIONAL_CHOICE_STATS:
        value = str(form.get(key, "")).strip()
        if not value:
            continue
        if value not in options:
            return {"ok": False, "error": f"{label} is not one of the options.", "stats": None}
        stats[key] = value

    for key, label, options, _hint in OPTIONAL_MULTI_STATS:
        raw = form.get(key) or []
        if isinstance(raw, str):
            raw = [raw]
        chosen = [value for value in options if value in raw]
        if key == "ethnicity" and len(chosen) > 2:
            return {"ok": False, "error": "Ethnicity — choose at most 2.", "stats": None}
        if chosen:
            if key == "budget":
                allowed = locale_defaults.budget_bands_for(str(form.get("city", "")).strip())
                chosen = [value for value in allowed if value in chosen]
            stats[key] = sorted(chosen)

    # Budget is a multi-select acceptable range. Keep the city-specific
    # bands authoritative and preserve their canonical order.
    raw_budget = form.get("budget") or []
    if isinstance(raw_budget, str):
        raw_budget = [raw_budget]
    budget_options = locale_defaults.budget_bands_for(str(form.get("city", "")).strip())
    chosen_budget = [value for value in budget_options if value in raw_budget]
    if chosen_budget:
        stats["budget"] = chosen_budget

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
    adjustable: dict[str, Any] = {
        "age": [max(21, age - 6), age + 6],
        # Distance has no backing stat — it is derived from two cities, and
        # city is always given — so it is always available.
        "distance_km": [0, 30],
        "nationality": ["IN", "NRI"],
    }

    # 2026-09-04, user's rule: REACH filters on what you actually keyed in.
    # A lever with no stat behind it is not created, so it cannot be widened,
    # cannot silently exclude anyone, and shows up in REACH as something you
    # unlock by filling the field in. Giving people a height filter when they
    # never told us their height is how a filter ends up meaning nothing.
    for key, default in (("height_cm", [150, 195]),
                         ("weight_kg", [45, 95]),
                         ("waist_in", [24, 40])):
        if stats.get(key) is not None:
            adjustable[key] = default

    if stats.get("religion"):
        adjustable["religion"] = ["same", "related"]

    return {"fixed": {"dealbreakers": []}, "adjustable": adjustable}


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
