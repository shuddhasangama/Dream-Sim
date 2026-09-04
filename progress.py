"""Where someone is in the journey, as a step number (Segment J, step 41).

A walkthrough needs a spine. Without one the viewer sees a sequence of
screens with no sense of how far in they are, and the demo's most common
question — "how much of this is left?" — has no answer on screen.

The steps here are the JOURNEY's, not the app's routes. They are the
things a person does, in the order the product makes them do them, and
each one is `done` when the fact that proves it is true. That matters:
a tracker driven by which page you last visited flatters the demo, and a
tracker driven by evidence tells the truth about where the pair actually
stands.

Facts come from the same dict guru.next_action() reads, so the tracker and
Guru's "what now?" can never disagree about what has happened.

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
