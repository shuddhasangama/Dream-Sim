"""What is open to a user right now, and what is not yet (Segment G).

Two problems, one mechanism.

FIRST: some things must not be askable too early. Intimacy expectations and
openness to discussing sexual health belong after a couple has actually
met, not on a sign-up form. A physical-boundary preference belongs once a
date is set, because that is when it becomes a real decision about a real
evening rather than an abstract preference about a stranger. Asking sooner
is not just awkward, it produces answers people did not mean.

SECOND: the navigation had grown to eleven links, most of which do nothing
for a user who has not matched yet. Escalations, Gate, Next Level and
Relationship are all meaningless before there is another person involved.

Both are the same question — "has this user reached the point where X makes
sense?" — so both are answered here, from one ordered list of milestones
and one table of surfaces. Tuning what appears when is editing SURFACES,
not hunting through templates for `{% if %}`.

Naming rule (docs/CLAUDE.md): never the word "contract" in identifiers.

Pure functions. The caller supplies the facts; nothing here touches the
database.
"""

from __future__ import annotations

from typing import Any

# ── milestones, in the order a user passes them ───────────────────────────
# Ordered, and upward-closed: reaching one implies every earlier one. That
# is what lets a surface declare a single unlock point instead of a
# condition, and it is why `milestones_for()` folds later states down.

REGISTERED = "registered"      # signed up, three steps done
VERIFIED = "verified"          # BGV cleared, in the matching pool
MATCHED = "matched"            # locked in with someone
DATE_SET = "date_set"          # a plan exists for a specific slot
FIRST_DATE = "first_date"      # the first date actually happened
RELATIONSHIP = "relationship"  # exclusivity agreed, Couple row exists

ORDER = [REGISTERED, VERIFIED, MATCHED, DATE_SET, FIRST_DATE, RELATIONSHIP]
_RANK = {name: i for i, name in enumerate(ORDER)}

MILESTONE_LABELS = {
    REGISTERED: "Signed up",
    VERIFIED: "Verified",
    MATCHED: "Locked in with someone",
    DATE_SET: "A date is set",
    FIRST_DATE: "First date done",
    RELATIONSHIP: "In a relationship",
}

RELATIONSHIP_STATES = ("relationship", "engaged", "married")


def milestones_for(
    *,
    bgv_status: str,
    journey_state: str,
    has_active_lockin: bool = False,
    has_dateplan: bool = False,
    has_date_outcome: bool = False,
) -> set[str]:
    """Everything this user has reached.

    Upward-closed on purpose: a user in the Relationship stage has plainly
    had a first date even if the outcome row is missing, and reading that
    literally would hide the very screens they need. The rank fold at the
    end is what guarantees it, so no caller has to remember.
    """
    reached = {REGISTERED}

    if bgv_status == "verified":
        reached.add(VERIFIED)
    if has_active_lockin:
        reached.add(MATCHED)
    if has_dateplan:
        reached.add(DATE_SET)
    if has_date_outcome:
        reached.add(FIRST_DATE)
    if journey_state in RELATIONSHIP_STATES:
        reached.add(RELATIONSHIP)

    highest = max((_RANK[m] for m in reached), default=0)
    return {name for name in ORDER if _RANK[name] <= highest}


def has_reached(milestones: set[str], milestone: str) -> bool:
    return milestone in milestones


# ── the surfaces ──────────────────────────────────────────────────────────
# ONE table. `unlocks_at` is the milestone that opens it; `retires_at`, if
# set, is the milestone that closes it again (Verify is pointless once you
# are verified). `nav` false means the screen exists but does not earn a
# permanent link — it is reached from the flow that needs it.

