"""Flask play-test UI for the DREAM simulation harness.

Local-only manual testing tool: pick a user, act as them, walk the Dating
week, watch REACH's reciprocity read respond to widened filters, and
advance the journey state machine. Reads and writes data/dream.db through
the existing modules (db.py, matching.py, cadence.py, journey.py,
generate_users.py) — this file is glue/presentation only, it never
reimplements their logic.

Run: python app.py   (serves http://localhost:5000)
"""

from __future__ import annotations

import json
import os
import random
import uuid
from datetime import date, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for

import cadence
import calendar_dating
import chemistry
import clock as clock_module
import dateplan
import db
import escalations
import guru_dating
import guru_relationship
import invite_home
import journey
import lockin
import matching
import next_level
import onboarding
import outcomes
import stage_gate
import vision
from generate_users import COHABIT_FOCUS, KIDS_STANCES, from_user_row

APP_DIR = Path(__file__).parent
SIM_STATE_PATH = APP_DIR / "data" / "sim_state.json"

# A fixed epoch so simulated "today" dates are derived from the week
# number, never from the wall clock — journey.py requires an explicit
# `today` and this keeps that reproducible across runs, matching
# docs/CLAUDE.md's "seeded randomness so runs are reproducible" convention.
WEEK_ONE_MONDAY = date(2026, 1, 5)

# ROAD's weekly routine grid — the full 7-day week, distinct from Dating's
# own Fri/Sat/Sun date-slot days (calendar_dating.DAY_SLOTS).
WEEK_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# One-time exceptions to the weekly routine (travel, obligatory visits) are
# CalendarEntry rows — the brief already models these, no new table needed.
EXCEPTION_TYPES = ["obligation", "travel"]
TRAVEL_MODES = ["solo", "partner_solo", "together"]

# The window each day that's ever considered for derived availability —
# an assumption, not something the user specified: nobody's free time is
# computed before 07:00 or after 23:00. Gaps shorter than MIN_GAP_MINUTES
# are dropped as noise (a 5-minute sliver between two routine blocks isn't
# a real offer of availability).
DAY_WINDOW_START = "07:00"
DAY_WINDOW_END = "23:00"
MIN_GAP_MINUTES = 30

ROAD_STEPS = [
    ("routine", "Routine"),
    ("obligations", "Obligations"),
    ("availability", "Availability"),
    ("vision", "Vision"),
]

# Which vision keys get a stance decided here rather than at Dating
# signup, and what the options are for each (generate_users.py's
# KIDS_STANCES/COHABIT_FOCUS — imported below). Travel together has no
# stance in this product, so it's never in this map.
VISION_STANCE_OPTIONS = {
    "Kids": KIDS_STANCES,
    "Cohabitate": COHABIT_FOCUS,
}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or "dream-sim-local-play-test-only"
# SECRET_KEY must be set in Railway. The fallback exists so `python app.py`
# still runs locally; it signs session cookies and is public in this repo,
# so anything deployed without the environment variable is forgeable.


# ── simulation-wide state: the current clock (week + day + hour) ──────────
# Dating's staggered timeline (docs/dating-stage-spec.md §1) needs more than
# a week counter — every user in a city is on the same clock.SimulationClock,
# and what's revealed/open/closed right now depends on day+hour within the
# week, not just which week it is. Replaces the old plain week_number file;
# get_week_number() stays as a thin accessor (clock.week) since ROAD/journey
# code elsewhere only ever needed the week number.

_DEFAULT_CLOCK = {"week": 1, "day": "Mon", "hour": 12}


def get_clock() -> clock_module.SimulationClock:
    if not SIM_STATE_PATH.exists():
        raw = _DEFAULT_CLOCK
    else:
        raw = json.loads(SIM_STATE_PATH.read_text(encoding="utf-8"))
    return clock_module.SimulationClock.at(raw.get("week", 1), raw.get("day", "Mon"), raw.get("hour", 12))


def set_clock(c: clock_module.SimulationClock) -> None:
    SIM_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SIM_STATE_PATH.write_text(json.dumps({"week": c.week, "day": c.day, "hour": c.hour}), encoding="utf-8")


def get_week_number() -> int:
    return get_clock().week


def week_to_date(week_number: int) -> str:
    return (WEEK_ONE_MONDAY + timedelta(weeks=week_number - 1)).isoformat()


def slot_datetime(week: int, day: str, meal_slot: str) -> str:
    """A real ISO date+time for a confirmed (week, day, meal_slot) — the
    one place Dating-stage code touches an actual calendar date, via the
    same WEEK_ONE_MONDAY epoch CalendarEntry/week_to_date() already use.
    Meal slots map to representative hours (breakfast 09:00, lunch 13:00,
    coffee 17:00, dinner 19:30) — illustrative for this simulation, not a
    real venue's opening hours."""
    day_offset = clock_module.DAYS_OF_WEEK.index(day)
    the_date = WEEK_ONE_MONDAY + timedelta(weeks=week - 1, days=day_offset)
    hour = {"breakfast": "09:00", "lunch": "13:00", "coffee": "17:00", "dinner": "19:30"}[meal_slot]
    return f"{the_date.isoformat()}T{hour}"


# ── one sqlite connection per request ──────────────────────────────────────


def get_db():
    if "db" not in g:
        g.db = db.get_connection()
        db.init_db(g.db)
    return g.db


@app.teardown_appcontext
def close_db(_exception=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


# ── cosmetic display names (not part of the data model — generate_users.py
# deliberately has no name field; this is presentation-only, deterministic
# per user_id so the same user always gets the same name) ──────────────────

FIRST_NAMES = {
    "female": ["Priya", "Ananya", "Meera", "Kavya", "Isha", "Riya", "Sneha", "Tara", "Divya", "Neha", "Pooja", "Simran"],
    "male": ["Arjun", "Rohan", "Vikram", "Aditya", "Karan", "Rahul", "Aryan", "Dev", "Nikhil", "Siddharth", "Varun", "Ishaan"],
}
LAST_NAMES = ["Sharma", "Mehta", "Iyer", "Rao", "Kapoor", "Nair", "Reddy", "Bhatt", "Chopra", "Menon", "Gupta", "Desai"]


def display_name(user_id: str, gender: str) -> str:
    rng = random.Random(user_id)
    first = rng.choice(FIRST_NAMES.get(gender, FIRST_NAMES["female"]))
    last = rng.choice(LAST_NAMES)
    return f"{first} {last}"


def with_view_fields(user: dict) -> dict:
    """Attach display-only fields to a generate_users()-shaped dict without
    touching the underlying data."""
    return {**user, "name": display_name(user["user_id"], user["gender"])}


# ── loading users/couples from the DB ──────────────────────────────────────


def load_pool() -> list[dict]:
    return [from_user_row(r) for r in db.fetch_all(get_db(), "User")]


def load_user(user_id: str) -> dict | None:
    row = db.fetch_one(get_db(), "User", id=user_id)
    return from_user_row(row) if row else None


def find_couple_for_user(user_id: str) -> dict | None:
    conn = get_db()
    return db.fetch_one(conn, "Couple", partner_a_id=user_id) or db.fetch_one(conn, "Couple", partner_b_id=user_id)


def partner_id_in(couple: dict, user_id: str) -> str:
    return couple["partner_b_id"] if couple["partner_a_id"] == user_id else couple["partner_a_id"]


def current_user() -> dict | None:
    user_id = session.get("user_id")
    return load_user(user_id) if user_id else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("signup"))
        return view(*args, **kwargs)

    return wrapped


@app.context_processor
def inject_globals():
    user = current_user()
    return {
        "session_user": user,
        "session_user_name": display_name(user["user_id"], user["gender"]) if user else None,
        "week_number": get_week_number(),
        "reach_locked": reach_locked(user) if user else False,
    }


def deterministic_couple_id(user_a_id: str, user_b_id: str) -> str:
    a, b = sorted([user_a_id, user_b_id])
    return f"couple_{a}_{b}"


@app.template_filter("fmtval")
def fmtval(value):
    """Render a whatif lever's from/to value for display: lists join with
    commas, everything else prints as-is."""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return value


def save_preferences(user_id: str, preferences: dict) -> None:
    row = dict(db.fetch_one(get_db(), "User", id=user_id))
    row["preferences_json"] = json.dumps(preferences, ensure_ascii=False)
    db.insert_row(get_db(), "User", row)


def save_visions(user_id: str, visions: list[dict]) -> None:
    row = dict(db.fetch_one(get_db(), "User", id=user_id))
    row["vision_json"] = json.dumps(visions, ensure_ascii=False)
    db.insert_row(get_db(), "User", row)


def get_road(user_id: str, couple_id: str) -> dict:
    """Fetch this user's RoadProfile row, creating an empty one if it's
    somehow missing (journey.advance_stage() seeds it once on Relationship
    entry — self-healing here means a schema change or edge case can never
    leave /road with nothing to render)."""
    row = db.fetch_one(get_db(), "RoadProfile", user_id=user_id, couple_id=couple_id)
    if row is None:
        db.insert_row(
            get_db(),
            "RoadProfile",
            {"id": f"{couple_id}:{user_id}", "user_id": user_id, "couple_id": couple_id, "routine_json": "[]", "availability_json": "[]"},
        )
        row = db.fetch_one(get_db(), "RoadProfile", user_id=user_id, couple_id=couple_id)
    return row


def add_routine_block(user_id: str, couple_id: str, category: str, days: list[str], label: str, start: str, end: str) -> None:
    """category is 'work' or 'fitness' — appends one recurring weekly block
    to the single merged routine list, e.g. {"category": "work",
    "days": ["Mon","Wed"], "label": "Office", "start": "09:00", "end": "18:00"}."""
    row = dict(get_road(user_id, couple_id))
    blocks = db.load_json_field(row["routine_json"], [])
    blocks.append({"id": uuid.uuid4().hex[:8], "category": category, "days": days, "label": label, "start": start, "end": end})
    row["routine_json"] = db.json_field(blocks)
    db.insert_row(get_db(), "RoadProfile", row)


def remove_routine_block(user_id: str, couple_id: str, block_id: str) -> None:
    row = dict(get_road(user_id, couple_id))
    blocks = db.load_json_field(row["routine_json"], [])
    blocks = [b for b in blocks if b["id"] != block_id]
    row["routine_json"] = db.json_field(blocks)
    db.insert_row(get_db(), "RoadProfile", row)


def weekly_grid(blocks: list[dict]) -> dict[str, list[dict]]:
    """Group routine blocks by day, in WEEK_DAYS order, for rendering a
    Mon-Sun grid."""
    grid = {day: [] for day in WEEK_DAYS}
    for block in blocks:
        for day in block["days"]:
            if day in grid:
                grid[day].append(block)
    for day in grid:
        grid[day].sort(key=lambda b: b["start"])
    return grid


def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def derive_availability(routine_blocks: list[dict]) -> dict[str, list[dict]]:
    """This person's free time, per day — from two sources that can be used
    independently or together:

    1. Derived: DAY_WINDOW_START/END minus every work/fitness block
       touching that day. Only computed once at least one work/fitness
       block exists anywhere — if a person hasn't touched Routine at all,
       we deliberately do NOT default to "free all day, every day" (that's
       not a real signal, just an artifact of no data), so this source
       contributes nothing until Routine has something in it.
    2. Declared: "free"-category blocks added directly on the Availability
       step itself (road_availability_add_free) — for someone who wants
       to state exactly when they're free without building out a routine
       first. These always count, with or without a routine.

    The two are unioned per day. Purely computed — never stored — so it's
    always in sync with the current routine/declarations and can't go
    stale. Gaps/windows under MIN_GAP_MINUTES are dropped as noise."""
    busy_blocks = [b for b in routine_blocks if b["category"] != "free"]
    free_blocks = [b for b in routine_blocks if b["category"] == "free"]
    busy_grid = weekly_grid(busy_blocks)
    free_grid = weekly_grid(free_blocks)
    window_start, window_end = _to_minutes(DAY_WINDOW_START), _to_minutes(DAY_WINDOW_END)

    availability: dict[str, list[dict]] = {}
    for day in WEEK_DAYS:
        windows: set[tuple[int, int]] = set()

        if busy_blocks:
            busy = sorted((_to_minutes(b["start"]), _to_minutes(b["end"])) for b in busy_grid[day])
            cursor = window_start
            for busy_start, busy_end in busy:
                if busy_start > cursor:
                    windows.add((cursor, min(busy_start, window_end)))
                cursor = max(cursor, busy_end)
                if cursor >= window_end:
                    break
            if cursor < window_end:
                windows.add((cursor, window_end))

        for b in free_grid[day]:
            windows.add((max(window_start, _to_minutes(b["start"])), min(window_end, _to_minutes(b["end"]))))

        availability[day] = [
            {"day": day, "start": _to_hhmm(s), "end": _to_hhmm(e)}
            for s, e in sorted(windows)
            if e - s >= MIN_GAP_MINUTES
        ]
    return availability


