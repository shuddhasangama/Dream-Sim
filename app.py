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
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for

import bgv
import cadence
import calendar_dating
import ceremony
import chemistry
import clock as clock_module
import date_alignment
import dateplan
import db
import demo
import disclosure
import escalations
import gate_conversation
import guru
import guru_dating
import guru_relationship
import invite_home
import journey
import locale_defaults
import lockin
import matching
import next_level
import onboarding
import outcomes
import payments
import progress
import stage_gate
import vision
from generate_users import COHABIT_FOCUS, KIDS_STANCES, from_user_row, to_user_row

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
    hour, minute = dateplan.slot_start(meal_slot)
    return f"{the_date.isoformat()}T{hour:02d}:{minute:02d}"


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


def _milestones_for(user: dict) -> set:
    """Turn this user's actual rows into the milestone set disclosure.py
    reasons about. The only place that maps database facts onto them."""
    if user is None:
        return set()
    active = _my_active_lockin(user["user_id"])
    plan = _dateplan_for_lockin(active["id"]) if active else None
    outcome = db.fetch_one(get_db(), "DateOutcome", dateplan_id=plan["id"]) if plan else None
    return disclosure.milestones_for(
        bgv_status=user["bgv_status"],
        journey_state=user["journey_state"],
        has_active_lockin=active is not None,
        has_dateplan=plan is not None,
        has_date_outcome=outcome is not None,
    )


def unlocked_or_redirect(key: str):
    """Route guard. Returns a redirect when the surface is not open yet,
    or None to carry on. Guarding in the route matters as much as hiding
    the link — a bookmarked URL must not get past the timing rules."""
    user = current_user()
    reached = _milestones_for(user)
    if disclosure.is_open(key, reached):
        return None
    return render_template(
        "locked.html",
        label=disclosure.BY_KEY[key][1],
        reason=disclosure.locked_reason(key, reached),
    ), 403