SURFACES = [
    # key            label            endpoint             unlocks_at    retires_at    nav
    ("dashboard",    "Dashboard",     "dashboard",         REGISTERED,   None,         True),
    ("verify",       "Verify",        "verify_view",       REGISTERED,   VERIFIED,     True),
    ("vision",       "Vision",        "vision_view",       REGISTERED,   None,         True),
    ("chemistry",    "Chemistry",     "chemistry_view",    REGISTERED,   None,         True),
    # REACH and the weekly rotation are the DATING machine. Once a couple
    # is exclusive they are not just unused, they are the wrong thing to
    # be offering, so both retire rather than lingering.
    ("reach",        "REACH",         "reach",             VERIFIED,     RELATIONSHIP, True),
    ("week",         "Week",          "week",              VERIFIED,     RELATIONSHIP, True),
    # Guru is the hub for everything contextual. Giving each of those a
    # tab of its own is what produced eleven links; they are cards in
    # guru.py instead, and this is the one tab that carries them.
    ("guru",         "Guru",          "guru_view",         VERIFIED,     None,         True),
    ("calendar",     "Calendar",      "calendar_view",     MATCHED,      None,         False),
    ("plan",         "Date plan",     "plan_view",         DATE_SET,     None,         False),
    # Boundaries belong to a specific date, so they are reached from that
    # date's plan rather than from a permanent link.
    ("boundaries",   "Boundaries",    "boundaries_view",   DATE_SET,     None,         False),
    ("debrief",      "Debrief",       "debrief_view",      DATE_SET,     None,         False),
    # Ceremony's endpoint takes a <kind>, so it can never be a nav link —
    # it is always entered from the thing being agreed to.
    ("ceremony",     "Ceremony",      "ceremony_view",     MATCHED,      None,         False),
    ("expectations", "Expectations",  "expectations_view", FIRST_DATE,   None,         False),
    ("escalations",  "Sharing",       "escalations_view",  FIRST_DATE,   RELATIONSHIP, False),
    # Next Level is OFFERED on a material pace mismatch (next_level.py),
    # not browsed. A permanent link would invite people into a
    # conversation nothing has suggested they need.
    ("next_level",   "Next level",    "next_level_view",   FIRST_DATE,   None,         False),
    ("gate",         "Gate",          "gate_view",         FIRST_DATE,   RELATIONSHIP, False),
    ("relationship", "Relationship",  "relationship_view", RELATIONSHIP, None,         True),
    ("vibes",        "Vibes",         "vibes_view",        RELATIONSHIP, None,         False),
    ("journey",      "Journey",       "journey_view",      RELATIONSHIP, None,         True),
]

# The cap this table is tuned against. The navigation had grown to eleven
# links; test_disclosure asserts no stage exceeds this, so the creep
# cannot come back unnoticed.
MAX_NAV_LINKS = 8

BY_KEY = {key: (key, label, endpoint, unlocks, retires, nav)
          for key, label, endpoint, unlocks, retires, nav in SURFACES}


def is_open(key: str, milestones: set[str]) -> bool:
    """Whether this surface is available to a user at these milestones.
    Unknown keys are open — this decides visibility, and a typo here must
    not silently lock someone out of a screen that has no rule."""
    entry = BY_KEY.get(key)
    if entry is None:
        return True
    _, _, _, unlocks, retires, _ = entry
    if unlocks not in milestones:
        return False
    if retires is not None and retires in milestones:
        return False
    return True


def nav_for(milestones: set[str], *, reach_locked: bool = False) -> list[dict[str, Any]]:
    """The navigation links to render, in order.

    reach_locked is passed through rather than folded into the milestones
    because it is not a milestone: REACH closes for the week once the
    match run has happened, and reopens. Milestones only move forwards.
    """
    links = []
    for key, label, endpoint, _unlocks, _retires, nav in SURFACES:
        if not nav or not is_open(key, milestones):
            continue
        if key == "reach" and reach_locked:
            continue
        links.append({"key": key, "label": label, "endpoint": endpoint})
    return links


def locked_reason(key: str, milestones: set[str]) -> str | None:
    """Why a locked surface is locked, in words a person should read. None
    when it is open.

    These are the sentences that carry the product's position on timing,
    so they say what has to happen rather than just refusing.
    """
    if is_open(key, milestones):
        return None
    entry = BY_KEY.get(key)
    if entry is None:
        return None
    _, label, _, unlocks, retires, _ = entry

    if retires is not None and retires in milestones:
        return f"{label} is behind you — you have already passed {MILESTONE_LABELS[retires].lower()}."

    return {
        VERIFIED: "Verification has to clear first. Until it does you can look around, but you are not in anyone's matches.",
        MATCHED: "This opens once you and someone have locked each other in.",
        DATE_SET: "This opens once a date is actually set — it is a decision about a real evening, not a preference about a stranger.",
        FIRST_DATE: "This opens after your first date. Asking sooner gets answers people did not mean.",
        RELATIONSHIP: "This opens once you have both agreed to be exclusive.",
    }.get(unlocks, f"{label} is not open yet.")