def _slot_key(slot: dict) -> str:
    return f"{slot['day']}|{slot['start']}|{slot['end']}"


def shared_availability_keys(user_id: str, couple_id: str) -> set[str]:
    """Which of this user's currently-derived free-time slots they've
    already chosen to share — validated against the LIVE derivation, so a
    slot that no longer exists (routine changed since it was shared) is
    silently dropped rather than shown as still-shared."""
    road = get_road(user_id, couple_id)
    shared = db.load_json_field(road["availability_json"], [])
    shared_keys = {_slot_key(s) for s in shared}
    live_keys = {_slot_key(s) for day_slots in derive_availability(db.load_json_field(road["routine_json"], [])).values() for s in day_slots}
    return shared_keys & live_keys


def set_shared_availability(user_id: str, couple_id: str, slot_keys: set[str]) -> None:
    """Overwrite the shared subset with exactly the given (day, start, end)
    keys, filtered to slots that actually exist right now — never trusts
    the client for anything beyond which of the live slots to expose."""
    road = dict(get_road(user_id, couple_id))
    live = derive_availability(db.load_json_field(road["routine_json"], []))
    chosen = [slot for day_slots in live.values() for slot in day_slots if _slot_key(slot) in slot_keys]
    road["availability_json"] = db.json_field([{"id": uuid.uuid4().hex[:8], **s} for s in chosen])
    db.insert_row(get_db(), "RoadProfile", road)


def live_shared_slots(user_id: str, couple_id: str) -> list[dict]:
    """This user's currently-shared slots as actual {day,start,end} dicts
    (not just the keys shared_availability_keys() returns), validated
    against the live derivation the same way."""
    road = get_road(user_id, couple_id)
    shared = db.load_json_field(road["availability_json"], [])
    live_keys = {_slot_key(s) for day_slots in derive_availability(db.load_json_field(road["routine_json"], [])).values() for s in day_slots}
    return [s for s in shared if _slot_key(s) in live_keys]


def couple_availability_overlap(couple: dict, user_id: str) -> dict[str, list[dict]]:
    """The actual answer to "when could the two of them go on a date":
    per-day windows where MY shared availability and my partner's shared
    availability overlap in time — not just each person's free time
    listed side by side, the real intersection. This is what ROAD's
    Availability step exists to feed (docs note: Availability -> Dates).
    Empty for a day/entirely until BOTH partners have shared something
    that actually overlaps."""
    partner_id = partner_id_in(couple, user_id)
    mine = live_shared_slots(user_id, couple["id"])
    theirs = live_shared_slots(partner_id, couple["id"])

    by_day_mine: dict[str, list[tuple[int, int]]] = {}
    for s in mine:
        by_day_mine.setdefault(s["day"], []).append((_to_minutes(s["start"]), _to_minutes(s["end"])))
    by_day_theirs: dict[str, list[tuple[int, int]]] = {}
    for s in theirs:
        by_day_theirs.setdefault(s["day"], []).append((_to_minutes(s["start"]), _to_minutes(s["end"])))

    overlap: dict[str, list[dict]] = {}
    for day in WEEK_DAYS:
        windows = set()
        for a_start, a_end in by_day_mine.get(day, []):
            for b_start, b_end in by_day_theirs.get(day, []):
                lo, hi = max(a_start, b_start), min(a_end, b_end)
                if hi - lo >= MIN_GAP_MINUTES:
                    windows.add((lo, hi))
        overlap[day] = [{"day": day, "start": _to_hhmm(s), "end": _to_hhmm(e)} for s, e in sorted(windows)]
    return overlap


def add_exception(couple_id: str, owner_id: str, exc_type: str, title: str, start_date: str, end_date: str, travel_mode: str | None, shared: bool) -> None:
    db.insert_row(
        get_db(),
        "CalendarEntry",
        {
            "id": uuid.uuid4().hex,
            "couple_id": couple_id,
            "owner_id": owner_id,
            "type": exc_type,
            "travel_mode": travel_mode if exc_type == "travel" else None,
            "starts_at": start_date,
            "ends_at": end_date,
            "title": title,
            "shared": int(shared),
        },
    )


# ── / — user picker ─────────────────────────────────────────────────────


@app.route("/pool")
def picker():
    pool = load_pool()
    users = sorted(
        (with_view_fields(u) for u in pool),
        key=lambda u: u["user_id"],
    )
    return render_template("picker.html", users=users)


@app.route("/login/<user_id>", methods=["POST"])
def login(user_id):
    if load_user(user_id) is None:
        abort(404)
    session["user_id"] = user_id
    return redirect(url_for("dashboard"))


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    return redirect(url_for("picker"))


# ── /dashboard ──────────────────────────────────────────────────────────


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    couple = find_couple_for_user(user["user_id"]) if user["journey_state"] != "dating" else None
    return render_template("dashboard.html", user=user, couple=couple)


# ── /reach ──────────────────────────────────────────────────────────────

# REACH is the Dating-stage searching tool — once a couple has actually
# formed, reviewing/widening match filters no longer means anything (per
# docs/agent-1-reach.pdf §5, "REACH sunsets" once locked in). Locked out
# for these journey_states specifically, not just hidden in the nav: the
# routes below refuse to run REACH's math for a user in any of them.
REACH_LOCKED_STATES = {"relationship", "engaged", "married"}


def reach_locked(user: dict) -> bool:
    if user["journey_state"] in REACH_LOCKED_STATES:
        return True
    # docs/dating-stage-spec.md §4/§12: "REACH sunsets at lock-in" — this
    # applies from the moment of mutual lock-in, which happens while
    # journey_state is still 'dating' (the Relationship transition only
    # happens post-date, in outcomes.py) — so the journey_state check
    # above alone isn't enough; also check for an active LockIn.
    return lockin.is_locked_in(user["user_id"], _active_lockins())


# Age/height/weight/waist/distance get a drag-both-ends slider bar instead
# of a one-tap "Widen" card — the person controls min AND max directly.
# Nationality and religion stay as widen cards below the sliders — they're
# the sensitive, user-explored-only levers, never AI-suggested.
SLIDER_LEVERS = [
    {"key": "age", "label": "Age", "unit": "yrs", "min": 18, "max": 70, "step": 1},
    {"key": "height_cm", "label": "Height", "unit": "cm", "min": 140, "max": 210, "step": 1},
    {"key": "weight_kg", "label": "Weight", "unit": "kg", "min": 40, "max": 150, "step": 1},
    {"key": "waist_in", "label": "Waist", "unit": "in", "min": 20, "max": 55, "step": 1},
    {"key": "distance_km", "label": "Distance", "unit": "km", "min": 0, "max": 1600, "step": 10},
]
_SLIDER_KEYS = {s["key"] for s in SLIDER_LEVERS}
_PARTNER_GENDER = {"female": "male", "male": "female"}


def build_sliders(user: dict, pool: list[dict]) -> list[dict]:
    """One entry per SLIDER_LEVERS row: the user's current [min,max], a
    deterministic "recommended range" — the interquartile spread of that
    stat among prospective partners (matching.suggest_range(), population
    percentiles, no LLM call — see that function's docstring) — and,
    where it means something, the user's OWN value for that stat
    (self_value), so the bar shows where they themselves sit while they
    drag the range for a partner. distance_km has neither a population
    "typical value" nor a personal one (it's derived from two people's
    cities, not a stat either one "has"), so both stay None for it."""
    partner_gender = _PARTNER_GENDER[user["gender"]]
    sliders = []
    for spec in SLIDER_LEVERS:
        key = spec["key"]
        suggested = matching.suggest_range(pool, key, gender=partner_gender) if key in matching.RANGE_LEVERS else None
        self_value = user["stats"].get(key) if key in matching.RANGE_LEVERS else None
        sliders.append({**spec, "current": user["preferences"]["adjustable"][key], "suggested": suggested, "self_value": self_value})
    return sliders


@app.route("/reach")
@login_required
def reach():
    user = current_user()
    if reach_locked(user):
        return redirect(url_for("week"))
    pool = load_pool()
    counts = matching.reciprocity_counts(user, pool)
    deltas = [d for d in matching.whatif_deltas(user, pool) if d["lever"] not in _SLIDER_KEYS]
    sliders = build_sliders(user, pool)
    return render_template("reach.html", counts=counts, deltas=deltas, sliders=sliders)


@app.route("/reach/widen", methods=["POST"])
@login_required
def reach_widen():
    user = current_user()
    if reach_locked(user):
        return jsonify({"error": "REACH is locked once you're past Dating"}), 403

    payload = request.get_json(silent=True) or {}
    lever = payload.get("lever")
    if lever not in matching.LEVERS:
        return jsonify({"error": f"unknown lever {lever!r}"}), 400

    pool = load_pool()
    widened = matching.apply_lever_widen(user, lever)
    save_preferences(user["user_id"], widened["preferences"])

    fresh_user = load_user(user["user_id"])
    counts = matching.reciprocity_counts(fresh_user, pool)
    deltas = [d for d in matching.whatif_deltas(fresh_user, pool) if d["lever"] not in _SLIDER_KEYS]
    return jsonify({"counts": counts, "deltas": deltas})


@app.route("/reach/set-range", methods=["POST"])
@login_required
def reach_set_range():
    user = current_user()
    if reach_locked(user):
        return jsonify({"error": "REACH is locked once you're past Dating"}), 403

    payload = request.get_json(silent=True) or {}
    lever = payload.get("lever")
    if lever not in _SLIDER_KEYS:
        return jsonify({"error": f"unknown slider lever {lever!r}"}), 400
    try:
        lo, hi = float(payload.get("min")), float(payload.get("max"))
    except (TypeError, ValueError):
        return jsonify({"error": "min/max must be numbers"}), 400

    pool = load_pool()
    updated = matching.set_range(user, lever, lo, hi)
    save_preferences(user["user_id"], updated["preferences"])

    fresh_user = load_user(user["user_id"])
    counts = matching.reciprocity_counts(fresh_user, pool)
    deltas = [d for d in matching.whatif_deltas(fresh_user, pool) if d["lever"] not in _SLIDER_KEYS]
    return jsonify({"counts": counts, "deltas": deltas})


# ── Dating stage (docs/dating-stage-spec.md) ───────────────────────────────


def _active_lockins() -> list[dict]:
    return db.fetch_all(get_db(), "LockIn", status="active")


def _active_lockin_ids(active: list[dict] | None = None) -> set[str]:
    rows = _active_lockins() if active is None else active
    ids: set[str] = set()
    for row in rows:
        ids.add(row["user_a"])
        ids.add(row["user_b"])
    return ids


def _my_active_lockin(user_id: str, active: list[dict] | None = None) -> dict | None:
    rows = _active_lockins() if active is None else active
    for row in rows:
        if user_id in (row["user_a"], row["user_b"]):
            return row
    return None


def _partner_id_in_lockin(lockin_row: dict, user_id: str) -> str:
    return lockin_row["user_a"] if lockin_row["user_b"] == user_id else lockin_row["user_b"]


