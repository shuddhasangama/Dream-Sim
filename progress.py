"""Which stage of the journey someone is in (Segment J, step 41).

2026-09-04, user's rule: "I don't understand this 'Step 11 of 12 · In a
relationship'. Just the status is good."

He is right, and the counter was the wrong idea twice over. A number out
of twelve implies the journey is a queue to get through, and it invited
the question "what are the other eleven?" — which is exactly the
confusion it was meant to remove.

What a person actually wants to know is where they ARE. That is the
D·R·E·M stage indicator the roadmap already asked for (Phase 2), so this
module serves that instead: four stages, the current one marked, no
arithmetic.

The step machinery underneath is kept, unexposed, because the walkthrough
reset and the demo scaffolding still need to know what has happened. It
just is not shown to a person any more.

Pure functions. Nothing here touches the database.
"""

from __future__ import annotations

from typing import Any

import disclosure as d

# key, label, and what proves it. `needs` is a milestone; `fact` is a key
# in the facts dict that must be truthy. Either, both, or neither.
STEPS: list[tuple[str, str, str | None, str | None]] = [
    ("signed_up",    "Signed up",              d.REGISTERED,   None),
    ("verified",     "Verified",               d.VERIFIED,     None),
    ("matched",      "Locked in",              d.MATCHED,      None),
    ("aligned",      "Aligned on the date",    d.MATCHED,      "aligned"),
    ("date_set",     "Date set",               d.DATE_SET,     None),
    ("agreement",    "Agreement signed",       d.DATE_SET,     "agreement_signed"),
    ("boundary",     "Boundary set",           d.DATE_SET,     "boundary_set"),
    ("first_date",   "First date done",        d.FIRST_DATE,   None),
    ("flags",        "Flags given",            d.FIRST_DATE,   "flags_given"),
    ("decision",     "Decision made",          d.FIRST_DATE,   "decision_made"),
    ("relationship", "In a relationship",      d.RELATIONSHIP, None),
    ("married",      "Happily married",        d.RELATIONSHIP, "married"),
]

TOTAL = len(STEPS)


def _is_done(needs: str | None, fact: str | None, milestones: set[str], facts: dict[str, Any]) -> bool:
    if needs is not None and needs not in milestones:
        return False
    if fact is not None and not facts.get(fact):
        return False
    return True


def steps(milestones: set[str], facts: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every step, marked done / current / todo.

    Exactly one step is `current`: the first one not yet done. Once they
    are all done nothing is current, because there is nothing to be in the
    middle of — which is the correct state for the end of the journey and
    the one a naive "last index" would get wrong.
    """
    facts = facts or {}
    out, found_current = [], False
    for i, (key, label, needs, fact) in enumerate(STEPS):
        done = _is_done(needs, fact, milestones, facts)
        state = "done" if done else ("current" if not found_current else "todo")
        if state == "current":
            found_current = True
        out.append({"key": key, "label": label, "index": i + 1, "state": state, "done": done})
    return out


# ── the four stages, which is all a person is shown ───────────────────────

STAGES = [
    ("dating", "Dating"),
    ("relationship", "Relationship"),
    ("engaged", "Engaged"),
    ("married", "Married"),
]
_STAGE_KEYS = [key for key, _ in STAGES]
_STAGE_LABELS = dict(STAGES)


def stage_view(journey_state: str, milestones: set[str]) -> dict[str, Any]:
    """The D·R·E·M indicator: four stages, the current one marked.

    `journey_state` is the authority — it is the column the whole app
    branches on. Milestones only decide whether to show the indicator at
    all, because someone still being verified is not yet on the track and
    a "Dating" pip would be telling them something untrue.

    Any state that is not one of the four (onboarding, exiting, cooloff)
    falls back to Dating rather than raising: an indicator is decoration,
    and decoration must never be able to take a page down.
    """
    current = journey_state if journey_state in _STAGE_KEYS else "dating"
    index = _STAGE_KEYS.index(current)
    return {
        "show": d.VERIFIED in milestones,
        "current": current,
        "label": _STAGE_LABELS[current],
        "stages": [
            {"key": key, "label": label,
             "state": "done" if i < index else ("current" if i == index else "todo")}
            for i, (key, label) in enumerate(STAGES)
        ],
    }


def position(milestones: set[str], facts: dict[str, Any] | None = None) -> dict[str, Any]:
    """The headline: "step 6 of 12", plus the label of where they are.

    `done` counts steps ACTUALLY completed rather than the current index,
    so a step skipped out of order — which the milestone fold makes
    possible — is not counted as finished just because a later one is.
    """
    marked = steps(milestones, facts)
    done = sum(1 for step in marked if step["done"])
    current = next((step for step in marked if step["state"] == "current"), None)
    return {
        "done": done,
        "total": TOTAL,
        "current": current,
        "label": current["label"] if current else "Journey complete",
        "step_number": current["index"] if current else TOTAL,
        "percent": round(100 * done / TOTAL),
        "complete": current is None,
    }