@app.context_processor
def inject_globals():
    user = current_user()
    reached = _milestones_for(user) if user else set()
    return {
        "session_user": user,
        "session_user_name": display_name(user["user_id"], user["gender"]) if user else None,
        "week_number": get_week_number(),
        "reach_locked": reach_locked(user) if user else False,
        "demo_enabled": demo.is_enabled(),
        "demo_clock": demo.clock_view(get_clock()) if demo.is_enabled() else None,
        "payments_enabled": payments.is_enabled(),
        "needs_verification": bool(user) and user["bgv_status"] != "verified",
        "nav_links": disclosure.nav_for(reached, reach_locked=reach_locked(user) if user else False),
        "milestones": reached,
        # 2026-09-04: a stage, not a step count. "Step 11 of 12" invited
        # the question "what are the other eleven?", which is the very
        # confusion it existed to remove.
        "journey_stage": progress.stage_view(user["journey_state"], reached) if user else None,
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


@app.template_filter("slot")
def humanise_slot(value):
    """Turn a DatePlan's stored ISO slot into something a person reads.

    slot_datetime() writes "2026-01-10T19:30" because that is what the
    rest of the code wants back. Printing it raw in an agreement someone
    is being asked to sign is the wrong register — a clause should read
    like a sentence. Anything that is not an ISO slot passes through
    untouched, so a placeholder stays a placeholder."""
    if not isinstance(value, str) or "T" not in value:
        return value
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        return value
    return f"{stamp:%a} {stamp.day} {stamp:%b}, {stamp:%H:%M}"


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
    adjustable = user["preferences"]["adjustable"]
    sliders = []
    for spec in SLIDER_LEVERS:
        key = spec["key"]
        # 2026-09-04, user's rule: a slider only exists where the stat
        # does. Skipping it silently would leave a gap with no explanation,
        # so reach.html lists these separately as "unlock by filling it in".
        if key not in adjustable:
            continue
        suggested = matching.suggest_range(pool, key, gender=partner_gender) if key in matching.RANGE_LEVERS else None
        self_value = user["stats"].get(key) if key in matching.RANGE_LEVERS else None
        sliders.append({**spec, "current": adjustable[key], "suggested": suggested, "self_value": self_value})
    return sliders


_STAT_PROMPTS = {
    "height_cm": "your height",
    "weight_kg": "your weight",
    "waist_in": "your waist measurement",
    "religion": "your religion",
}


def locked_lever_view(user: dict) -> list[dict]:
    """The filters this user has not unlocked, and what unlocks each.

    Naming them beats hiding them: a short REACH with no explanation reads
    as the product failing, where "add your height to filter on height"
    reads as a trade the user can take or leave.
    """
    labels = {spec["key"]: spec.get("label", spec["key"]) for spec in SLIDER_LEVERS}
    labels.setdefault("religion", "Religion")
    labels.setdefault("nationality", "Nationality")
    return [
        {
            "lever": entry["lever"],
            "label": labels.get(entry["lever"], entry["lever"]),
            "needs": _STAT_PROMPTS.get(entry["needs"], entry["needs"]),
        }
        for entry in matching.locked_levers(user)
    ]


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
    return render_template("reach.html", counts=counts, deltas=deltas, sliders=sliders,
                           locked_levers=locked_lever_view(user))


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


def _boundary_of(user_id: str) -> str | None:
    """One person's greeting preference, from the one place it is stored."""
    row = db.fetch_one(get_db(), "ChemistryEntry", user_id=user_id, key="physical_boundary")
    return row["value"] if row else None


def _plan_slot(plan: dict) -> tuple[int, int] | None:
    """Where this date sits in the simulated week, as (day_index, hour).

    Derived from the stored ISO datetime rather than a new column: the
    epoch that produced it (WEEK_ONE_MONDAY) starts on a Monday, so the
    weekday IS the day index. One source of truth, no migration."""
    stamp = plan.get("datetime")
    if not stamp or "T" not in stamp:
        return None
    try:
        day_index = date.fromisoformat(stamp.split("T")[0]).weekday()
    except ValueError:
        return None
    return day_index, dateplan.debrief_opens_hour(plan["meal"])


def _debrief_is_open(plan: dict, clock: clock_module.SimulationClock) -> bool:
    """2026-09-04, user's rule: the debrief opens an hour after the date
    starts, not on Sunday night — so a no-show can be reported the same
    evening rather than three days later.

    A plan whose slot cannot be read opens the debrief rather than sealing
    it shut. Being unable to say when the date was is not a reason to stop
    someone reporting what happened at it."""
    slot = _plan_slot(plan)
    if slot is None:
        return True
    day_index, opens_hour = slot
    return (clock.day_index, clock.hour) >= (day_index, opens_hour)


def _cancellation_terms(plan: dict, clock: clock_module.SimulationClock) -> dict:
    """What cancelling this date right now would cost."""
    slot = _plan_slot(plan)
    start_hour = dateplan.slot_start(plan["meal"])[0]
    day_index = slot[0] if slot else clock.day_index
    notice = dateplan.hours_between((clock.day_index, clock.hour), (day_index, start_hour))
    return dateplan.cancellation(notice, payments.fee(payments.CANCELLATION)["amount_inr"])


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
    guard = unlocked_or_redirect("calendar")
    if guard is not None:
        return guard
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

    # Segment D: the availability fee is charged before the slots are
    # submitted, which is where the mock-up puts it.
    gate = _require_payment(user, payments.AVAILABILITY)
    if gate is not None:
        return gate

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

    # 2026-09-04: budget, diet and cuisine are asked here rather than at
    # sign-up, so a date cannot be confirmed until both have answered.
    if not date_alignment.ready_for_pair(user["stats"], partner["stats"]):
        return redirect(url_for("align_view"))

    venue = calendar_dating.suggest_venue(day, meal, user["stats"]["diet"], partner["stats"]["diet"])

    # The bill clause used to assert "both parties declared" a band that
    # came from a hardcoded default and matched neither of them. It now
    # states the lower of the two bands they actually chose, which is the
    # only reading that does not commit the person with less money to the
    # other's idea of an evening.
    budget = date_alignment.lower_budget(user["stats"].get("budget"),
                                         partner["stats"].get("budget"), user.get("city"))
    shared = date_alignment.shared_cuisines(user["stats"].get("cuisine"),
                                            partner["stats"].get("cuisine"))
    plan = dateplan.generate_plan(
        lockin_id=active["id"],
        confirmed_slot={"day": day, "meal_slot": meal},
        venue={**venue, "cuisine": shared[0] if shared else venue.get("cuisine")},
        datetime_str=slot_datetime(active["week"], day, meal),
        bill_split="pay-your-own",
        selections_a={},
        selections_b={},
        config={"budget_estimate": budget} if budget else None,
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
    guard = unlocked_or_redirect("plan")
    if guard is not None:
        return guard
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

    # 2026-09-04: the greeting lives in ChemistryEntry, set on /boundaries,
    # and nowhere else. It used to ALSO be a DatePlan selection — two
    # fields for one thing, with the agreement reading only one of them.
    my_boundary = _boundary_of(user["user_id"])
    briefing = guru_dating.pre_date_briefing(_boundary_of(partner_id))

    return render_template(
        "plan.html",
        partner=partner,
        plan=plan,
        my_selections=my_selections,
        my_signature=my_signature,
        confirmed=confirmed,
        briefing=briefing,
        ack_fields=dateplan.ACK_FIELDS,
        my_boundary=my_boundary,
        # Signed once is signed. The form comes back only if they ask for
        # it, and the screen otherwise offers a way onward rather than the
        # same request again.
        signed=my_signature is not None and dateplan.is_fully_acknowledged(dict(my_signature)),
        editing=request.args.get("edit") == "1",
        bill_split_labels=dateplan.BILL_SPLIT_LABELS,
        phase=clock_module.phase(get_clock()),
        cancellable=plan["status"] == "confirmed",
        cancellation=_cancellation_terms(plan, get_clock()),
        cancellation_fee=payments.amount_label(payments.CANCELLATION),
        notice_hours=dateplan.CANCELLATION_NOTICE_HOURS,
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
    # No greeting here any more — /boundaries owns it (2026-09-04).
    selections = {
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

    # Segment D: the agreement fee is charged before either party can sign.
    gate = _require_payment(user, payments.AGREEMENT)
    if gate is not None:
        return gate

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


def _feedback_back() -> str:
    """Where to land after recording flags or a decision. The debrief screen
    (Segment F) and the week screen post to these same two routes, so the
    rules stay in one place and only the destination differs."""
    return "debrief_view" if request.form.get("back") == "debrief_view" else "week"


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

    return redirect(url_for(_feedback_back()))


@app.route("/plan/feedback", methods=["POST"])
@login_required
def plan_feedback():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for(_feedback_back()))
    plan = _dateplan_for_lockin(active["id"])
    if plan is None or plan["status"] != "confirmed":
        return redirect(url_for(_feedback_back()))

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
        return redirect(url_for(_feedback_back()))
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

    return redirect(url_for(_feedback_back()))


# ── Contact exchange / invite home (docs/relationship-stage-spec.md Part A,
#    docs/intimacy-expectations-spec.md Part C) ─────────────────────────────


@app.route("/escalations")
@login_required
def escalations_view():
    guard = unlocked_or_redirect("escalations")
    if guard is not None:
        return guard
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

    # Segment G: each escalation is gated behind its own ceremony, and the
    # home invite is gated behind contact sharing as well — you do not
    # invite someone home before you have exchanged a phone number.
    share = _ceremony_pair_state(ceremony.CONTACT_SHARE, active["id"], active)
    home = _ceremony_pair_state(ceremony.HOME_INVITE, active["id"], active)
    home["blocked_by"] = None if share["both_complete"] else share["label"]

    return render_template(
        "escalations.html",
        share_ceremony=share,
        home_ceremony=home,
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
    """Requesting is free; REVEALING is what the ceremony gates. The
    request is how you ask, and asking is not the thing that hands your
    number over."""
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
    # Ceremony #2. Accepting is what makes a number visible, so that is
    # what the agreement gates — not the asking. Declining never needs a
    # signature: nobody should have to sign something to say no.
    active = _my_active_lockin(user["user_id"])
    if request.form.get("response") == "accepted" and active is not None:
        share = _ceremony_pair_state(ceremony.CONTACT_SHARE, active["id"], active)
        if not share["mine_complete"]:
            return redirect(url_for("ceremony_view", kind=ceremony.CONTACT_SHARE))

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

    # Ceremony #3, and the ordering that goes with it: contact details are
    # shared before an address is. Both gates are checked here rather than
    # only hidden in the template, because a posted form is not a click.
    share = _ceremony_pair_state(ceremony.CONTACT_SHARE, active["id"], active)
    if not share["both_complete"]:
        return redirect(url_for("escalations_view"))
    home = _ceremony_pair_state(ceremony.HOME_INVITE, active["id"], active)
    if not home["mine_complete"]:
        return redirect(url_for("ceremony_view", kind=ceremony.HOME_INVITE))
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
    guard = unlocked_or_redirect("gate")
    if guard is not None:
        return guard
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

    conversation = _gate_conversation_state(dict(gate), active)
    return render_template(
        "gate.html",
        conversation=conversation,
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


def _clock_hours(clock) -> int:
    """The simulated clock as a flat hour count, so a pause can be measured
    across day and week boundaries without date arithmetic."""
    return (clock.week - 1) * 24 * 7 + clock.day_index * 24 + clock.hour


def _gate_conversation_state(gate: dict, active: dict) -> dict:
    """Everything the gate screen needs, in Guru's words.

    Nothing either person wrote reaches the other from here. What crosses
    is which question was asked — unattributed — and a comparison of two
    scale answers phrased as a shared position.
    """
    user = current_user()
    round_no = gate.get("round_no") or 1
    asks = db.fetch_all(get_db(), "GateAsk", pair_id=active["id"])
    this_round = [a for a in asks if (a["round_no"] or 1) == round_no]
    asked_keys = [a["question_key"] for a in this_round]

    responses = db.fetch_all(get_db(), "GateResponse", pair_id=active["id"])
    def answers_of(uid):
        return {r["question_key"]: (r["readiness_scale"] or r["answer_text"])
                for r in responses if r["user_id"] == uid}

    partner_id = _partner_id_in_lockin(active, user["user_id"])
    mine, theirs = answers_of(user["user_id"]), answers_of(partner_id)
    now = _clock_hours(get_clock())

    return {
        "round_no": round_no,
        "asked": [gate_conversation.relay(k) for k in asked_keys],
        "asked_keys": asked_keys,
        "i_asked": [a["question_key"] for a in this_round if a["asked_by"] == user["user_id"]],
        "my_answers": mine,
        "unanswered": [k for k in asked_keys if k not in mine],
        "report": gate_conversation.report(asked_keys, mine, theirs),
        "reflection": gate_conversation.reflection(gate.get("answers_closed_at"), now),
        "may_commit": gate_conversation.may_commit(
            asked_keys, mine, theirs, gate.get("answers_closed_at"), now),
        "askable": gate_conversation.askable([a["question_key"] for a in asks]),
        "max_asks": gate_conversation.MAX_ASKS_PER_ROUND,
        "reflection_hours": gate_conversation.REFLECTION_HOURS,
    }


@app.route("/gate/ask", methods=["POST"])
@login_required
def gate_ask():
    """Choose what you want to know. Both of you then answer it."""
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    gate = _gate_for_lockin(active["id"]) if active else None
    if gate is None:
        return redirect(url_for("guru_view"))

    asks = db.fetch_all(get_db(), "GateAsk", pair_id=active["id"])
    result = gate_conversation.validate_asks(
        request.form.getlist("question_key"), [a["question_key"] for a in asks])
    if not result["ok"]:
        return redirect(url_for("gate_view", asked="invalid"))

    round_no = gate.get("round_no") or 1
    clock = get_clock()
    for key in result["keys"]:
        db.insert_row(get_db(), "GateAsk", {
            "id": f"{active['id']}:{round_no}:{key}", "pair_id": active["id"],
            "round_no": round_no, "asked_by": user["user_id"],
            "question_key": key, "asked_at": str(clock),
        })
    # A new question reopens the round: the pause restarts, because there
    # is something new to sit with.
    db.insert_row(get_db(), "StageGate", {**dict(gate), "answers_closed_at": None})
    return redirect(url_for("gate_view"))


@app.route("/gate/respond", methods=["POST"])
@login_required
def gate_respond():
    """Answer one of the questions on the table.

    Scale answers are compared; free text is stored and never shown to the
    other person. It is collected because writing it is what makes someone
    think, not because anyone else will read it.
    """
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    gate = _gate_for_lockin(active["id"]) if active else None
    if gate is None:
        return redirect(url_for("guru_view"))

    key = request.form.get("question_key")
    asks = {a["question_key"] for a in db.fetch_all(get_db(), "GateAsk", pair_id=active["id"])}
    if key not in asks:
        return redirect(url_for("gate_view"))

    db.insert_row(get_db(), "GateResponse", {
        "id": f"{active['id']}:{user['user_id']}:{key}",
        "pair_id": active["id"], "user_id": user["user_id"], "question_key": key,
        "readiness_scale": request.form.get("readiness_scale") or None,
        "answer_text": (request.form.get("answer_text") or "").strip() or None,
    })

    # Once BOTH have answered everything asked, the pause starts. Started
    # once and not restarted by a re-answer — otherwise editing a reply
    # would reset everyone's clock.
    state = _gate_conversation_state(dict(gate), active)
    if state["report"]["complete"] and gate.get("answers_closed_at") is None:
        db.insert_row(get_db(), "StageGate",
                      {**dict(gate), "answers_closed_at": _clock_hours(get_clock())})
    return redirect(url_for("gate_view"))


@app.route("/gate/raise", methods=["POST"])
@login_required
def gate_raise():
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))
    if _gate_for_lockin(active["id"]) is None:
        gate = stage_gate.open_gate(active["id"], "exclusivity_raised",
                                    str(get_clock()), raised_by=user["user_id"])
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

    # 2026-09-04: the pause is enforced here, not merely hidden in the
    # template. Someone who has just read that they see three things
    # differently must not be able to commit in the same minute — that is
    # the behaviour this whole feature exists to prevent, and a disabled
    # button is not a rule.
    if not _gate_conversation_state(dict(gate), active)["may_commit"]:
        return redirect(url_for("gate_view", early="1"))

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
    """Segment H: this no longer signs anything itself.

    It used to run its own playbook-free signature and face check, which
    meant two implementations of one rule — and two places for the wording,
    the refusals and the record to drift apart. Consent for Relationship
    entry is ceremony #4 now, exactly like the date agreement, so this
    route's whole job is to send people to it.

    The gate row is still where the answer LANDS — _mirror_gate_consent()
    writes it when the ceremony completes, so stage_gate.py and everything
    downstream keep reading the columns they always did.
    """
    return redirect(url_for("ceremony_view", kind=ceremony.RELATIONSHIP_ENTRY))


def _mirror_gate_consent() -> None:
    """A completed relationship-entry ceremony is the gate's consent.

    Same shape as _mirror_date_signature(): the ceremony is the front end,
    the existing row stays the source of truth for every rule already
    written against it.
    """
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return
    gate = _gate_for_lockin(active["id"])
    if gate is None:
        return
    role = _my_role_in_lockin(active, user["user_id"])
    db.insert_row(get_db(), "StageGate", {**dict(gate),
                                          f"consent_{role}": 1,
                                          f"biometric_{role}": 1})


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
    """Chemistry is hobbies and activities — the things Guru suggests you
    try together through the DREAM stages. It is NOT the intimacy layer;
    that moved to /boundaries and /expectations, which open on their own
    schedule (see disclosure.py). Sharing one word for both was the
    confusion worth removing.
    """
    user = current_user()
    row = db.fetch_one(get_db(), "User", id=user["user_id"])
    skills = db.load_json_field(row.get("skills_json"), {}) or {}
    chosen = skills.get("activities", {})

    partner_chosen = {}
    couple = find_couple_for_user(user["user_id"]) if user["journey_state"] != "dating" else None
    active = _my_active_lockin(user["user_id"]) if user["journey_state"] == "dating" else None
    partner_id = partner_id_in(couple, user["user_id"]) if couple else (_partner_id_in_lockin(active, user["user_id"]) if active else None)
    if partner_id:
        prow = db.fetch_one(get_db(), "User", id=partner_id)
        if prow:
            partner_chosen = (db.load_json_field(prow.get("skills_json"), {}) or {}).get("activities", {})

    overlap = [
        {"activity": a, "mine": chosen[a], "theirs": partner_chosen[a]}
        for a in onboarding.ACTIVITIES
        if a in chosen and a in partner_chosen
    ]

    return render_template(
        "chemistry.html",
        activities=onboarding.ACTIVITIES,
        buckets=onboarding.BUCKETS,
        chosen=chosen,
        bucket_labels={b[0]: b[2] for b in onboarding.BUCKETS},
        by_bucket=skills.get("by_bucket", {}),
        overlap=overlap,
        has_partner=partner_id is not None,
    )


@app.route("/chemistry/activities", methods=["POST"])
@login_required
def chemistry_set_activities():
    user = current_user()
    submitted = {a: request.form.get(f"act__{a}") for a in onboarding.ACTIVITIES}
    submitted = {a: b for a, b in submitted.items() if b}
    result = onboarding.validate_activities(submitted)
    if not result["ok"]:
        return redirect(url_for("chemistry_view"))
    row = dict(db.fetch_one(get_db(), "User", id=user["user_id"]))
    row["skills_json"] = json.dumps(onboarding.build_skills(result["activities"]), ensure_ascii=False)
    db.insert_row(get_db(), "User", row)
    return redirect(url_for("chemistry_view"))


# ── the intimacy layer, split by when it should be asked ────────────────
# Both write the same ChemistryEntry rows through chemistry.set_entry(),
# so vision.py's Relationship-entry prerequisite check is unchanged. Only
# WHERE and WHEN they are asked has moved.

BOUNDARY_KEYS = ("physical_boundary",)
EXPECTATION_KEYS = ("intimacy_pace", "intimacy_importance", "intimacy_notes", "health_openness")


@app.route("/boundaries")
@login_required
def boundaries_view():
    """Opens once a date is set. A greeting preference is a decision about
    a specific evening with a specific person, not an abstract preference
    about a stranger — asking at sign-up gets answers people did not mean."""
    guard = unlocked_or_redirect("boundaries")
    if guard is not None:
        return guard
    user = current_user()
    entries = db.fetch_all(get_db(), "ChemistryEntry", user_id=user["user_id"])
    return render_template(
        "boundaries.html",
        by_key={e["key"]: e["value"] for e in entries},
        boundary_options=chemistry.PHYSICAL_BOUNDARY_OPTIONS,
    )


@app.route("/expectations")
@login_required
def expectations_view():
    """Opens after the first date. Intimacy expectations and openness to
    discussing sexual health and contraception are questions between two
    people who have met, not sign-up fields."""
    guard = unlocked_or_redirect("expectations")
    if guard is not None:
        return guard
    user = current_user()
    entries = db.fetch_all(get_db(), "ChemistryEntry", user_id=user["user_id"])

    couple = find_couple_for_user(user["user_id"]) if user["journey_state"] != "dating" else None
    active = _my_active_lockin(user["user_id"]) if user["journey_state"] == "dating" else None
    partner_id = partner_id_in(couple, user["user_id"]) if couple else (_partner_id_in_lockin(active, user["user_id"]) if active else None)

    mismatch = None
    if partner_id:
        mismatch = chemistry.on_chemistry_update(entries, db.fetch_all(get_db(), "ChemistryEntry", user_id=partner_id))

    return render_template(
        "expectations.html",
        by_key={e["key"]: e["value"] for e in entries},
        pace_options=chemistry.INTIMACY_PACE_OPTIONS,
        health_options=chemistry.HEALTH_OPENNESS_OPTIONS,
        mismatch=mismatch,
        has_partner=partner_id is not None,
    )


@app.route("/vibes")
@login_required
def vibes_view():
    """The Relationship-entry chemistry keys — love language, how you each
    like to communicate, what makes you feel appreciated. Guru's material,
    so it opens with the Relationship stage."""
    guard = unlocked_or_redirect("relationship")
    if guard is not None:
        return guard
    user = current_user()
    entries = db.fetch_all(get_db(), "ChemistryEntry", user_id=user["user_id"])
    return render_template(
        "vibes.html",
        by_key={e["key"]: e["value"] for e in entries},
        mandatory_keys=chemistry.MANDATORY_KEYS,
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
    # Back to whichever screen asked. These keys now live on three
    # different surfaces (see disclosure.py), so a single hardcoded
    # redirect would bounce people off the page they were filling in.
    back = request.form.get("back")
    if back in ("boundaries_view", "expectations_view", "vibes_view"):
        return redirect(url_for(back))
    return redirect(url_for("chemistry_view"))


# ── The "Next Level" conversation (docs/intimacy-expectations-spec.md Part B)


@app.route("/next-level")
@login_required
def next_level_view():
    guard = unlocked_or_redirect("next_level")
    if guard is not None:
        return guard
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
    guard = unlocked_or_redirect("relationship")
    if guard is not None:
        return guard
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


@app.route("/married")
@login_required
def married_view():
    """Step 37 — the end of the journey.

    Deliberately the only screen in the product with nothing to do on it.
    Everything else asks for a decision, a signature or a slot; this one
    asks for nothing, which is the whole point of arriving. The four
    pillars keep running underneath, because a marriage is not a finish
    line — but the JOURNEY has one, and it should feel like it.
    """
    guard = unlocked_or_redirect("married")
    if guard is not None:
        return guard
    user = current_user()
    couple = find_couple_for_user(user["user_id"])
    if couple is None or couple["stage"] != "married":
        return redirect(url_for("journey_view"))
    partner_id = partner_id_in(couple, user["user_id"])
    partner = with_view_fields(load_user(partner_id))

    # What it took to get here, counted from the record rather than
    # asserted: every ceremony either of them completed along the way.
    signed = [
        dict(row) for row in db.fetch_all(get_db(), "Ceremony")
        if row["user_id"] in (couple["user_a"], couple["user_b"]) and row["completed_at"]
    ]
    by_kind: dict[str, int] = {}
    for row in signed:
        by_kind[row["kind"]] = by_kind.get(row["kind"], 0) + 1

    return render_template(
        "married.html",
        couple=couple,
        partner=partner,
        stage_order=journey.STAGE_ORDER,
        agreements=[
            {"label": ceremony.kind_meta(kind)["label"], "count": count}
            for kind, count in by_kind.items()
        ],
        total_signed=len(signed),
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
        # to_dict() keeps only the first value of a repeated field, which
        # silently drops every multi-select but the first choice. Read
        # each one with getlist so "Italian, Thai" survives as both.
        submitted = {
            **request.form.to_dict(),
            **{key: request.form.getlist(key)
               for key, _, _, _ in onboarding.MULTI_STATS + onboarding.OPTIONAL_MULTI_STATS},
        }
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
            optional_numeric_stats=onboarding.OPTIONAL_NUMERIC_STATS,
            optional_choice_stats=onboarding.OPTIONAL_CHOICE_STATS,
            optional_multi_stats=onboarding.OPTIONAL_MULTI_STATS,
            cities=onboarding.CITIES_FOR_SIGNUP,
            genders=onboarding.GENDERS_FOR_SIGNUP,
            multi_stats=onboarding.MULTI_STATS,
            income_bands=onboarding.INCOME_BANDS,
            mandatory_labels=onboarding.MANDATORY_FIELD_LABELS,
            # City decides currency, which languages lead the list, and
            # which diets do. Asking for any of that separately is a
            # question the city already answered.
            locale=locale_defaults.defaults_for(
                submitted.get("city") or draft.get("city") or onboarding.CITIES_FOR_SIGNUP[0]),
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



# ── Segment B: background verification ─────────────────────────────────
# Steps 6-8 of the Case 1 walkthrough. The provider is stubbed; bgv.py's
# simulate_provider_callback() is the one function a real vendor replaces.


def _verification_statuses(user_id: str) -> dict:
    """This user's field statuses, seeding the rows on first look so the
    screen always has something to render."""
    rows = db.fetch_all(get_db(), "Verification", user_id=user_id)
    if not rows:
        for row in bgv.new_verification_rows(user_id, str(get_clock())):
            db.insert_row(get_db(), "Verification", row)
        rows = db.fetch_all(get_db(), "Verification", user_id=user_id)
    return bgv.statuses_from_rows(rows)


def _save_verification(user_id: str, statuses: dict) -> None:
    """Persist the field statuses, then roll them up into the User row's
    bgv_status and promote the user if verification just completed."""
    stamp = str(get_clock())
    for field, status in statuses.items():
        db.insert_row(
            get_db(), "Verification",
            {"id": f"{user_id}:{field}", "user_id": user_id, "field": field,
             "status": status, "note": None, "updated_at": stamp},
        )

    row = dict(db.fetch_one(get_db(), "User", id=user_id))
    row["bgv_status"] = bgv.aggregate_status(statuses)
    promoted = bgv.promotion_for(row["journey_state"], statuses)
    if promoted:
        row["journey_state"] = promoted
    db.insert_row(get_db(), "User", row)


@app.route("/verify")
@login_required
def verify_view():
    user = current_user()
    statuses = _verification_statuses(user["user_id"])
    return render_template(
        "verify.html",
        fields=bgv.field_view(statuses),
        action=bgv.next_action(statuses),
        account_status=bgv.aggregate_status(statuses),
        outcomes=[{"key": k, "label": v} for k, v in bgv.OUTCOME_LABELS.items()],
        is_verified=bgv.is_verified(statuses),
    )


@app.route("/verify/start", methods=["POST"])
@login_required
def verify_start():
    user = current_user()
    statuses = bgv.start_review(_verification_statuses(user["user_id"]))
    _save_verification(user["user_id"], statuses)
    return redirect(url_for("verify_view"))


@app.route("/verify/simulate", methods=["POST"])
@login_required
def verify_simulate():
    """Stands in for the provider's webhook. A real integration deletes
    this route and receives the callback instead — everything downstream
    of bgv.simulate_provider_callback() stays as it is."""
    user = current_user()
    outcome = request.form.get("outcome", "all_pass")
    if outcome not in bgv.OUTCOMES:
        return redirect(url_for("verify_view"))
    statuses = bgv.simulate_provider_callback(_verification_statuses(user["user_id"]), outcome)
    _save_verification(user["user_id"], statuses)
    return redirect(url_for("verify_view"))


# ── Segment C: the demo clock and the scripted partner ─────────────────
# The week machine gates on a simulated clock only the admin screen could
# move. This lets a viewer walk Monday into Tuesday from inside the
# journey, which is what makes steps 9-13 reachable at all.


@app.route("/demo/advance", methods=["POST"])
def demo_advance():
    if not demo.is_enabled():
        abort(404)
    step = request.form.get("step", "day")
    if step in demo.STEP_HOURS:
        set_clock(demo.advance(get_clock(), step))
    back = request.form.get("back") or request.referrer or url_for("dashboard")
    return redirect(back)


@app.route("/demo/partner", methods=["POST"])
@login_required
def demo_partner():
    """Put one counterpart in the pool who is guaranteed to match this
    user, in both directions. Built to satisfy matching.fits_filters, not
    to bypass it — demo.verify_pairing() runs the real function, and this
    refuses rather than seeding a partner who would not actually match."""
    if not demo.is_enabled():
        abort(404)
    user = current_user()
    partner_id = demo.partner_id_for(user["user_id"])
    partner = demo.build_partner_for(user, partner_id)

    checks = demo.verify_pairing(user, partner)
    if not all(checks.values()):
        return render_template("demo_partner_failed.html", checks=checks, user=user), 409

    row = to_user_row(partner, journey_state="dating")
    row["bgv_status"] = "verified"
    db.insert_row(get_db(), "User", row)
    for field in bgv.FIELD_KEYS:
        db.insert_row(
            get_db(), "Verification",
            {"id": f"{partner_id}:{field}", "user_id": partner_id, "field": field,
             "status": bgv.VERIFIED, "note": "demo partner", "updated_at": str(get_clock())},
        )
    return redirect(url_for("week"))


# ── Segment D: the four fees ───────────────────────────────────────────
# No gateway. payments.simulate_gateway_callback() is where Razorpay's
# webhook lands. The entitlement question is answered in exactly one
# place — payments.has_paid() — so no screen invents its own rule.


def _payment_scope(user: dict, purpose: str) -> str | None:
    """What this fee is being charged FOR. A fee is never 'paid forever':
    the availability fee is per date, so the next date charges again."""
    if purpose == payments.GURU:
        return f"week-{get_week_number()}"
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return None
    if purpose == payments.AVAILABILITY:
        return active["id"]
    if purpose == payments.AGREEMENT:
        plan = _dateplan_for_lockin(active["id"])
        return plan["id"] if plan else None
    if purpose == payments.STAGE_GATE:
        return active["id"]
    return None


def _has_paid(user_id: str, purpose: str, scope_id: str) -> bool:
    rows = db.fetch_all(get_db(), "Payment", user_id=user_id)
    return payments.has_paid(rows, user_id, purpose, scope_id)


def _require_payment(user: dict, purpose: str):
    """Returns a redirect to the checkout when this is unpaid, or None to
    let the caller carry on. Callers use it as an early return."""
    if not payments.is_enabled():
        return None
    scope_id = _payment_scope(user, purpose)
    if scope_id is None:
        return None
    if _has_paid(user["user_id"], purpose, scope_id):
        return None
    return redirect(url_for("pay_view", purpose=purpose))


@app.route("/pay/<purpose>")
@login_required
def pay_view(purpose):
    if purpose not in payments.PURPOSES:
        abort(404)
    user = current_user()
    scope_id = _payment_scope(user, purpose)
    if scope_id is None:
        return redirect(url_for("week"))
    paid = _has_paid(user["user_id"], purpose, scope_id)
    return render_template(
        "pay.html",
        view=payments.checkout_view(purpose, scope_id, paid),
        next_url=request.args.get("next") or url_for("week"),
    )


@app.route("/pay/<purpose>/confirm", methods=["POST"])
@login_required
def pay_confirm(purpose):
    """The stub gateway. Writes a Payment row and marks it paid; no money
    moves and the screen says so."""
    if purpose not in payments.PURPOSES:
        abort(404)
    user = current_user()
    scope_id = _payment_scope(user, purpose)
    if scope_id is None:
        return redirect(url_for("week"))

    row = payments.payment_row(user["user_id"], purpose, scope_id, str(get_clock()))
    db.insert_row(get_db(), "Payment", payments.simulate_gateway_callback(row, succeeded=True))

    nxt = request.form.get("next") or url_for("week")
    return redirect(nxt)


# ═══════════════════════════════════════════════════════════════════════
#  SEGMENTS E, F, G — the ceremony, the debrief, and Guru's hub
# ═══════════════════════════════════════════════════════════════════════


# ── Segment E: the ceremony ────────────────────────────────────────────
# playbook -> sign -> face -> verified. Six occasions, one implementation
# (ceremony.py), because building it six times means six places to get the
# rules slightly different in.


def _ceremony_scope(kind: str) -> str | None:
    """What this ceremony is ABOUT for this user right now. The same kind
    recurs — a new agreement for every date, a new checkpoint for every
    stage — so the scope is what keeps them apart."""
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return None
    if kind == ceremony.DATE_AGREEMENT:
        plan = _dateplan_for_lockin(active["id"])
        return plan["id"] if plan else None
    return active["id"]


def _ceremony_state(kind: str, scope_id: str) -> dict:
    user = current_user()
    row = db.fetch_one(get_db(), "Ceremony", user_id=user["user_id"], kind=kind, scope_id=scope_id)
    if row is None:
        row = ceremony.new_state(user["user_id"], kind, scope_id, str(get_clock()))
        db.insert_row(get_db(), "Ceremony", row)
    return dict(row)


def _save_ceremony(state: dict) -> dict:
    if ceremony.is_complete(state):
        state = ceremony.complete(state, str(get_clock()))
    db.insert_row(get_db(), "Ceremony", _bool_ints(state))
    return state


def _date_ceremony_context(scope_id: str) -> dict:
    """Fill the seven clauses from what both people already told us.
    Nothing here is typed by hand — the agreement is a readback."""
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    plan = _dateplan_for_lockin(active["id"]) if active else None
    if plan is None:
        return {}
    entries = db.fetch_all(get_db(), "ChemistryEntry", user_id=user["user_id"])
    greeting = {e["key"]: e["value"] for e in entries}.get("physical_boundary")
    partner = load_user(_partner_id_in_lockin(active, user["user_id"]))
    return {
        "slot": humanise_slot(plan.get("datetime")),
        "meal": plan.get("meal"),
        "cuisine": plan.get("cuisine"),
        "budget": plan.get("budget_estimate"),
        "bill_split": dateplan.BILL_SPLIT_LABELS.get(plan.get("bill_split"), plan.get("bill_split")),
        "my_diet": (user.get("stats") or {}).get("diet"),
        "their_diet": (partner.get("stats") or {}).get("diet") if partner else None,
        "greeting": greeting,
    }


@app.route("/ceremony/<kind>")
@login_required
def ceremony_view(kind):
    if kind not in ceremony.KINDS:
        abort(404)
    guard = unlocked_or_redirect("ceremony")
    if guard is not None:
        return guard
    scope_id = _ceremony_scope(kind)
    if scope_id is None:
        return redirect(url_for("guru_view"))

    state = _ceremony_state(kind, scope_id)
    meta = ceremony.kind_meta(kind)

    # The fee, if this kind carries one, uses the SAME scope helper the
    # rest of payments.py uses — a ceremony must never be reachable by a
    # route the checkout would have stopped.
    fee_gate = None
    if meta["fee"] and payments.is_enabled():
        fee_scope = _payment_scope(current_user(), meta["fee"])
        if fee_scope is not None and not _has_paid(current_user()["user_id"], meta["fee"], fee_scope):
            fee_gate = meta["fee"]

    ctx = _date_ceremony_context(scope_id) if kind == ceremony.DATE_AGREEMENT else {}
    peers = [dict(p) for p in db.fetch_all(get_db(), "Ceremony", kind=kind, scope_id=scope_id)]

    return render_template(
        "ceremony.html",
        kind=kind,
        meta=meta,
        state=state,
        step=ceremony.next_step(state),
        steps=ceremony.progress(state),
        acks=ceremony.acks_for(kind),
        signed_acks=ceremony.signed_acks(state),
        unsigned=request.args.get("unsigned") == "1",
        clauses=ceremony.clauses_for(kind, ctx),
        complete=ceremony.is_complete(state),
        fee_gate=fee_gate,
        fee_label=payments.amount_label(fee_gate) if fee_gate else None,
        face_failed=request.args.get("face") == "failed",
        waiting_on_partner=(
            ceremony.is_complete(state)
            and len([p for p in peers if ceremony.is_complete(p)]) < 2
        ),
    )


@app.route("/ceremony/<kind>/step", methods=["POST"])
@login_required
def ceremony_step(kind):
    """One route for all three actions. Which step runs is decided by
    ceremony.next_step(), never by which form was posted — you cannot sign
    a playbook you have not opened, whatever the request body says."""
    if kind not in ceremony.KINDS:
        abort(404)
    guard = unlocked_or_redirect("ceremony")
    if guard is not None:
        return guard
    scope_id = _ceremony_scope(kind)
    if scope_id is None:
        return redirect(url_for("guru_view"))

    meta = ceremony.kind_meta(kind)
    if meta["fee"]:
        # Segment I: the ₹2,999 stage-gate fee is charged HERE, at the
        # checkpoint's ceremony, rather than sitting in the fee table
        # unconnected at both ends as it did before.
        gate = _require_payment(current_user(), meta["fee"])
        if gate is not None:
            return gate

    state = _ceremony_state(kind, scope_id)
    step = ceremony.next_step(state)
    face_failed = False

    if step == ceremony.PLAYBOOK:
        state = ceremony.ack_playbook(state)
    elif step == ceremony.SIGN:
        state = ceremony.sign(
            state, request.form.get("signed_name", ""),
            request.form.getlist("acks"), str(get_clock()),
        )
        if ceremony.next_step(state) == ceremony.SIGN:
            # Refused — a blank name or an unticked term. Say which rather
            # than bouncing them back to an unchanged page with no reason.
            return redirect(url_for("ceremony_view", kind=kind, unsigned="1"))
    elif step == ceremony.FACE:
        # Reuses the existing stub rather than adding a second one. A fresh
        # seed every attempt, so a retry is a genuinely new draw — the
        # /plan/sign flow had to grow that fix after a user could get
        # permanently stuck repeating one deterministic failure.
        if dateplan.verify_face(current_user()["user_id"], seed=uuid.uuid4().hex):
            state = ceremony.capture_face(state)
        else:
            face_failed = True

    state = _save_ceremony(state)

    # Each ceremony writes back into whatever row the rest of the app
    # already reads, so nothing downstream had to learn about Ceremony.
    if ceremony.is_complete(state):
        if kind == ceremony.DATE_AGREEMENT:
            _mirror_date_signature()
        elif kind == ceremony.RELATIONSHIP_ENTRY:
            _mirror_gate_consent()
        elif kind == ceremony.STAGE_GATE:
            _mirror_stage_gate()

    if face_failed:
        return redirect(url_for("ceremony_view", kind=kind, face="failed"))
    return redirect(url_for("ceremony_view", kind=kind))


def _ceremony_pair_state(kind: str, scope_id: str, active: dict) -> dict:
    """Where a two-sided ceremony stands for this pair.

    Segment G's whole shape: a ceremony gates the thing it is about, and
    one signature gates nothing. Both flows — contact sharing and the home
    invite — ask this the same question rather than each inventing its own
    idea of "signed".
    """
    rows = [dict(r) for r in db.fetch_all(get_db(), "Ceremony", kind=kind, scope_id=scope_id)]
    mine = next((r for r in rows if r["user_id"] == current_user()["user_id"]), None)
    return {
        "kind": kind,
        "mine_complete": mine is not None and ceremony.is_complete(mine),
        "both_complete": ceremony.both_complete(rows, active["user_a"], active["user_b"]),
        "url": url_for("ceremony_view", kind=kind),
        "label": ceremony.kind_meta(kind)["label"],
    }


def _mirror_date_signature() -> None:
    """A completed date agreement is a signed DatePlan.

    dateplan.is_confirmed() / payment_open() / the whole feedback cycle all
    read Signature rows. Rather than teach them about Ceremony, the
    ceremony writes the row they already expect — face_verified is True
    because the ceremony's own face step has just passed, and every ack is
    True because the playbook it acknowledged contains all four."""
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    plan = _dateplan_for_lockin(active["id"]) if active else None
    if plan is None:
        return
    # The ceremony's ack keys for a date agreement are dateplan.ACK_FIELDS,
    # deliberately, so what gets mirrored is what the person actually
    # ticked rather than a blanket True. ceremony.sign() will not complete
    # without all four, so this is always full — but it is full because
    # they said so, not because this line says so.
    ticked = set(ceremony.signed_acks(_ceremony_state(ceremony.DATE_AGREEMENT, plan["id"])))
    sig = dateplan.sign(
        plan["id"], user["user_id"],
        {field: field in ticked for field in dateplan.ACK_FIELDS},
        signed_at=str(get_clock()), face_verified=True,
    )
    db.insert_row(get_db(), "Signature",
                  {"id": f"{plan['id']}:{user['user_id']}", **_bool_ints(sig)})
    signatures = db.fetch_all(get_db(), "Signature", dateplan_id=plan["id"])
    if dateplan.is_confirmed(signatures, active["user_a"], active["user_b"]) and plan["status"] != "confirmed":
        db.insert_row(get_db(), "DatePlan", {**plan, "status": "confirmed"})


def _mirror_stage_gate() -> None:
    """Ceremonies #5 and #6 — the Engaged and Married checkpoints.

    Same kind, different scope: stage_gate is scoped to the LockIn, so
    each stage's checkpoint is its own row and signing for one never reads
    as signing for the next.
    """
    _mirror_gate_consent()


# ── Segment F: the post-date debrief ───────────────────────────────────
# The rules already existed — guru_dating enforces two green flags and at
# most two red, outcomes.apply_resolution() runs the three-way branch, and
# plan_feedback_flags()/plan_feedback() persist both. What was missing was
# a screen of its own; this one posts to those same two routes rather than
# growing a second copy of the rules that could drift from the first.


def _debrief_opens_label(plan: dict) -> str:
    slot = _plan_slot(plan)
    if slot is None:
        return "shortly"
    day = clock_module.DAYS_OF_WEEK[slot[0]]
    return f"{day} {slot[1]:02d}:00"


@app.route("/debrief")
@login_required
def debrief_view():
    guard = unlocked_or_redirect("debrief")
    if guard is not None:
        return guard
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    plan = _dateplan_for_lockin(active["id"]) if active else None
    if plan is None:
        return redirect(url_for("week"))

    row = db.fetch_one(get_db(), "DateOutcome", dateplan_id=plan["id"])
    outcome = _outcome_from_row(row) if row else None
    role = _my_role_in_lockin(active, user["user_id"])
    my_green = (outcome or {}).get(f"{role}_green_flags") or []
    partner_id = _partner_id_in_lockin(active, user["user_id"])
    partner = load_user(partner_id)

    clock = get_clock()
    return render_template(
        "debrief.html",
        plan=plan,
        is_open=_debrief_is_open(plan, clock),
        opens_at=_debrief_opens_label(plan),
        happened=(outcome or {}).get("happened", 1),
        no_show_reported=bool(outcome) and not outcome.get("happened", 1),
        green_flags=guru_dating.GREEN_FLAGS,
        red_flags=guru_dating.RED_FLAGS,
        min_green=guru_dating.MIN_GREEN_FLAGS,
        max_red=guru_dating.MAX_RED_FLAGS,
        my_green=my_green,
        my_red=(outcome or {}).get(f"{role}_red_flags") or [],
        flags_given=len(my_green) >= guru_dating.MIN_GREEN_FLAGS,
        my_decision=(outcome or {}).get(f"{role}_decision"),
        partner_name=display_name(partner_id, (partner or {}).get("gender", "female")),
    )


@app.route("/align", methods=["GET", "POST"])
@login_required
def align_view():
    """Budget, diet and cuisine — asked here rather than at sign-up.

    2026-09-04, user's rule: these are needed for a date, not for a
    profile. Asking at sign-up puts three questions between a stranger and
    their first match, and invites "it depends" as the honest answer. Asked
    now, there is a real evening waiting on them.

    Answers are written into stats, so someone who fills them in once is
    not asked again — and can change them for the next date.
    """
    guard = unlocked_or_redirect("align")
    if guard is not None:
        return guard
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))

    error = None
    if request.method == "POST":
        form = {**request.form.to_dict(), "cuisine": request.form.getlist("cuisine")}
        result = date_alignment.validate(form, user.get("city"))
        if result["ok"]:
            row = dict(db.fetch_one(get_db(), "User", id=user["user_id"]))
            stats = json.loads(row["stats_json"])
            stats.update(result["stats"])
            row["stats_json"] = json.dumps(stats, ensure_ascii=False)
            db.insert_row(get_db(), "User", row)
            return redirect(url_for("calendar_view"))
        error = result["error"]

    partner_id = _partner_id_in_lockin(active, user["user_id"])
    partner = load_user(partner_id)
    return render_template(
        "align.html",
        error=error,
        fields=date_alignment.FIELDS,
        labels=date_alignment.LABELS,
        blurbs=date_alignment.BLURBS,
        options={f: date_alignment.options_for(f, user.get("city")) for f in date_alignment.FIELDS},
        saved=user["stats"],
        partner_name=display_name(partner_id, (partner or {}).get("gender", "female")),
        partner_pending=date_alignment.missing((partner or {}).get("stats", {})),
    )


@app.route("/plan/cancel", methods=["POST"])
@login_required
def plan_cancel():
    """Cancel a confirmed date.

    2026-09-04, user's rule: dates are set on Thursday for the weekend, so
    a free cancellation is an invitation to change your mind at everyone
    else's expense. Inside 24 hours it costs a fee AND files a late_cancel
    strike; outside it, nothing is charged and nothing is recorded —
    punishing honest early notice teaches people to no-show instead, which
    is the behaviour this is trying to prevent.
    """
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    plan = _dateplan_for_lockin(active["id"]) if active else None
    if plan is None or plan["status"] != "confirmed":
        return redirect(url_for("week"))

    clock = get_clock()
    terms = _cancellation_terms(plan, clock)

    db.insert_row(get_db(), "DatePlan", {**plan, "status": "cancelled",
                                         "cancel_fee": terms["fee_inr"]})

    if terms["late"]:
        db.insert_row(get_db(), "ComplianceEvent", {
            "id": uuid.uuid4().hex[:12],
            **outcomes.record_compliance_event(
                user["user_id"], "late_cancel", clock.week, value="late_cancel",
                notes=terms["reason"],
            ),
        })
        if payments.is_enabled():
            row = payments.payment_row(user["user_id"], payments.CANCELLATION, plan["id"], str(clock))
            db.insert_row(get_db(), "Payment", {**row, "status": payments.PENDING})

    db.insert_row(get_db(), "LockIn", {**active, **lockin.release(active, "date cancelled")})
    return redirect(url_for("week"))


@app.route("/debrief/no-show", methods=["POST"])
@login_required
def debrief_no_show():
    """Report that the other person did not turn up.

    Kept separate from the flag form on purpose: green flags are mandatory
    before a decision, and demanding two nice things about someone who
    left you sitting there is absurd. A no-show records the outcome as
    not-happened, files a compliance strike against them, and releases the
    lock-in without asking for flags at all.
    """
    guard = unlocked_or_redirect("debrief")
    if guard is not None:
        return guard
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    plan = _dateplan_for_lockin(active["id"]) if active else None
    if plan is None:
        return redirect(url_for("week"))

    clock = get_clock()
    if not _debrief_is_open(plan, clock):
        return redirect(url_for("debrief_view"))

    partner_id = _partner_id_in_lockin(active, user["user_id"])
    row = db.fetch_one(get_db(), "DateOutcome", dateplan_id=plan["id"])
    outcome = _outcome_from_row(row) if row else outcomes.record_outcome(plan["id"], True, None, None)
    outcome.setdefault("id", f"outcome:{plan['id']}")
    outcome["happened"] = False
    role = _my_role_in_lockin(active, user["user_id"])
    outcome[f"{role}_decision"] = "pass"
    outcome[f"{role}_reason"] = "They did not turn up."
    db.insert_row(get_db(), "DateOutcome", _outcome_to_row(outcome))

    db.insert_row(get_db(), "ComplianceEvent", {
        "id": uuid.uuid4().hex[:12],
        **outcomes.record_compliance_event(
            partner_id, "no_show", clock.week, value="no_show",
            notes=f"Reported by their match for {plan['datetime']}",
        ),
    })

    db.insert_row(get_db(), "LockIn", {**active, **lockin.release(active, "no-show reported")})
    return redirect(url_for("week"))


# ── Segment G: Guru's hub ──────────────────────────────────────────────
# The one tab that is always there once you are verified, carrying every
# contextual screen as a card. This is what replaced four separate tabs.


def _guru_facts(user: dict) -> dict:
    """The handful of things a milestone cannot express. Anything missing
    reads as not-yet-done, so Guru under-promises rather than telling
    someone a step is finished when it is not."""
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return {"married": user["journey_state"] == "married"}
    aligned = date_alignment.is_complete(user["stats"])
    married = user["journey_state"] == "married"
    gate_facts = _gate_facts(user, active)
    plan = _dateplan_for_lockin(active["id"])
    if plan is None:
        return {"aligned": aligned, "married": married, **gate_facts}
    signature = db.fetch_one(get_db(), "Signature", dateplan_id=plan["id"], user_id=user["user_id"])
    entries = db.fetch_all(get_db(), "ChemistryEntry", user_id=user["user_id"])
    row = db.fetch_one(get_db(), "DateOutcome", dateplan_id=plan["id"])
    outcome = _outcome_from_row(row) if row else {}
    role = _my_role_in_lockin(active, user["user_id"])
    return {
        "agreement_signed": signature is not None and dateplan.is_fully_acknowledged(dict(signature)),
        "boundary_set": any(e["key"] == "physical_boundary" and e["value"] for e in entries),
        # An unsigned agreement for a date that already happened is not a
        # thing to chase — the evening is over. Guru asked for it anyway,
        # which pushed the debrief down the list on the one night the
        # debrief is the whole point.
        "date_done": row is not None,
        "flags_given": len(outcome.get(f"{role}_green_flags") or []) >= guru_dating.MIN_GREEN_FLAGS,
        "decision_made": outcome.get(f"{role}_decision") is not None,
        "aligned": aligned,
        "married": married,
        **gate_facts,
    }


def _gate_facts(user: dict, active: dict) -> dict:
    """Where an open stage gate stands, for Guru.

    2026-09-04, user's rule: "If one of them expressed moving to next
    stage it should be visible or first thing someone wants to see."
    Guru had no knowledge of the gate at all — it was one tile among
    nine. These three facts are what it needs to put it first and say
    the true thing about it.
    """
    gate = _gate_for_lockin(active["id"])
    if gate is None or gate["status"] not in ("open", "must_resolve"):
        return {"gate_open": False}

    round_no = gate["round_no"] or 1
    asked = [a["question_key"] for a in db.fetch_all(get_db(), "GateAsk", pair_id=active["id"])
             if (a["round_no"] or 1) == round_no]
    mine = {r["question_key"] for r in
            db.fetch_all(get_db(), "GateResponse", pair_id=active["id"], user_id=user["user_id"])}
    raised_by = gate["raised_by"] if "raised_by" in gate.keys() else None
    partner_id = _partner_id_in_lockin(active, user["user_id"])
    partner = load_user(partner_id)
    # with_view_fields is where `name` comes from — the raw row has none.
    partner = with_view_fields(partner) if partner else None
    return {
        "gate_open": True,
        "partner_name": partner.get("name") if partner else None,
        # None means neither of them moved first — they arrived together
        # at the debrief — so nobody gets named.
        "gate_raised_by_partner": raised_by is not None and raised_by != user["user_id"],
        "gate_waiting_on_me": [k for k in asked if k not in mine] != [],
        "gate_nothing_asked_yet": not asked,
    }


@app.route("/after-date")
@login_required
def after_date_view():
    """Everything that opens after a first date, on one screen.

    2026-09-04, user's rule: "post date expectations all of these can be
    clubbed together". Expectations, contact sharing and the next-level
    conversation were three cards in Guru, and three cards asking to be
    chosen between is the confusion the review was about. They are one
    screen with three sections now — the same routes still exist for the
    forms to post to, they just are not three separate invitations.
    """
    guard = unlocked_or_redirect("after_date")
    if guard is not None:
        return guard
    user = current_user()
    active = _my_active_lockin(user["user_id"])
    if active is None:
        return redirect(url_for("week"))

    partner_id = _partner_id_in_lockin(active, user["user_id"])
    partner = with_view_fields(load_user(partner_id))
    entries = {e["key"]: e["value"]
               for e in db.fetch_all(get_db(), "ChemistryEntry", user_id=user["user_id"])}
    share = _ceremony_pair_state(ceremony.CONTACT_SHARE, active["id"], active)
    requests = db.fetch_all(get_db(), "ContactRequest", pair_id=active["id"])

    return render_template(
        "after_date.html",
        partner=partner,
        intimacy_keys=chemistry.INTIMACY_MANDATORY_KEYS,
        entries=entries,
        answered=len([k for k in chemistry.INTIMACY_MANDATORY_KEYS if entries.get(k)]),
        total=len(chemistry.INTIMACY_MANDATORY_KEYS),
        share_ceremony=share,
        shared_channels=[r for r in requests if r["status"] == "accepted"],
        pending_channels=[r for r in requests if r["status"] == "pending"],
        unlocked=escalations.unlocks_available(active["dates_completed"]),
    )


@app.route("/guru")
@login_required
def guru_view():
    guard = unlocked_or_redirect("guru")
    if guard is not None:
        return guard
    user = current_user()
    reached = _milestones_for(user)
    action = guru.next_action(reached, facts=_guru_facts(user))
    # 2026-09-04, user's rule: "Keep this intuitive rather than with
    # multiple options, which is very confusing." One answer, two cards,
    # and one link to the rest — not seven tiles competing with the
    # answer above them.
    open_cards = guru.cards(reached, exclude_endpoint=action["endpoint"])
    return render_template(
        "guru.html",
        cards=open_cards[:guru.MAX_CARDS],
        more=max(len(open_cards) - guru.MAX_CARDS, 0),
        action=action,
    )


@app.route("/guru/everything")
@login_required
def guru_all_view():
    """Every door currently open, for when the two on Guru are not it.

    The cap on Guru is a cap on what competes with the answer, not on
    what you are allowed to reach. Nothing is hidden — it is one link
    further away.
    """
    guard = unlocked_or_redirect("guru")
    if guard is not None:
        return guard
    user = current_user()
    reached = _milestones_for(user)
    return render_template("guru_all.html", cards=guru.cards(reached))


def _mutually_open_pairs(limit: int = 25) -> list[dict]:
    """Verified pairs who can actually match each other (Segment J, 40b).

    Finding a testable pair used to mean a SQL query against the deployed
    database — which is a poor answer to "who do I click to try this?".
    This runs matching.mutual_open() over the pool directly, so it cannot
    drift from the rules the week machine uses.
    """
    pool = [u for u in load_pool()
            if u["bgv_status"] == "verified" and u["journey_state"] == "dating"]
    locked = _active_lockin_ids()
    pairs = []
    for i, a in enumerate(pool):
        if a["user_id"] in locked:
            continue
        for b in pool[i + 1:]:
            if b["user_id"] in locked:
                continue
            if not matching.mutual_open(a, b):
                continue
            pairs.append({
                "a": with_view_fields(a), "b": with_view_fields(b),
                "city": a["city"],
            })
            if len(pairs) >= limit:
                return pairs
    return pairs


@app.route("/admin/pairs")
def admin_pairs():
    """Who can be used to walk the journey, right now, in this database."""
    return render_template("admin_pairs.html", pairs=_mutually_open_pairs(), week=get_week_number())


@app.route("/admin/reset-walkthrough", methods=["POST"])
def admin_reset_walkthrough():
    """Put a pair back to step 1 (Segment J, step 40).

    Deletes every row a run through the journey wrote for these two and
    returns both to a verified, dating, unmatched state — then resets the
    clock to Monday noon so the week starts over with them. The table
    order comes from demo.RESET_TABLES_IN_ORDER, children first, because
    getting it wrong leaves the pair in a worse state than the one being
    reset.
    """
    user_id = (request.form.get("user_id") or "").strip()
    partner_id = (request.form.get("partner_id") or "").strip() or None
    if not user_id:
        return redirect(url_for("admin_pairs"))

    plan = demo.reset_plan(user_id, partner_id)
    conn = get_db()
    ids = set(plan["user_ids"])

    # Every lock-in either of them is in, resolved UP FRONT. Most of the
    # journey's rows hang off a lock-in rather than a user, and matching
    # them by picking a user id out of the lock-in's own id string is the
    # kind of guess that leaves an orphan behind and fails on the parent
    # delete three tables later.
    lockin_ids = {row["id"] for row in db.fetch_all(conn, "LockIn")
                  if row["user_a"] in ids or row["user_b"] in ids}
    # A DatePlan's id is what Signature and DateOutcome point at.
    plan_ids = {row["id"] for row in db.fetch_all(conn, "DatePlan")
                if row["lockin_id"] in lockin_ids}

    for table in plan["tables"]:
        for row in db.fetch_all(conn, table):
            row = dict(row)
            if (
                {row.get("user_id"), row.get("requester_id"), row.get("owner_id"),
                 row.get("candidate_id")} & ids
                or row.get("id") in lockin_ids
                or row.get("pair_id") in lockin_ids
                or row.get("lockin_id") in lockin_ids
                or row.get("dateplan_id") in plan_ids
            ):
                db.delete_row(conn, table, row["id"])

    for uid in plan["user_ids"]:
        existing = db.fetch_one(conn, "User", id=uid)
        if existing is not None:
            db.insert_row(conn, "User", {**dict(existing),
                                         "journey_state": plan["journey_state"],
                                         "bgv_status": plan["bgv_status"]})

    set_clock(clock_module.SimulationClock.at(get_week_number(), "Mon", 12))
    return redirect(url_for("admin_pairs"))


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