def _recent_match_ids(user_id: str, week: int, weeks_back: int = 8) -> set[str]:
    """Every candidate this user has been shown a Match for in the last
    `weeks_back` weeks (docs/dating-stage-spec.md §2's 8-week exclusion)."""
    ids: set[str] = set()
    for w in range(max(1, week - weeks_back), week):
        ids.update(r["candidate_id"] for r in db.fetch_all(get_db(), "Match", user_id=user_id, week=w))
    return ids


def _get_or_generate_matches(user: dict, pool: list[dict], week: int, clock: clock_module.SimulationClock) -> list[dict]:
    """This user's Match rows for `week` — generated ONCE (the first time
    this is called after the week has actually started) and persisted;
    every later call just reads them back, so the set stays fixed for the
    week regardless of later pool changes (cadence.generate_week_matches's
    generate-once model)."""
    existing = db.fetch_all(get_db(), "Match", user_id=user["user_id"], week=week)
    if not existing:
        if clock_module.phase(clock) == "before_week_start":
            return []
        active = _active_lockins()
        generated = cadence.generate_week_matches(
            user, pool, week, _active_lockin_ids(active), _recent_match_ids(user["user_id"], week)
        )
        for m in generated:
            db.insert_row(
                get_db(),
                "Match",
                {
                    "id": f"{user['user_id']}:{week}:{m['slot']}",
                    "user_id": user["user_id"],
                    "candidate_id": m["candidate_id"],
                    "week": week,
                    "slot": m["slot"],
                    "revealed_at": str(m["revealed_at"]),
                    "window_closes_at": str(m["window_closes_at"]),
                },
            )
        existing = db.fetch_all(get_db(), "Match", user_id=user["user_id"], week=week)
    return sorted(existing, key=lambda r: r["slot"])


def _match_status(row: dict, clock: clock_module.SimulationClock) -> str:
    m = {
        "revealed_at": clock_module.SimulationClock.parse(row["week"], row["revealed_at"]),
        "window_closes_at": clock_module.SimulationClock.parse(row["week"], row["window_closes_at"]),
        "action": row["action"],
    }
    return cadence.match_status(m, clock)


def _interested_in_me(user_id: str, week: int) -> set[str]:
    """Real, recorded interest — every user_id whose own Match row already
    has action='interest' pointed at `user_id` this week (§3's
    transparency rule: "if one party expresses interest, the other is
    shown that fact")."""
    rows = db.fetch_all(get_db(), "Match", candidate_id=user_id, week=week, action="interest")
    return {r["user_id"] for r in rows}


def _create_lockin(user_a_id: str, user_b_id: str, week: int, clock: clock_module.SimulationClock) -> dict:
    row = lockin.on_mutual_interest(user_a_id, user_b_id, week, clock)
    lockin_id = f"lockin:{'|'.join(sorted([user_a_id, user_b_id]))}:{week}"
    db.insert_row(get_db(), "LockIn", {"id": lockin_id, **row})

    a_matches = db.fetch_all(get_db(), "Match", user_id=user_a_id, week=week)
    b_matches = db.fetch_all(get_db(), "Match", user_id=user_b_id, week=week)
    clear = lockin.candidates_to_clear(a_matches, b_matches, locked_a_id=user_a_id, locked_b_id=user_b_id)
    for candidate_id in clear["user_a"]:
        match = next(m for m in a_matches if m["candidate_id"] == candidate_id)
        db.delete_row(get_db(), "Match", match["id"])
    for candidate_id in clear["user_b"]:
        match = next(m for m in b_matches if m["candidate_id"] == candidate_id)
        db.delete_row(get_db(), "Match", match["id"])

    return db.fetch_one(get_db(), "LockIn", id=lockin_id)


def _dateplan_for_lockin(lockin_id: str) -> dict | None:
    return db.fetch_one(get_db(), "DatePlan", lockin_id=lockin_id)


# DateOutcome stores each partner's green/red flags as *_flags_json text
# columns; everywhere else in app.py/outcomes.py works with plain
# a_green_flags/a_red_flags/b_green_flags/b_red_flags list keys instead —
# these two helpers are the only place that translates between the two,
# so a row read from the DB, passed through outcomes.py, and written back
# never has to think about (de)serialization itself.
_OUTCOME_FLAG_FIELDS = ("a_green_flags", "a_red_flags", "b_green_flags", "b_red_flags")


def _outcome_from_row(row: dict) -> dict:
    outcome = dict(row)
    for field in _OUTCOME_FLAG_FIELDS:
        outcome[field] = db.load_json_field(outcome.pop(f"{field}_json", None), [])
    return outcome


def _outcome_to_row(outcome: dict) -> dict:
    row = dict(outcome)
    for field in _OUTCOME_FLAG_FIELDS:
        row[f"{field}_json"] = db.json_field(row.pop(field, []))
    row["happened"] = int(row.get("happened", True))
    row["together_photo"] = int(row.get("together_photo", False))
    row["bill_photo"] = int(row.get("bill_photo", False))
    return row


def _bool_ints(row: dict) -> dict:
    """Convert every True/False value in a pure-function's returned dict
    to 1/0 before an insert_row() call — every boolean-shaped column in
    this schema is an INTEGER CHECK (x IN (0,1)), not a real boolean
    type, and sqlite3 would otherwise happily insert a Python bool as
    itself (it's an int subclass) but other code paths that build the
    same row manually (request.form membership checks) already produce
    plain ints, so this keeps both paths consistent."""
    return {k: (int(v) if isinstance(v, bool) else v) for k, v in row.items()}


def _my_role_in_lockin(lockin_row: dict, user_id: str) -> str:
    return "a" if lockin_row["user_a"] == user_id else "b"


def _prerequisites_for_user(user_id: str) -> dict:
    user = load_user(user_id)
    # from_user_row() deliberately pulls city/gender/age_band OUT of
    # "stats" into top-level user fields (matching.py's own established
    # shape) — vision.MANDATORY_STATS_FIELDS' "city" entry means put it
    # back for this one check, not that it's missing from the user.
    stats = {**user["stats"], "city": user["city"]}
    vision_entries = db.fetch_all(get_db(), "VisionEntry", user_id=user_id)
    chemistry_entries = db.fetch_all(get_db(), "ChemistryEntry", user_id=user_id)
    return vision.prerequisites_met(vision_entries, stats, chemistry_entries)


def _prerequisites_for_couple(user_a_id: str, user_b_id: str) -> dict:
    a, b = _prerequisites_for_user(user_a_id), _prerequisites_for_user(user_b_id)
    return {"met": a["met"] and b["met"], "a": a, "b": b}


# Added at StageGate insert time, not by stage_gate.open_gate() itself —
# see schema.sql's own comment on these columns for why.
_GATE_FLAG_DEFAULTS = {
    "confirm_a": 0, "confirm_b": 0,
    "exclusivity_ack_a": 0, "exclusivity_ack_b": 0,
    "consent_a": 0, "consent_b": 0,
    "biometric_a": 0, "biometric_b": 0,
}


def _auto_resolve_stale_outcome(lockin_row: dict, plan: dict, clock: clock_module.SimulationClock) -> dict:
    """If we've rolled into a later week than the date's own and one side
    never recorded a post-date decision, treat them as ghosted (§9: "no
    response by close ... counts toward compliance") and resolve — a lazy
    check run whenever the locked-in pair's week view loads, so nothing
    needs a background job. Returns the (possibly updated) LockIn row."""
    if plan["status"] != "confirmed" or lockin_row["week"] >= clock.week:
        return lockin_row

    existing = db.fetch_one(get_db(), "DateOutcome", dateplan_id=plan["id"])
    outcome = _outcome_from_row(existing) if existing else outcomes.record_outcome(plan["id"], True, None, None)
    outcome.setdefault("id", f"outcome:{plan['id']}")

    newly_ghosted = []
    for role, uid in (("a", lockin_row["user_a"]), ("b", lockin_row["user_b"])):
        if outcome.get(f"{role}_decision") is None:
            outcome[f"{role}_decision"] = "ghosted"
            newly_ghosted.append(uid)
    if not newly_ghosted:
        return lockin_row

    db.insert_row(get_db(), "DateOutcome", _outcome_to_row(outcome))
    for uid in newly_ghosted:
        db.insert_row(
            get_db(),
            "ComplianceEvent",
            {"id": uuid.uuid4().hex[:8], "user_id": uid, "type": "no_show", "week": lockin_row["week"], "notes": "no post-date response"},
        )

    result = outcomes.apply_resolution(outcome)
    if result["release_lockin"]:
        released = lockin.release(lockin_row, result["release_reason"])
        db.insert_row(get_db(), "LockIn", {**lockin_row, **released})
        return db.fetch_one(get_db(), "LockIn", id=lockin_row["id"])
    return lockin_row


@app.route("/week")
@login_required
def week():
    user = current_user()
    clock = get_clock()
    week_number = clock.week

    if user["journey_state"] != "dating":
        couple = find_couple_for_user(user["user_id"])
        partner = load_user(partner_id_in(couple, user["user_id"])) if couple else None
        return render_template(
            "week.html", mode="post_dating", couple=couple, partner=with_view_fields(partner) if partner else None
        )

    active = _my_active_lockin(user["user_id"])
    if active is not None:
        plan = _dateplan_for_lockin(active["id"])
        if plan is not None:
            active = _auto_resolve_stale_outcome(active, plan, clock)
        if active["status"] != "active":
            # just got released/completed by the lazy check above — treat
            # as "not locked in" for this render, matches will regenerate
            active = None

    if active is not None:
        partner = with_view_fields(load_user(_partner_id_in_lockin(active, user["user_id"])))
        plan = _dateplan_for_lockin(active["id"])
        outcome_row = db.fetch_one(get_db(), "DateOutcome", dateplan_id=plan["id"]) if plan else None
        outcome = _outcome_from_row(outcome_row) if outcome_row else None
        my_role = "a" if active["user_a"] == user["user_id"] else "b"
        return render_template(
            "week.html",
            mode="locked_in",
            partner=partner,
            lockin=active,
            plan=plan,
            green_flags=guru_dating.GREEN_FLAGS,
            red_flags=guru_dating.RED_FLAGS,
            outcome=outcome,
            my_role=my_role,
            phase=clock_module.phase(clock),
            clock=clock,
        )

    pool = load_pool()
    rows = _get_or_generate_matches(user, pool, week_number, clock)
    already_interested = _interested_in_me(user["user_id"], week_number)

    slots = []
    for row in rows:
        candidate = load_user(row["candidate_id"])
        if candidate is None:
            continue
        slots.append(
            {
                "row": row,
                "status": _match_status(row, clock),
                "candidate": with_view_fields(candidate),
                "their_interest_real": row["candidate_id"] in already_interested,
            }
        )

    return render_template("week.html", mode="dating", clock=clock, phase=clock_module.phase(clock), slots=slots)


@app.route("/week/act", methods=["POST"])
@login_required
def week_act():
    user = current_user()
    clock = get_clock()
    action = request.form.get("action")
    if action not in ("interest", "pass"):
        abort(400)

    match_id = request.form.get("match_id")
    row = db.fetch_one(get_db(), "Match", id=match_id) if match_id else None
    if row is None or row["user_id"] != user["user_id"] or _match_status(row, clock) != "open":
        return redirect(url_for("week"))

    updated = dict(row)
    updated["action"] = action
    updated["pass_reason"] = (request.form.get("pass_reason") or "").strip() or None if action == "pass" else None
    db.insert_row(get_db(), "Match", updated)

    if action == "interest":
        candidate_id = row["candidate_id"]
        their_row = db.fetch_one(get_db(), "Match", user_id=candidate_id, candidate_id=user["user_id"], week=row["week"])
        if their_row is not None and their_row["action"] == "interest":
            # mutual — §4's pivotal event: short-circuits the week for
            # both, clears every other candidate, opens the calendar.
            _create_lockin(user["user_id"], candidate_id, row["week"], clock)

    return redirect(url_for("week"))


# ── Dating calendar (docs/dating-stage-spec.md §5) ─────────────────────────


