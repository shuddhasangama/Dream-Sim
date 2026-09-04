"""Guru's hub — one place that answers "what now?" (navigation).

The navigation problem had a second half. Rationalising the tabs down to a
handful left the contextual screens — the debrief, the agreement, sharing
contact details, the checkpoint — with nowhere to live. Putting each back
as its own tab is what produced eleven links in the first place.

So they live here. Guru is the one tab that is always present once you are
verified, and its contents change with where you are. That is both the
answer to "too many tabs" and what makes Guru feel like part of the
journey rather than a separate feature: the cards ARE the navigation.

Two things this returns:

  * `next_action()` — the single most useful thing to do right now. One,
    never a list. If everything is done it says so plainly rather than
    inventing busywork.
  * `cards()` — everything currently open, in journey order.

Both are driven by disclosure.py's milestones, so a screen can never
appear in Guru before its own route would allow it. Nothing here touches
the database.
"""

from __future__ import annotations

from typing import Any

import disclosure as d

# ── the cards ─────────────────────────────────────────────────────────────
# `code` is the two-letter mark the mock-up uses. `needs` is the milestone
# that opens the card; `hides_at` closes it again. `surface` names the
# disclosure key so the two can never disagree — a card whose surface is
# shut is never shown, whatever this table says.

# Nothing that already has its own tab appears here. REACH and Week do, so
# they are deliberately absent — a card for a tab is the same link twice,
# and this list has to stay short for the same reason the nav did.

CARDS = [
    # code  title                    subtitle                                    endpoint            surface        needs           hides_at
    # The calendar closes once the date it was collecting slots for exists.
    ("AL", "Before the date",        "Budget, what you eat, what you enjoy",     "align_view",       "align",       d.MATCHED,      d.DATE_SET),
    ("CL", "Weekend calendar",       "Offer the slots that suit you",            "calendar_view",    "calendar",    d.MATCHED,      d.DATE_SET),
    ("AG", "Agreement of understanding", "The terms for this date",              "plan_view",        "plan",        d.DATE_SET,     d.RELATIONSHIP),
    ("BD", "Boundaries",             "How you would like to be greeted",         "boundaries_view",  "boundaries",  d.DATE_SET,     d.RELATIONSHIP),
    ("DB", "Post-date debrief",      "Two green flags, and what happens next",   "debrief_view",     "debrief",     d.DATE_SET,     d.RELATIONSHIP),
    ("EX", "Expectations",           "Pace, and what you are open to discussing", "expectations_view", "expectations", d.FIRST_DATE, None),
    ("SH", "Sharing",                "Contact details, and inviting someone home", "escalations_view", "escalations", d.FIRST_DATE, d.RELATIONSHIP),
    ("NL", "Next level",             "When the two of you describe a different pace", "next_level_view", "next_level", d.FIRST_DATE, d.RELATIONSHIP),
    ("GT", "Checkpoint",             "Moving to the next stage, together",       "gate_view",        "gate",        d.FIRST_DATE,   d.RELATIONSHIP),
    ("VB", "Vibes",                  "What keeps this alive",                    "vibes_view",       "vibes",       d.RELATIONSHIP, None),
    ("HM", "Happily married",        "The end of the journey",                   "married_view",     "married",     d.RELATIONSHIP, None),
]


# The cap this list is tuned against — the same discipline the nav is held
# to. Nine cards after a first date is the crowding complaint moved one
# screen down rather than fixed.
MAX_CARDS = 7


def cards(milestones: set[str]) -> list[dict[str, Any]]:
    """Everything open to this user, in journey order.

    Double-gated on purpose: a card appears only if its own `needs` is met
    AND disclosure says the underlying surface is open. The second check
    is what stops Guru from ever offering a door the router would slam.
    """
    out = []
    for code, title, subtitle, endpoint, surface, needs, hides_at in CARDS:
        if needs not in milestones:
            continue
        if hides_at is not None and hides_at in milestones:
            continue
        if not d.is_open(surface, milestones):
            continue
        out.append({"code": code, "title": title, "subtitle": subtitle,
                    "endpoint": endpoint, "surface": surface})
    return out


# ── the single next action ────────────────────────────────────────────────
# Ordered most-urgent first. The first one whose condition holds wins, so
# adding a rule means putting it in the right place rather than reasoning
# about the whole table.


def next_action(milestones: set[str], *, facts: dict[str, Any] | None = None) -> dict[str, Any]:
    """The one thing worth doing now.

    `facts` carries the handful of things a milestone cannot express — a
    signature still outstanding, flags not yet given. Everything it does
    not carry is treated as not-yet-done, so a missing fact under-promises
    rather than telling someone a step is finished when it is not.
    """
    f = facts or {}

    def action(headline, body, endpoint=None, cta=None):
        return {"headline": headline, "body": body, "endpoint": endpoint, "cta": cta}

    if d.VERIFIED not in milestones:
        return action(
            "Get verified",
            "Four checks stand between you and the matching pool. Until they clear you can look "
            "around, but you will not appear in anyone's matches.",
            "verify_view", "Start verification")

    if d.MATCHED not in milestones:
        return action(
            "Your week is running",
            "Matches are released through the week. Nothing needs doing until one lands — "
            "though REACH will tell you how far your filters actually go.",
            "week", "Open your week")

    if d.DATE_SET not in milestones and not f.get("aligned", True):
        return action(
            "Three things before the slot",
            "Budget, what you eat, and the cuisines you enjoy. They were not asked at sign-up "
            "because they mean nothing until there is a bill and a table.",
            "align_view", "Answer them")

    if d.DATE_SET not in milestones:
        return action(
            "Offer your weekend",
            "You have locked in with someone. Give at least two slots so a date can be found "
            "between you.",
            "calendar_view", "Set your availability")

    if not f.get("agreement_signed"):
        return action(
            "Sign the agreement",
            "Both of you sign before the date is confirmed. It is a readback of what you already "
            "told us, not a negotiation.",
            "plan_view", "Read and sign")

    if not f.get("boundary_set"):
        return action(
            "Say how you would like to be greeted",
            "It goes into the agreement, so neither of you has to guess at the door.",
            "boundaries_view", "Set your boundary")

    if d.FIRST_DATE not in milestones:
        return action(
            "Enjoy it",
            "Nothing to do until afterwards. The debrief opens once the date has happened.",
            "week", "Back to your week")

    if not f.get("flags_given"):
        return action(
            "Two green flags",
            "Write it tonight. Tomorrow you will remember the ending, not the evening.",
            "debrief_view", "Open the debrief")

    if not f.get("decision_made"):
        return action(
            "Decide what happens next",
            "See them again, go back to the pool, or agree to be exclusive. Nothing moves until "
            "you choose.",
            "debrief_view", "Make your call")

    if d.RELATIONSHIP in milestones and f.get("married"):
        return action(
            "Nothing needs you",
            "You went the whole way. The four pillars keep running underneath, and that is the "
            "only thing left to do.",
            "married_view", "Happily married")

    if d.RELATIONSHIP in milestones:
        return action(
            "Keep the rhythm",
            "The four pillars run every week. Open whichever one is sitting with you.",
            "relationship_view", "Open the pillars")

    return action(
        "Nothing needs you",
        "You are up to date. Guru will surface the next thing when there is one.",
        None, None)