@app.route("/calendar")
@login_required
def calendar_view():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    if _dateplan_for_lockin(active["id"]) is not None:
        return redirect(url_for("plan_view"))  # slot already confirmed

    partner_id = _partner_id_in_lockin(active, user["user_id"])
    partner = with_view_fields(load_user(partner_id))
    my_slots = {(r["day"], r["meal_slot"]) for r in db.fetch_all(get_db(), "Availability", lockin_id=active["id"], user_id=user["user_id"])}
    their_rows = db.fetch_all(get_db(), "Availability", lockin_id=active["id"], user_id=partner_id)
    their_slots = [(r["day"], r["meal_slot"]) for r in their_rows]
    overlap = calendar_dating.compute_overlap(list(my_slots), their_slots) if their_rows else []

    return render_template(
        "calendar.html",
        partner=partner,
        valid_slots=calendar_dating.valid_slots(),
        my_slots=my_slots,
        their_submitted=bool(their_rows),
        overlap=overlap,
    )


@app.route("/calendar/submit", methods=["POST"])
@login_required
def calendar_submit():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))

    valid = set(calendar_dating.valid_slots())
    chosen = set()
    for raw in request.form.getlist("slot"):
        day, _, meal = raw.partition("|")
        if (day, meal) in valid:
            chosen.add((day, meal))

    for row in db.fetch_all(get_db(), "Availability", lockin_id=active["id"], user_id=user["user_id"]):
        db.delete_row(get_db(), "Availability", row["id"])
    for day, meal in chosen:
        db.insert_row(
            get_db(), "Availability",
            {"id": uuid.uuid4().hex[:8], "lockin_id": active["id"], "user_id": user["user_id"], "day": day, "meal_slot": meal},
        )
    return redirect(url_for("calendar_view"))


@app.route("/calendar/confirm", methods=["POST"])
@login_required
def calendar_confirm():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))

    day, meal = request.form.get("day"), request.form.get("meal_slot")
    if (day, meal) not in set(calendar_dating.valid_slots()):
        abort(400)

    partner = load_user(_partner_id_in_lockin(active, user["user_id"]))
    venue = calendar_dating.suggest_venue(day, meal, user["stats"]["diet"], partner["stats"]["diet"])
    plan = dateplan.generate_plan(
        lockin_id=active["id"],
        confirmed_slot={"day": day, "meal_slot": meal},
        venue=venue,
        datetime_str=slot_datetime(active["week"], day, meal),
        bill_split="pay-your-own",
        selections_a={},
        selections_b={},
    )
    db.insert_row(
        get_db(), "DatePlan",
        {
            "id": f"plan:{active['id']}",
            **{k: v for k, v in plan.items() if k not in ("selections_a_json", "selections_b_json")},
            "selections_a_json": db.json_field(plan["selections_a_json"]),
            "selections_b_json": db.json_field(plan["selections_b_json"]),
        },
    )
    return redirect(url_for("plan_view"))


@app.route("/calendar/no-overlap", methods=["POST"])
@login_required
def calendar_no_overlap():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))

    if request.form.get("choice") == "return_to_pool":
        released = lockin.release(active, "no calendar overlap")
        db.insert_row(get_db(), "LockIn", {**active, **released})
        return redirect(url_for("week"))

    # "Offer next weekend": Fri/Sat/Sun are the only slot labels that
    # exist (calendar_dating has no separate week axis), so both partners
    # simply get a clean slate to try different picks — the LockIn itself
    # stays active.
    for owner_id in (active["user_a"], active["user_b"]):
        for row in db.fetch_all(get_db(), "Availability", lockin_id=active["id"], user_id=owner_id):
            db.delete_row(get_db(), "Availability", row["id"])
    return redirect(url_for("calendar_view"))


# ── Date plan & signing (docs/dating-stage-spec.md §6-8) ───────────────────


@app.route("/plan")
@login_required
def plan_view():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    plan = _dateplan_for_lockin(active["id"])
    if plan is None:
        return redirect(url_for("calendar_view"))

    partner_id = _partner_id_in_lockin(active, user["user_id"])
    partner = with_view_fields(load_user(partner_id))
    my_role = "a" if active["user_a"] == user["user_id"] else "b"
    partner_role = "b" if my_role == "a" else "a"
    my_selections = db.load_json_field(plan[f"selections_{my_role}_json"], {})
    partner_selections = db.load_json_field(plan[f"selections_{partner_role}_json"], {})

    signatures = db.fetch_all(get_db(), "Signature", dateplan_id=plan["id"])
    my_signature = next((s for s in signatures if s["user_id"] == user["user_id"]), None)
    confirmed = dateplan.is_confirmed(signatures, active["user_a"], active["user_b"])
    briefing = guru_dating.pre_date_briefing(partner_selections.get("greeting"))

    return render_template(
        "plan.html",
        partner=partner,
        plan=plan,
        my_selections=my_selections,
        my_signature=my_signature,
        confirmed=confirmed,
        briefing=briefing,
        ack_fields=dateplan.ACK_FIELDS,
        bill_split_labels=dateplan.BILL_SPLIT_LABELS,
        phase=clock_module.phase(get_clock()),
    )


@app.route("/plan/selections", methods=["POST"])
@login_required
def plan_selections():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    plan = _dateplan_for_lockin(active["id"])
    if plan is None:
        return redirect(url_for("calendar_view"))

    my_role = "a" if active["user_a"] == user["user_id"] else "b"
    selections = {
        "greeting": request.form.get("greeting"),
        "dietary": request.form.get("dietary"),
        "dress": request.form.get("dress"),
    }
    updated = dict(plan)
    updated[f"selections_{my_role}_json"] = db.json_field(selections)
    # Bill split isn't a per-partner selection any more — it's part of the
    # auto-filled "rules of engagement" (cuisine/budget/split), set once
    # at calendar_confirm() time and never hand-edited here.
    db.insert_row(get_db(), "DatePlan", updated)
    return redirect(url_for("plan_view"))


@app.route("/plan/sign", methods=["POST"])
@login_required
def plan_sign():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    plan = _dateplan_for_lockin(active["id"])
    if plan is None:
        return redirect(url_for("calendar_view"))

    ack_flags = {f: (f in request.form) for f in dateplan.ACK_FIELDS}
    clock = get_clock()
    # First attempt is deterministic (verify_face()'s own default seed);
    # a retry — signaled by an existing Signature row for this plan/user,
    # which a failed attempt already inserts with face_verified=0 — gets a
    # fresh random seed each time. Previously this reused a hardcoded
    # "attempt=2" from the retry form forever, so a user whose first TWO
    # attempts both happened to land on the stub's failure branch could
    # never get past it — every retry recomputed the exact same outcome.
    already_tried = db.fetch_one(get_db(), "Signature", dateplan_id=plan["id"], user_id=user["user_id"])
    seed = uuid.uuid4().hex if already_tried is not None else None
    face_verified = dateplan.verify_face(user["user_id"], seed=seed)
    sig = dateplan.sign(plan["id"], user["user_id"], ack_flags, signed_at=str(clock), face_verified=face_verified)
    db.insert_row(
        get_db(), "Signature",
        {"id": f"{plan['id']}:{user['user_id']}", **{k: (int(v) if isinstance(v, bool) else v) for k, v in sig.items()}},
    )

    signatures = db.fetch_all(get_db(), "Signature", dateplan_id=plan["id"])
    if dateplan.is_confirmed(signatures, active["user_a"], active["user_b"]) and plan["status"] != "confirmed":
        db.insert_row(get_db(), "DatePlan", {**plan, "status": "confirmed"})

    return redirect(url_for("plan_view"))


@app.route("/plan/feedback/flags", methods=["POST"])
@login_required
def plan_feedback_flags():
    """Step 1 of feedback — mandatory, before either the accept/reject
    decision or the other partner sees anything (2026-08-28, user's
    explicit rule: "immaterial of a lock-in or pass... journey of
    improvement"). Green flags (exactly guru_dating.MIN..MAX_GREEN_FLAGS,
    currently 2) are required; red flags and the together/bill photo
    consent toggles are optional. Not gated on clock phase beyond the
    plan being confirmed — the date having actually happened is what
    matters, not which exact hour it is."""
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    plan = _dateplan_for_lockin(active["id"])
    if plan is None or plan["status"] != "confirmed":
        return redirect(url_for("week"))

    captured = guru_dating.capture_flags(request.form.getlist("green_flags"), request.form.getlist("red_flags"))
    if not captured["meets_minimum"]:
        return redirect(url_for("week"))

    my_role = "a" if active["user_a"] == user["user_id"] else "b"
    existing = db.fetch_one(get_db(), "DateOutcome", dateplan_id=plan["id"])
    outcome = _outcome_from_row(existing) if existing else outcomes.record_outcome(plan["id"], True, None, None)
    outcome.setdefault("id", f"outcome:{plan['id']}")
    outcome[f"{my_role}_green_flags"] = captured["green"]
    outcome[f"{my_role}_red_flags"] = captured["red"]
    # Together/bill photo are shared consent flags, not per-partner —
    # either side marking it as taken counts, matches together_photo/
    # bill_photo's schema (no a_/b_ prefix, unlike everything else here).
    outcome["together_photo"] = outcome.get("together_photo", False) or ("together_photo" in request.form)
    outcome["bill_photo"] = outcome.get("bill_photo", False) or ("bill_photo" in request.form)
    db.insert_row(get_db(), "DateOutcome", _outcome_to_row(outcome))

    return redirect(url_for("week"))


@app.route("/plan/feedback", methods=["POST"])
@login_required
def plan_feedback():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    plan = _dateplan_for_lockin(active["id"])
    if plan is None or plan["status"] != "confirmed":
        return redirect(url_for("week"))

    decision = request.form.get("decision")
    if decision not in ("continue", "relationship", "pass"):
        abort(400)
    reason = guru_dating.capture_pass_reason(request.form.get("reason"))["reason"] if decision == "pass" else None

    my_role = "a" if active["user_a"] == user["user_id"] else "b"
    existing = db.fetch_one(get_db(), "DateOutcome", dateplan_id=plan["id"])
    outcome = _outcome_from_row(existing) if existing else outcomes.record_outcome(plan["id"], True, None, None)
    outcome.setdefault("id", f"outcome:{plan['id']}")
    # Flag feedback is mandatory and comes first — refuse a decision
    # recorded without it, not just hidden in the UI.
    if len(outcome.get(f"{my_role}_green_flags", [])) < guru_dating.MIN_GREEN_FLAGS:
        return redirect(url_for("week"))
    outcome[f"{my_role}_decision"] = decision
    outcome[f"{my_role}_reason"] = reason
    db.insert_row(get_db(), "DateOutcome", _outcome_to_row(outcome))

    result = outcomes.apply_resolution(outcome)

    # dates_completed only ever advances once both halves of a date-cycle
    # are in (result["resolution"] != "pending" means exactly that) — it
    # feeds escalations.unlocks_available() and stage_gate's own B1
    # eligibility, so it has to be current before either of those get
    # checked, regardless of which branch below fires.
    if result["resolution"] != "pending":
        active = dict(active)
        active.update(lockin.increment_dates_completed(active))
        db.insert_row(get_db(), "LockIn", active)

    if result["advance_to_relationship"]:
        # Both partners picking "relationship" no longer creates the
        # Couple directly — it opens the Dating exit / Relationship entry
        # gate (docs/relationship-stage-spec.md Part B); the LockIn stays
        # 'active' (not completed) until journey.enter_relationship()
        # actually succeeds at the end of that sequence. One open gate
        # per LockIn — re-use it if one's already there (e.g. a re-raised
        # StageGate from a prior "relationship" pick that got declined at
        # step 4 and the couple later changed their minds).
        existing_gate = db.fetch_one(get_db(), "StageGate", pair_id=active["id"])
        if existing_gate is None:
            gate = stage_gate.open_gate(active["id"], "exclusivity_raised", str(get_clock()))
            db.insert_row(get_db(), "StageGate", {"id": f"gate:{active['id']}", **gate, **_GATE_FLAG_DEFAULTS})
        return redirect(url_for("gate_view"))
    elif result["release_lockin"]:
        db.insert_row(get_db(), "LockIn", {**active, **lockin.release(active, result["release_reason"])})
    elif result["continue_dating"]:
        # Accept — keep dating: the LockIn stays exactly as it is (still
        # 'active', REACH still sunset for both). This date instance is
        # done, so its DatePlan/Signature/DateOutcome rows are cleared —
        # DatePlan's id is deterministic per lockin_id (f"plan:{lockin_id}"),
        # so leaving the old row behind would make the next
        # calendar_confirm() collide with stale signatures that were never
        # actually re-signed for the new date. Availability rows are
        # cleared too, so /calendar starts clean for the next date.
        db.delete_row(get_db(), "Signature", f"{plan['id']}:{active['user_a']}")
        db.delete_row(get_db(), "Signature", f"{plan['id']}:{active['user_b']}")
        db.delete_row(get_db(), "DateOutcome", outcome["id"])
        db.delete_row(get_db(), "DatePlan", plan["id"])
        for row in db.fetch_all(get_db(), "Availability", lockin_id=active["id"]):
            db.delete_row(get_db(), "Availability", row["id"])

    return redirect(url_for("week"))


# ── Contact exchange / invite home (docs/relationship-stage-spec.md Part A,
#    docs/intimacy-expectations-spec.md Part C) ─────────────────────────────


@app.route("/escalations")
@login_required
def escalations_view():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    if not escalations.unlocks_available(active["dates_completed"]):
        return render_template("escalations.html", unlocked=False, dates_completed=active["dates_completed"])

    partner_id = _partner_id_in_lockin(active, user["user_id"])
    partner = with_view_fields(load_user(partner_id))

    contact_requests = db.fetch_all(get_db(), "ContactRequest", pair_id=active["id"])
    my_sent = [r for r in contact_requests if r["requester_id"] == user["user_id"]]
    their_sent = [r for r in contact_requests if r["requester_id"] == partner_id]

    invites = db.fetch_all(get_db(), "HomeInvite", pair_id=active["id"])
    invite = invites[-1] if invites else None  # only one pending/accepted at a time by design

    return render_template(
        "escalations.html",
        unlocked=True,
        partner=partner,
        channels=escalations.CONTACT_CHANNELS,
        my_sent=my_sent,
        their_sent=their_sent,
        contact_status=escalations.contact_status_for_requester,
        invite=invite,
        invite_status=invite_home.status_for_requester,
        expectation_flags=invite_home.EXPECTATION_FLAGS,
        expectation_copy=invite_home.EXPECTATION_FLAG_COPY,
        rules_of_engagement=invite_home.RULES_OF_ENGAGEMENT,
        guidance=invite_home.INTIMACY_EXPECTED_GUIDANCE,
        my_role=_my_role_in_lockin(active, user["user_id"]),
        my_user_id=user["user_id"],
        lockin_week=active["week"],
    )


@app.route("/escalations/contact/request", methods=["POST"])
@login_required
def escalations_contact_request():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None or not escalations.unlocks_available(active["dates_completed"]):
        return redirect(url_for("escalations_view"))
    channel = request.form.get("channel")
    existing = db.fetch_all(get_db(), "ContactRequest", pair_id=active["id"], channel=channel) if channel in escalations.CONTACT_CHANNELS else []
    try:
        row = escalations.request_contact(active["id"], user["user_id"], channel, active["week"], str(get_clock()), existing)
    except ValueError:
        return redirect(url_for("escalations_view"))
    db.insert_row(get_db(), "ContactRequest", {"id": uuid.uuid4().hex[:12], **row})
    return redirect(url_for("escalations_view"))


@app.route("/escalations/contact/respond", methods=["POST"])
@login_required
def escalations_contact_respond():
    user = current_user()
    row = db.fetch_one(get_db(), "ContactRequest", id=request.form.get("request_id"))
    if row is None or row["requester_id"] == user["user_id"]:
        return redirect(url_for("escalations_view"))
    try:
        updated = escalations.respond_to_contact_request(row, request.form.get("response"), str(get_clock()))
    except ValueError:
        return redirect(url_for("escalations_view"))
    db.insert_row(get_db(), "ContactRequest", updated)
    return redirect(url_for("escalations_view"))


@app.route("/escalations/invite/propose", methods=["POST"])
@login_required
def escalations_invite_propose():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None or not escalations.unlocks_available(active["dates_completed"]):
        return redirect(url_for("escalations_view"))
    proposed_datetime = request.form.get("proposed_datetime")
    if not proposed_datetime:
        return redirect(url_for("escalations_view"))
    existing = db.fetch_all(get_db(), "HomeInvite", pair_id=active["id"])
    try:
        row = invite_home.propose_invite(active["id"], user["user_id"], proposed_datetime, request.form.get("expectation_flag"), existing)
    except ValueError:
        return redirect(url_for("escalations_view"))
    db.insert_row(get_db(), "HomeInvite", {"id": uuid.uuid4().hex[:12], **_bool_ints(row)})
    return redirect(url_for("escalations_view"))


@app.route("/escalations/invite/see-flag", methods=["POST"])
@login_required
def escalations_invite_see_flag():
    invite = db.fetch_one(get_db(), "HomeInvite", id=request.form.get("invite_id"))
    if invite is None:
        return redirect(url_for("escalations_view"))
    updated = invite_home.mark_flag_seen(invite, str(get_clock()))
    db.insert_row(get_db(), "HomeInvite", updated)
    return redirect(url_for("escalations_view"))


@app.route("/escalations/invite/respond", methods=["POST"])
@login_required
def escalations_invite_respond():
    invite = db.fetch_one(get_db(), "HomeInvite", id=request.form.get("invite_id"))
    if invite is None:
        return redirect(url_for("escalations_view"))
    try:
        updated = invite_home.respond_to_invite(invite, request.form.get("response"))
    except ValueError:
        return redirect(url_for("escalations_view"))
    db.insert_row(get_db(), "HomeInvite", updated)
    return redirect(url_for("escalations_view"))


@app.route("/escalations/invite/guidance", methods=["POST"])
@login_required
def escalations_invite_guidance():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    invite = db.fetch_one(get_db(), "HomeInvite", id=request.form.get("invite_id"))
    if invite is None or active is None:
        return redirect(url_for("escalations_view"))
    try:
        updated = invite_home.show_guidance(invite, _my_role_in_lockin(active, user["user_id"]))
    except ValueError:
        return redirect(url_for("escalations_view"))
    db.insert_row(get_db(), "HomeInvite", updated)
    return redirect(url_for("escalations_view"))


@app.route("/escalations/invite/acknowledge", methods=["POST"])
@login_required
def escalations_invite_acknowledge():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    invite = db.fetch_one(get_db(), "HomeInvite", id=request.form.get("invite_id"))
    if invite is None or active is None:
        return redirect(url_for("escalations_view"))
    party = _my_role_in_lockin(active, user["user_id"])
    face_verified = dateplan.verify_face(user["user_id"], seed=uuid.uuid4().hex)
    try:
        updated = invite_home.acknowledge(invite, party, face_verified)
    except ValueError:
        return redirect(url_for("escalations_view"))
    db.insert_row(get_db(), "HomeInvite", _bool_ints(updated))
    return redirect(url_for("escalations_view"))


@app.route("/escalations/invite/trusted-contact", methods=["POST"])
@login_required
def escalations_invite_trusted_contact():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    invite = db.fetch_one(get_db(), "HomeInvite", id=request.form.get("invite_id"))
    if invite is None or active is None:
        return redirect(url_for("escalations_view"))
    updated = invite_home.notify_trusted_contact(invite, _my_role_in_lockin(active, user["user_id"]))
    db.insert_row(get_db(), "HomeInvite", updated)
    return redirect(url_for("escalations_view"))


@app.route("/escalations/invite/revoke", methods=["POST"])
@login_required
def escalations_invite_revoke():
    user = current_user()
    invite = db.fetch_one(get_db(), "HomeInvite", id=request.form.get("invite_id"))
    if invite is None:
        return redirect(url_for("escalations_view"))
    updated = invite_home.revoke(invite, user["user_id"], str(get_clock()))
    db.insert_row(get_db(), "HomeInvite", updated)
    return redirect(url_for("escalations_view"))


# ── Dating exit / Relationship entry gate (docs/relationship-stage-spec.md
#    Part B) ──────────────────────────────────────────────────────────────


def _gate_for_lockin(lockin_id: str) -> dict | None:
    return db.fetch_one(get_db(), "StageGate", pair_id=lockin_id)


def _gate_analysis_for(pair_id: str) -> dict | None:
    row = db.fetch_one(get_db(), "GateAnalysis", pair_id=pair_id)
    if row is None:
        return None
    return {
        "pair_id": row["pair_id"],
        "divergences": db.load_json_field(row["divergences_json"], []),
        "must_resolve": db.load_json_field(row["must_resolve_json"], []),
        "guru_prompts": db.load_json_field(row["guru_prompts_json"], []),
    }


def _maybe_compute_gate_analysis(gate: dict, active: dict) -> None:
    """Once both partners have answered every stage-gate question, run
    stage_gate.analyze_gate() once and persist it — idempotent and cheap
    enough to call on every /gate page load rather than needing its own
    background trigger."""
    if _gate_analysis_for(gate["pair_id"]) is not None:
        return
    responses_a = db.fetch_all(get_db(), "GateResponse", pair_id=gate["pair_id"], user_id=active["user_a"])
    responses_b = db.fetch_all(get_db(), "GateResponse", pair_id=gate["pair_id"], user_id=active["user_b"])
    if not (stage_gate.all_questions_answered(responses_a) and stage_gate.all_questions_answered(responses_b)):
        return
    analysis = stage_gate.analyze_gate(gate["pair_id"], responses_a, responses_b)
    db.insert_row(
        get_db(), "GateAnalysis",
        {
            "id": f"analysis:{gate['pair_id']}",
            "pair_id": gate["pair_id"],
            "divergences_json": db.json_field(analysis["divergences"]),
            "must_resolve_json": db.json_field(analysis["must_resolve"]),
            "guru_prompts_json": db.json_field(analysis["guru_prompts"]),
        },
    )


@app.route("/gate")
@login_required
def gate_view():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    gate = _gate_for_lockin(active["id"])
    if gate is None:
        return render_template("gate.html", gate=None, lockin=active)

    my_role = _my_role_in_lockin(active, user["user_id"])
    partner_role = "b" if my_role == "a" else "a"
    partner_id = _partner_id_in_lockin(active, user["user_id"])
    partner = with_view_fields(load_user(partner_id))

    my_responses = db.fetch_all(get_db(), "GateResponse", pair_id=gate["pair_id"], user_id=user["user_id"])
    partner_responses = db.fetch_all(get_db(), "GateResponse", pair_id=gate["pair_id"], user_id=partner_id)
    if gate["status"] == "open":
        _maybe_compute_gate_analysis(gate, active)
    analysis = _gate_analysis_for(gate["pair_id"])

    answered_keys = {r["question_key"] for r in my_responses}
    next_question = next((q for q in stage_gate.STAGE_GATE_QUESTIONS if q["key"] not in answered_keys), None)
    both_answered = stage_gate.all_questions_answered(my_responses) and stage_gate.all_questions_answered(partner_responses)
    has_mismatch = stage_gate.has_unresolved_exclusivity_mismatch(analysis) if analysis else False

    prerequisites = None
    if analysis is not None and gate[f"confirm_{my_role}"] and gate[f"confirm_{partner_role}"] and not has_mismatch:
        prerequisites = _prerequisites_for_couple(active["user_a"], active["user_b"])

    return render_template(
        "gate.html",
        gate=gate,
        lockin=active,
        partner=partner,
        my_role=my_role,
        questions=stage_gate.STAGE_GATE_QUESTIONS,
        answered_keys=answered_keys,
        next_question=next_question,
        both_answered=both_answered,
        analysis=analysis,
        has_mismatch=has_mismatch,
        prerequisites=prerequisites,
    )


@app.route("/gate/raise", methods=["POST"])
@login_required
def gate_raise():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    if _gate_for_lockin(active["id"]) is None:
        gate = stage_gate.open_gate(active["id"], "exclusivity_raised", str(get_clock()))
        db.insert_row(get_db(), "StageGate", {"id": f"gate:{active['id']}", **gate, **_GATE_FLAG_DEFAULTS})
    return redirect(url_for("gate_view"))


@app.route("/gate/answer", methods=["POST"])
@login_required
def gate_answer():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    gate = _gate_for_lockin(active["id"])
    if gate is None or gate["status"] != "open":
        return redirect(url_for("gate_view"))

    question_key = request.form.get("question_key")
    question = next((q for q in stage_gate.STAGE_GATE_QUESTIONS if q["key"] == question_key), None)
    if question is None:
        abort(400)
    kwargs: dict = {}
    if question["kind"] == "scale":
        kwargs["readiness_scale"] = request.form.get("readiness_scale") or None
    else:
        kwargs["answer_text"] = (request.form.get("answer_text") or "").strip() or None
    try:
        response = stage_gate.submit_gate_response(gate["pair_id"], user["user_id"], question_key, **kwargs)
    except ValueError:
        return redirect(url_for("gate_view"))
    db.insert_row(get_db(), "GateResponse", {"id": f"{gate['pair_id']}:{user['user_id']}:{question_key}", **response})
    return redirect(url_for("gate_view"))


@app.route("/gate/confirm", methods=["POST"])
@login_required
def gate_confirm():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    gate = _gate_for_lockin(active["id"])
    if gate is None:
        return redirect(url_for("week"))
    updated = dict(gate)
    updated[f"confirm_{_my_role_in_lockin(active, user['user_id'])}"] = 1
    db.insert_row(get_db(), "StageGate", updated)
    return redirect(url_for("gate_view"))


@app.route("/gate/decline", methods=["POST"])
@login_required
def gate_decline():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    gate = _gate_for_lockin(active["id"])
    if gate is None:
        return redirect(url_for("week"))
    db.insert_row(get_db(), "StageGate", stage_gate.resolve_gate(gate, "declined", str(get_clock())))
    return redirect(url_for("week"))


@app.route("/gate/exclusivity-ack", methods=["POST"])
@login_required
def gate_exclusivity_ack():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    gate = _gate_for_lockin(active["id"])
    if gate is None:
        return redirect(url_for("week"))
    updated = dict(gate)
    updated[f"exclusivity_ack_{_my_role_in_lockin(active, user['user_id'])}"] = 1
    db.insert_row(get_db(), "StageGate", updated)
    return redirect(url_for("gate_view"))


@app.route("/gate/consent", methods=["POST"])
@login_required
def gate_consent():
    """Consent block, signed independently per partner, face-verified
    (B2 step 7) — a single attempt per click, same verify_face() stub as
    everywhere else in this project; unlike /plan/sign there's no
    hardcoded-attempt bug to guard against here since this route never
    reuses a fixed seed across calls in the first place."""
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    gate = _gate_for_lockin(active["id"])
    if gate is None:
        return redirect(url_for("week"))
    my_role = _my_role_in_lockin(active, user["user_id"])
    verified = dateplan.verify_face(user["user_id"], seed=uuid.uuid4().hex)
    updated = dict(gate)
    updated[f"biometric_{my_role}"] = int(verified)
    updated[f"consent_{my_role}"] = int(verified)
    db.insert_row(get_db(), "StageGate", updated)
    return redirect(url_for("gate_view"))


@app.route("/gate/enter-relationship", methods=["POST"])
@login_required
def gate_enter_relationship():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    gate = _gate_for_lockin(active["id"])
    if gate is None:
        return redirect(url_for("gate_view"))
    analysis = _gate_analysis_for(gate["pair_id"])
    if analysis is None:
        return redirect(url_for("gate_view"))

    prerequisites = _prerequisites_for_couple(active["user_a"], active["user_b"])
    vision_entries_for_couple = db.fetch_all(get_db(), "VisionEntry", user_id=active["user_a"]) + db.fetch_all(
        get_db(), "VisionEntry", user_id=active["user_b"]
    )
    couple_id = deterministic_couple_id(active["user_a"], active["user_b"])
    result = journey.enter_relationship(
        get_db(),
        couple_id,
        active["user_a"],
        active["user_b"],
        lockin_id=active["id"],
        gate=gate,
        gate_analysis=analysis,
        prerequisites=prerequisites,
        exclusivity_ack_a=bool(gate["exclusivity_ack_a"]),
        exclusivity_ack_b=bool(gate["exclusivity_ack_b"]),
        consent_a=bool(gate["consent_a"]),
        consent_b=bool(gate["consent_b"]),
        biometric_a=bool(gate["biometric_a"]),
        biometric_b=bool(gate["biometric_b"]),
        vision_entries_for_couple=vision_entries_for_couple,
        today=week_to_date(active["week"]),
    )
    if result["advanced"]:
        gate = db.fetch_one(get_db(), "StageGate", pair_id=active["id"])  # re-fetch: enter_relationship didn't touch it
        db.insert_row(get_db(), "StageGate", stage_gate.resolve_gate(gate, "progressed", str(get_clock())))
        return redirect(url_for("journey_view"))
    return redirect(url_for("gate_view"))


# ── Vision / Chemistry at Relationship entry (docs/relationship-stage-spec.md
#    Part C, docs/intimacy-expectations-spec.md Part A) ─────────────────────


@app.route("/vision")
@login_required
def vision_view():
    user = current_user()
    entries = db.fetch_all(get_db(), "VisionEntry", user_id=user["user_id"])
    changes = db.fetch_all(get_db(), "VisionChange", user_id=user["user_id"])
    grouped: dict[str, list[dict]] = {}
    for e in entries:
        grouped.setdefault(e["element_key"], []).append(e)
    return render_template("vision.html", element_keys=vision.VISION_ELEMENT_KEYS, grouped=grouped, changes=changes)


@app.route("/vision/add", methods=["POST"])
@login_required
def vision_add():
    user = current_user()
    element_key = (request.form.get("element_key") or "").strip()
    detail_text = (request.form.get("detail_text") or "").strip()
    if not element_key or not detail_text:
        return redirect(url_for("vision_view"))
    existing = db.fetch_all(get_db(), "VisionEntry", user_id=user["user_id"], element_key=element_key)
    parent_id = existing[-1]["id"] if existing else None
    row = vision.add_vision_detail(user["user_id"], element_key, detail_text, str(get_clock()), parent_id=parent_id)
    db.insert_row(get_db(), "VisionEntry", {"id": uuid.uuid4().hex[:12], **row})
    return redirect(url_for("vision_view"))


@app.route("/vision/declare-change", methods=["POST"])
@login_required
def vision_declare_change():
    user = current_user()
    element_key = (request.form.get("element_key") or "").strip()
    from_value = (request.form.get("from_value") or "").strip()
    to_value = (request.form.get("to_value") or "").strip()
    disclosed = "disclosed" in request.form
    if not (element_key and from_value and to_value):
        return redirect(url_for("vision_view"))
    try:
        row = vision.declare_vision_change(
            user["user_id"], element_key, from_value, to_value, str(get_clock()),
            disclosed_to_partner=disclosed, guru_conversation_id=uuid.uuid4().hex[:12] if disclosed else None,
        )
    except ValueError:
        return redirect(url_for("vision_view"))
    db.insert_row(get_db(), "VisionChange", {"id": uuid.uuid4().hex[:12], **_bool_ints(row)})
    return redirect(url_for("vision_view"))


@app.route("/chemistry")
@login_required
def chemistry_view():
    user = current_user()
    entries = db.fetch_all(get_db(), "ChemistryEntry", user_id=user["user_id"])
    by_key = {e["key"]: e["value"] for e in entries}

    couple = find_couple_for_user(user["user_id"]) if user["journey_state"] != "dating" else None
    active = _my_active_lockin(user["user_id"]) if user["journey_state"] == "dating" else None
    partner_id = partner_id_in(couple, user["user_id"]) if couple else (_partner_id_in_lockin(active, user["user_id"]) if active else None)

    mismatch = None
    if partner_id:
        partner_entries = db.fetch_all(get_db(), "ChemistryEntry", user_id=partner_id)
        mismatch = chemistry.on_chemistry_update(entries, partner_entries)

    return render_template(
        "chemistry.html",
        by_key=by_key,
        mandatory_keys=chemistry.MANDATORY_KEYS,
        intimacy_keys=chemistry.INTIMACY_MANDATORY_KEYS,
        pace_options=chemistry.INTIMACY_PACE_OPTIONS,
        health_options=chemistry.HEALTH_OPENNESS_OPTIONS,
        boundary_options=chemistry.PHYSICAL_BOUNDARY_OPTIONS,
        mismatch=mismatch,
        has_partner=partner_id is not None,
    )


@app.route("/chemistry/set", methods=["POST"])
@login_required
def chemistry_set():
    user = current_user()
    key = (request.form.get("key") or "").strip()
    value = (request.form.get("value") or "").strip()
    if not key or not value:
        return redirect(url_for("chemistry_view"))
    row = chemistry.set_entry(user["user_id"], key, value, str(get_clock()))
    db.insert_row(get_db(), "ChemistryEntry", {"id": f"{user['user_id']}:{key}", **row})
    return redirect(url_for("chemistry_view"))


# ── The "Next Level" conversation (docs/intimacy-expectations-spec.md Part B)


@app.route("/next-level")
@login_required
def next_level_view():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    my_role = _my_role_in_lockin(active, user["user_id"])
    partner_id = _partner_id_in_lockin(active, user["user_id"])
    partner = with_view_fields(load_user(partner_id))

    threads = db.fetch_all(get_db(), "NextLevelThread", pair_id=active["id"])
    my_entries = db.fetch_all(get_db(), "ChemistryEntry", user_id=user["user_id"])
    partner_entries = db.fetch_all(get_db(), "ChemistryEntry", user_id=partner_id)
    mismatch = chemistry.on_chemistry_update(my_entries, partner_entries)

    visible = [next_level.visible_answers(t, my_role) for t in threads]

    return render_template(
        "next_level.html",
        partner=partner,
        threads=list(zip(threads, visible)),
        mismatch=mismatch,
        guru_can_offer=mismatch["offer_next_level"] and not next_level.guru_already_offered(threads),
        unlocked=escalations.unlocks_available(active["dates_completed"]),
        already_open=bool(threads),
    )


@app.route("/next-level/open", methods=["POST"])
@login_required
def next_level_open():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None or not escalations.unlocks_available(active["dates_completed"]):
        return redirect(url_for("week"))
    if db.fetch_all(get_db(), "NextLevelThread", pair_id=active["id"]):
        return redirect(url_for("next_level_view"))
    opened_by = request.form.get("opened_by", "user")
    try:
        threads = next_level.open_conversation(active["id"], opened_by, str(get_clock()))
    except ValueError:
        return redirect(url_for("next_level_view"))
    for t in threads:
        db.insert_row(get_db(), "NextLevelThread", {"id": f"{active['id']}:{t['question_key']}", **_bool_ints(t)})
    return redirect(url_for("next_level_view"))


@app.route("/next-level/answer", methods=["POST"])
@login_required
def next_level_answer():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    thread = db.fetch_one(get_db(), "NextLevelThread", pair_id=active["id"], question_key=request.form.get("question_key"))
    if thread is None:
        abort(400)
    declined = "declined" in request.form
    answer_text = (request.form.get("answer_text") or "").strip() or None
    updated = next_level.submit_answer(
        thread, _my_role_in_lockin(active, user["user_id"]), answered_at=str(get_clock()), answer_text=answer_text, declined=declined
    )
    db.insert_row(get_db(), "NextLevelThread", _bool_ints(updated))
    return redirect(url_for("next_level_view"))


# ── Relationship stage mechanics (docs/relationship-stage-spec.md Part D) ──


@app.route("/relationship")
@login_required
def relationship_view():
    user = current_user()
    couple = find_couple_for_user(user["user_id"]) if user["journey_state"] != "dating" else None
    if couple is None:
        return redirect(url_for("journey_view"))
    partner = with_view_fields(load_user(partner_id_in(couple, user["user_id"])))
    playbook = db.fetch_one(get_db(), "Playbook", couple_id=couple["id"], stage=couple["stage"])
    generic = db.load_json_field(playbook["tier_generic_json"], []) if playbook else []
    specific = db.load_json_field(playbook["tier_vision_json"], []) if playbook else []
    custom = db.load_json_field(playbook["tier_custom_json"], []) if playbook else []

    differences = db.fetch_all(get_db(), "Difference", couple_id=couple["id"])
    open_differences = [d for d in differences if d["status"] == "open"]
    sorted_differences = [d for d in differences if d["status"] == "sorted"]

    report = db.fetch_one(get_db(), "WeeklyReport", couple_id=couple["id"], week_index=couple["stage_week_index"])
    checkpoint = journey.sixteen_week_checkpoint(couple)

    return render_template(
        "relationship.html",
        couple=couple,
        partner=partner,
        generic=generic,
        specific=specific,
        custom=custom,
        open_differences=open_differences,
        sorted_differences=sorted_differences,
        report=report,
        checkpoint=checkpoint,
        pillars=guru_relationship.PILLARS,
    )


@app.route("/relationship/playbook/add-custom", methods=["POST"])
@login_required
def relationship_playbook_add_custom():
    user = current_user()
    couple = find_couple_for_user(user["user_id"])
    idea = (request.form.get("idea") or "").strip()
    if couple is not None and idea:
        playbook = dict(db.fetch_one(get_db(), "Playbook", couple_id=couple["id"], stage=couple["stage"]))
        custom = db.load_json_field(playbook["tier_custom_json"], [])
        custom.append(idea)
        playbook["tier_custom_json"] = db.json_field(custom)
        db.insert_row(get_db(), "Playbook", playbook)
    return redirect(url_for("relationship_view"))


@app.route("/relationship/romance/idea", methods=["POST"])
@login_required
def relationship_romance_idea():
    user = current_user()
    couple = find_couple_for_user(user["user_id"])
    idea = (request.form.get("idea") or "").strip()
    if couple is not None and idea:
        playbook = dict(db.fetch_one(get_db(), "Playbook", couple_id=couple["id"], stage=couple["stage"]))
        custom = db.load_json_field(playbook["tier_custom_json"], [])
        playbook["tier_custom_json"] = db.json_field(guru_relationship.add_romance_idea(custom, f"Romance idea: {idea}"))
        db.insert_row(get_db(), "Playbook", playbook)
    return redirect(url_for("relationship_view"))


@app.route("/relationship/difference/raise", methods=["POST"])
@login_required
def relationship_difference_raise():
    user = current_user()
    couple = find_couple_for_user(user["user_id"])
    text = (request.form.get("text") or "").strip()
    if couple is None or not text:
        return redirect(url_for("relationship_view"))
    existing = db.fetch_all(get_db(), "Difference", couple_id=couple["id"])
    row = guru_relationship.air_step1_raise_difference(couple["id"], user["user_id"], text, couple["stage_week_index"], existing)
    db.insert_row(get_db(), "Difference", {"id": uuid.uuid4().hex[:12], **_bool_ints(row)})
    return redirect(url_for("relationship_view"))


@app.route("/relationship/difference/consent", methods=["POST"])
@login_required
def relationship_difference_consent():
    row = db.fetch_one(get_db(), "Difference", id=request.form.get("difference_id"))
    if row is None:
        return redirect(url_for("relationship_view"))
    updated = guru_relationship.air_step2_consent_to_share(row, "consent" in request.form)
    db.insert_row(get_db(), "Difference", _bool_ints(updated))
    return redirect(url_for("relationship_view"))


@app.route("/relationship/difference/resolve", methods=["POST"])
@login_required
def relationship_difference_resolve():
    row = db.fetch_one(get_db(), "Difference", id=request.form.get("difference_id"))
    if row is None:
        return redirect(url_for("relationship_view"))
    db.insert_row(get_db(), "Difference", guru_relationship.resolve_difference(row))
    return redirect(url_for("relationship_view"))


@app.route("/relationship/expense/check", methods=["POST"])
@login_required
def relationship_expense_check():
    user = current_user()
    couple = find_couple_for_user(user["user_id"])
    if couple is None:
        return redirect(url_for("relationship_view"))
    result = guru_relationship.expense_check(request.form.get("expense_strategy"), "compliant" in request.form)
    report = db.fetch_one(get_db(), "WeeklyReport", couple_id=couple["id"], week_index=couple["stage_week_index"])
    if report is None:
        report = journey.schedule_weekly_report(get_db(), couple["id"], couple["stage"], couple["stage_week_index"])
    updated = dict(report)
    updated["expense_compliant"] = int(result["compliant"])
    db.insert_row(get_db(), "WeeklyReport", updated)
    return redirect(url_for("relationship_view"))


# ── /journey ────────────────────────────────────────────────────────────


@app.route("/journey")
@login_required
def journey_view():
    user = current_user()
    # A Couple record only exists from Relationship onward (schema.sql's
    # own documented invariant) — a 'dating' user must never be shown one,
    # even if a stale row happens to reference them (e.g. left over from
    # a re-seed that reset journey_state without touching Couple). Matches
    # the same gate dashboard()/week() already use.
    couple = find_couple_for_user(user["user_id"]) if user["journey_state"] != "dating" else None
    partner = None
    road_block_count = 0
    exception_count = 0
    next_stage_name = None
    if couple:
        partner = with_view_fields(load_user(partner_id_in(couple, user["user_id"])))
        road = get_road(user["user_id"], couple["id"])
        road_block_count = len(db.load_json_field(road["routine_json"], []))
        exception_count = len(
            [e for e in db.fetch_all(get_db(), "CalendarEntry", couple_id=couple["id"]) if e["type"] in EXCEPTION_TYPES]
        )
        next_stage_name = journey.next_stage(couple["stage"])
    return render_template(
        "journey.html",
        couple=couple,
        partner=partner,
        road_block_count=road_block_count,
        exception_count=exception_count,
        next_stage=next_stage_name,
        stage_order=journey.STAGE_ORDER,
    )


@app.route("/journey/advance", methods=["POST"])
@login_required
def journey_advance():
    user = current_user()
    if user["journey_state"] == "dating":
        return redirect(url_for("journey_view"))
    couple = find_couple_for_user(user["user_id"])
    if couple is None:
        return redirect(url_for("journey_view"))
    opt_in_me = "opt_in_me" in request.form
    opt_in_partner = "opt_in_partner" in request.form
    journey.advance_stage(get_db(), couple["id"], opt_in_me, opt_in_partner, today=week_to_date(get_week_number()))
    return redirect(url_for("journey_view"))


# ── /road — the ROAD pathway: Routine -> Obligations -> Availability ──────
#
# Three separate pages/steps, not one long form — Routine is captured
# first, then one-time Obligations, then Availability is DERIVED from
# both and shown to the person privately before they choose what (if
# anything) to expose to their partner.


def _couple_or_redirect():
    user = current_user()
    # Same invariant as journey_view()/week(): no Couple for a 'dating'
    # user, even if a stale row references them.
    couple = find_couple_for_user(user["user_id"]) if user["journey_state"] != "dating" else None
    return user, couple


@app.route("/road")
@login_required
def road_view():
    return redirect(url_for("road_routine"))


@app.route("/road/routine")
@login_required
def road_routine():
    user, couple = _couple_or_redirect()
    if couple is None:
        return redirect(url_for("journey_view"))

    road = get_road(user["user_id"], couple["id"])
    # "free" blocks are declared directly on the Availability step
    # (road_availability_add_free) — Routine only shows work/fitness, its
    # own scope.
    blocks = [b for b in db.load_json_field(road["routine_json"], []) if b["category"] != "free"]

    return render_template(
        "road_routine.html",
        steps=ROAD_STEPS,
        active_index=0,
        couple=couple,
        blocks=blocks,
        grid=weekly_grid(blocks),
        week_days=WEEK_DAYS,
    )


@app.route("/road/routine/add", methods=["POST"])
@login_required
def road_routine_add():
    user, couple = _couple_or_redirect()
    if couple is None:
        return redirect(url_for("journey_view"))

    category = request.form.get("category")
    if category not in ("work", "fitness"):
        abort(400)
    days = [d for d in request.form.getlist("days") if d in WEEK_DAYS]
    label = (request.form.get("label") or "").strip()
    start = request.form.get("start")
    end = request.form.get("end")
    if days and label and start and end:
        add_routine_block(user["user_id"], couple["id"], category, days, label, start, end)
    return redirect(url_for("road_routine"))


@app.route("/road/routine/remove", methods=["POST"])
@login_required
def road_routine_remove():
    user, couple = _couple_or_redirect()
    if couple is None:
        return redirect(url_for("journey_view"))
    block_id = request.form.get("block_id")
    if block_id:
        remove_routine_block(user["user_id"], couple["id"], block_id)
    return redirect(url_for("road_routine"))


@app.route("/road/obligations")
@login_required
def road_obligations():
    user, couple = _couple_or_redirect()
    if couple is None:
        return redirect(url_for("journey_view"))

    exceptions = sorted(
        (e for e in db.fetch_all(get_db(), "CalendarEntry", couple_id=couple["id"], owner_id=user["user_id"]) if e["type"] in EXCEPTION_TYPES),
        key=lambda e: e["starts_at"],
    )
    return render_template(
        "road_obligations.html",
        steps=ROAD_STEPS,
        active_index=1,
        couple=couple,
        exceptions=exceptions,
        exception_types=EXCEPTION_TYPES,
        travel_modes=TRAVEL_MODES,
    )


@app.route("/road/obligations/add", methods=["POST"])
@login_required
def road_obligations_add():
    user, couple = _couple_or_redirect()
    if couple is None:
        return redirect(url_for("journey_view"))

    exc_type = request.form.get("type")
    title = (request.form.get("title") or "").strip()
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    travel_mode = request.form.get("travel_mode")
    shared = "shared" in request.form

    if exc_type in EXCEPTION_TYPES and title and start_date and end_date:
        if exc_type == "travel" and travel_mode not in TRAVEL_MODES:
            travel_mode = "solo"
        add_exception(couple["id"], user["user_id"], exc_type, title, start_date, end_date, travel_mode, shared)
    return redirect(url_for("road_obligations"))


@app.route("/road/obligations/remove", methods=["POST"])
@login_required
def road_obligations_remove():
    entry_id = request.form.get("entry_id")
    if entry_id:
        db.delete_row(get_db(), "CalendarEntry", entry_id)
    return redirect(url_for("road_obligations"))


@app.route("/road/availability")
@login_required
def road_availability():
    user, couple = _couple_or_redirect()
    if couple is None:
        return redirect(url_for("journey_view"))

    road = get_road(user["user_id"], couple["id"])
    blocks = db.load_json_field(road["routine_json"], [])
    free_blocks = [b for b in blocks if b["category"] == "free"]
    derived = derive_availability(blocks)
    shared_keys = shared_availability_keys(user["user_id"], couple["id"])
    partner = with_view_fields(load_user(partner_id_in(couple, user["user_id"])))
    overlap = couple_availability_overlap(couple, user["user_id"])
    overlap_count = sum(len(v) for v in overlap.values())

    return render_template(
        "road_availability.html",
        steps=ROAD_STEPS,
        active_index=2,
        couple=couple,
        partner=partner,
        week_days=WEEK_DAYS,
        derived=derived,
        free_blocks=free_blocks,
        shared_keys=shared_keys,
        slot_key=_slot_key,
        shared_count=len(shared_keys),
        overlap=overlap,
        overlap_count=overlap_count,
    )


@app.route("/road/availability/add-free", methods=["POST"])
@login_required
def road_availability_add_free():
    user, couple = _couple_or_redirect()
    if couple is None:
        return redirect(url_for("journey_view"))

    days = [d for d in request.form.getlist("days") if d in WEEK_DAYS]
    start = request.form.get("start")
    end = request.form.get("end")
    if days and start and end:
        add_routine_block(user["user_id"], couple["id"], "free", days, "Free time", start, end)
    return redirect(url_for("road_availability"))


@app.route("/road/availability/remove-free", methods=["POST"])
@login_required
def road_availability_remove_free():
    user, couple = _couple_or_redirect()
    if couple is None:
        return redirect(url_for("journey_view"))
    block_id = request.form.get("block_id")
    if block_id:
        remove_routine_block(user["user_id"], couple["id"], block_id)
    return redirect(url_for("road_availability"))


@app.route("/road/availability/share", methods=["POST"])
@login_required
def road_availability_share():
    user, couple = _couple_or_redirect()
    if couple is None:
        return redirect(url_for("journey_view"))
    chosen_keys = set(request.form.getlist("slot"))
    set_shared_availability(user["user_id"], couple["id"], chosen_keys)
    return redirect(url_for("road_availability"))


@app.route("/road/vision")
@login_required
def road_vision():
    user, couple = _couple_or_redirect()
    if couple is None:
        return redirect(url_for("journey_view"))

    partner = with_view_fields(load_user(partner_id_in(couple, user["user_id"])))
    my_pending = [v for v in user["visions"] if v["key"] in VISION_STANCE_OPTIONS]
    partner_visions = {v["key"]: v["stance"] for v in partner["visions"] if v["key"] in VISION_STANCE_OPTIONS}

    return render_template(
        "road_vision.html",
        steps=ROAD_STEPS,
        active_index=3,
        couple=couple,
        partner=partner,
        my_pending=my_pending,
        partner_visions=partner_visions,
        stance_options=VISION_STANCE_OPTIONS,
    )


@app.route("/road/vision/set", methods=["POST"])
@login_required
def road_vision_set():
    user, couple = _couple_or_redirect()
    if couple is None:
        return redirect(url_for("journey_view"))

    key = request.form.get("key")
    options = VISION_STANCE_OPTIONS.get(key)
    if options is None or not any(v["key"] == key for v in user["visions"]):
        abort(400)  # only settable for a vision this user actually selected

    if key == "Cohabitate":
        chosen = sorted(v for v in request.form.getlist("stance") if v in options)
        stance = chosen or None
    else:
        raw = request.form.get("stance")
        stance = raw if raw in options else None

    visions = [dict(v) for v in user["visions"]]
    for v in visions:
        if v["key"] == key:
            v["stance"] = stance
    save_visions(user["user_id"], visions)
    return redirect(url_for("road_vision"))


# ── /admin — simulation clock control ──────────────────────────────────
# The staggered weekly timeline (docs/dating-stage-spec.md §1) needs to be
# steppable for testing/demoing without waiting real hours — this panel
# jumps the shared SimulationClock straight to any of the week's named
# checkpoints, or to next week's Monday noon.

_ADMIN_CHECKPOINTS = [
    ("match_1", "Match 1 reveals", clock_module.MATCH_1_REVEAL),
    ("match_2", "Match 2 reveals / Match 1 closes", clock_module.MATCH_2_REVEAL),
    ("match_3", "Match 3 reveals / Match 2 closes", clock_module.MATCH_3_REVEAL),
    ("calendar_open", "Calendar opens / Match 3 closes", clock_module.CALENDAR_OPENS),
    ("calendar_close", "Calendar closes", clock_module.CALENDAR_CLOSES),
    ("dates_live", "Dates go live", clock_module.DATES_LIVE),
    ("feedback", "Feedback opens (Sun night)", clock_module.FEEDBACK_OPENS),
]



# ── Sign-up and the three-step onboarding wizard ───────────────────────
# Steps 1-5 of the Case 1 walkthrough. The draft lives in the session and
# only becomes a User row at /onboarding/finish, so an abandoned sign-up
# leaves nothing behind. journey_state starts at 'onboarding' — Segment B
# (BGV) is what promotes a user to 'dating'.

ONBOARDING_STEPS = [
    ("signup", "Sign up"),
    ("onboard_vision", "Vision"),
    ("onboard_stats", "Stats"),
    ("onboard_chemistry", "Chemistry"),
    ("onboard_done", "Verification"),
]


def _draft() -> dict:
    """The in-progress onboarding draft held in the session."""
    if "onboarding" not in session:
        session["onboarding"] = onboarding.blank_draft()
    return session["onboarding"]


def _save_draft(draft: dict) -> None:
    session["onboarding"] = draft
    session.modified = True


def _onboarding_context(step_endpoint: str, **extra):
    """Shared template context: which wizard step we're on, for the rail."""
    steps = [
        {"endpoint": endpoint, "label": label, "index": i + 1,
         "state": "done" if i < [s[0] for s in ONBOARDING_STEPS].index(step_endpoint)
                  else ("current" if endpoint == step_endpoint else "todo")}
        for i, (endpoint, label) in enumerate(ONBOARDING_STEPS)
    ]
    return {"wizard_steps": steps, "step_total": len(ONBOARDING_STEPS), **extra}


@app.route("/")
def home():
    """The front door. Signed in, you go to your dashboard; otherwise you
    start signing up. The seeded-user picker used to live here — it is
    still available at /pool for play-testing the simulation."""
    if session.get("user_id") and current_user() is not None:
        return redirect(url_for("dashboard"))
    return redirect(url_for("signup"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    """Step 1. Phone and email, neither validated — Case 1's unvalidated
    front door. Shape hints are shown, nothing is enforced."""
    draft = _draft()
    error = None
    hints = {}

    if request.method == "POST":
        result = onboarding.normalise_identifiers(request.form.get("email"), request.form.get("phone"))
        if result["ok"]:
            draft["email"] = result["email"]
            draft["phone"] = result["phone"]
            _save_draft(draft)
            return redirect(url_for("onboard_vision"))
        error = result["error"]
        hints = result

    return render_template(
        "signup.html",
        **_onboarding_context("signup", draft=draft, error=error, hints=hints),
    )


@app.route("/onboarding/vision", methods=["GET", "POST"])
def onboard_vision():
    """Step 2. The four end goals. Intimacy is mandatory with 1-2 kinds,
    plus at least one of Kids / Cohabitate / Travel together, and Kids
    requires Physical — the same rules generate_users enforces."""
    draft = _draft()
    error = None

    if request.method == "POST":
        result = onboarding.validate_vision(
            request.form.getlist("intimacy_kinds"),
            request.form.getlist("other_keys"),
            request.form.getlist("cohabit_focus"),
        )
        if result["ok"]:
            draft["vision"] = {
                "intimacy_kinds": result["intimacy_kinds"],
                "other_keys": result["other_keys"],
                "cohabit_focus": result["cohabit_focus"],
            }
            _save_draft(draft)
            return redirect(url_for("onboard_stats"))
        error = result["error"]

    saved = draft.get("vision") or {}
    return render_template(
        "onboard_vision.html",
        **_onboarding_context(
            "onboard_vision",
            error=error,
            intimacy_kinds=onboarding.INTIMACY_KINDS,
            other_keys=onboarding.OTHER_VISION_KEYS,
            chosen_kinds=saved.get("intimacy_kinds", []),
            chosen_others=saved.get("other_keys", []),
            cohabit_focus_options=onboarding.COHABIT_FOCUS,
            chosen_focus=saved.get("cohabit_focus", []),
        ),
    )


@app.route("/onboarding/stats", methods=["GET", "POST"])
def onboard_stats():
    """Step 3. Stats, with the salary → bracket derivation. Only the
    bracket is ever shown to anyone else; the salary itself is not stored
    on the User row at all."""
    draft = _draft()
    error = None
    submitted = {}

    if request.method == "POST":
        submitted = {**request.form.to_dict(), "languages": request.form.getlist("languages")}
        result = onboarding.validate_stats(submitted)
        if result["ok"]:
            draft["stats"] = result["stats"]
            draft["city"] = result["city"]
            draft["gender"] = result["gender"]
            _save_draft(draft)
            return redirect(url_for("onboard_chemistry"))
        error = result["error"]

    saved = draft.get("stats") or {}
    return render_template(
        "onboard_stats.html",
        **_onboarding_context(
            "onboard_stats",
            error=error,
            submitted=submitted,
            saved=saved,
            saved_city=draft.get("city"),
            saved_gender=draft.get("gender"),
            numeric_stats=onboarding.NUMERIC_STATS,
            choice_stats=onboarding.CHOICE_STATS,
            cities=onboarding.CITIES_FOR_SIGNUP,
            genders=onboarding.GENDERS_FOR_SIGNUP,
            languages_pool=onboarding.LANGUAGES_POOL,
            saved_languages=saved.get("languages", []),
            income_bands=onboarding.INCOME_BANDS,
        ),
    )


@app.route("/onboarding/chemistry", methods=["GET", "POST"])
def onboard_chemistry():
    """Step 4. Sort activities into four buckets. Not to be confused with
    chemistry.py, which is the Relationship-entry intimacy layer — this
    step writes User.skills_json."""
    draft = _draft()
    error = None

    if request.method == "POST":
        submitted = {activity: request.form.get(f"act__{activity}") for activity in onboarding.ACTIVITIES}
        submitted = {a: b for a, b in submitted.items() if b}
        result = onboarding.validate_activities(submitted)
        draft["activities"] = submitted
        _save_draft(draft)
        if result["ok"]:
            return redirect(url_for("onboard_finish"))
        error = result["error"]

    return render_template(
        "onboard_chemistry.html",
        **_onboarding_context(
            "onboard_chemistry",
            error=error,
            activities=onboarding.ACTIVITIES,
            buckets=onboarding.BUCKETS,
            chosen=draft.get("activities", {}),
            min_sorted=onboarding.MIN_SORTED,
        ),
    )


@app.route("/onboarding/finish", methods=["GET", "POST"])
def onboard_finish():
    """Step 5. Write the User and Account rows, sign the person in, and
    hand off to verification. This is the only place in the wizard that
    touches the database."""
    draft = _draft()

    if not draft.get("vision"):
        return redirect(url_for("onboard_vision"))
    if not draft.get("stats"):
        return redirect(url_for("onboard_stats"))
    if not onboarding.validate_activities(draft.get("activities", {}))["ok"]:
        return redirect(url_for("onboard_chemistry"))

    if request.method == "POST":
        user_id = onboarding.new_user_id()
        visions = onboarding.build_visions(
            draft["vision"]["intimacy_kinds"],
            draft["vision"]["other_keys"],
            draft["vision"].get("cohabit_focus"),
        )
        user_row = onboarding.build_user_row(
            user_id=user_id,
            city=draft["city"],
            gender=draft["gender"],
            stats=draft["stats"],
            visions=visions,
            activities=draft["activities"],
        )
        db.insert_row(get_db(), "User", user_row)
        db.insert_row(
            get_db(),
            "Account",
            onboarding.account_row(user_id, draft.get("email"), draft.get("phone"), str(get_clock())),
        )

        session.pop("onboarding", None)
        session["user_id"] = user_id
        return redirect(url_for("dashboard"))

    return render_template(
        "onboard_done.html",
        **_onboarding_context(
            "onboard_done",
            draft=draft,
            visions=onboarding.build_visions(
                draft["vision"]["intimacy_kinds"],
                draft["vision"]["other_keys"],
                draft["vision"].get("cohabit_focus"),
            ),
            skills=onboarding.build_skills(draft["activities"]),
            bucket_labels={b[0]: b[2] for b in onboarding.BUCKETS},
            income_band=draft["stats"]["income_band"],
        ),
    )


@app.route("/onboarding/restart", methods=["POST"])
def onboard_restart():
    session.pop("onboarding", None)
    return redirect(url_for("signup"))


@app.route("/admin/reset-week", methods=["GET", "POST"])
def admin_reset_week():
    if request.method == "POST":
        current = get_clock()
        action = request.form.get("action")
        if action == "next_week":
            set_clock(clock_module.SimulationClock.at(current.week + 1, "Mon", 12))
        else:
            point = next((p for key, _label, p in _ADMIN_CHECKPOINTS if key == action), None)
            if point is not None:
                set_clock(clock_module.checkpoint(current.week, point))
        return redirect(url_for("admin_reset_week"))

    clock = get_clock()
    return render_template("admin.html", clock=clock, phase=clock_module.phase(clock), checkpoints=_ADMIN_CHECKPOINTS)


if __name__ == "__main__":
    app.run(port=5000, debug=True)
