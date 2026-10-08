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
    # 2026-09-04: Expectations, Sharing and Next level were three tiles
    # asking the same question — "which of these am I meant to open?".
    # They are one screen now, so they are one card.
    ("AD", "After the date",         "Expectations, sharing, and where this goes", "after_date_view", "after_date", d.FIRST_DATE, d.RELATIONSHIP),
    ("GT", "Checkpoint",             "Moving to the next stage, together",       "gate_view",        "gate",        d.FIRST_DATE,   d.RELATIONSHIP),
    ("VB", "Vibes",                  "What keeps this alive",                    "vibes_view",       "vibes",       d.RELATIONSHIP, None),
    ("HM", "Happily married",        "The end of the journey",                   "married_view",     "married",     d.RELATIONSHIP, None),
]


# How many cards sit under the action before the rest go behind one link.
#
# 2026-09-04, user's rule: "All other tabs being visible under guru,
# doesn't make sense as well. Keep this intuitive rather than with
# multiple options, which is very confusing." Seven tiles under the one
# answer is the crowding complaint moved one screen down rather than
# fixed. Two is what fits under an answer without competing with it.
#
# Nothing is taken away — the rest live at /guru/everything, because a
# screen that silently drops a door you used yesterday is its own
# confusion.
MAX_CARDS = 2


def cards(milestones: set[str], *, exclude_endpoint: str | None = None) -> list[dict[str, Any]]:
    """Everything open to this user, in journey order.

    Double-gated on purpose: a card appears only if its own `needs` is met
    AND disclosure says the underlying surface is open. The second check
    is what stops Guru from ever offering a door the router would slam.

    `exclude_endpoint` drops the card the next action already points at.
    The same link twice, once as the answer and once as a tile, is the
    "multiple options" the review was about.

    Newest first. Only MAX_CARDS of these reach the hub, so table order —
    which is journey order — would put the agreement and the boundaries
    for a date that has already happened above the checkpoint someone
    just raised. The most recently opened thing is the one most likely
    to be wanted; the rest are a link away, not gone.
    """
    out = []
    for code, title, subtitle, endpoint, surface, needs, hides_at in CARDS:
        if needs not in milestones:
            continue
        if hides_at is not None and hides_at in milestones:
            continue
        if not d.is_open(surface, milestones):
            continue
        if endpoint == exclude_endpoint:
            continue
        out.append({"code": code, "title": title, "subtitle": subtitle,
                    "endpoint": endpoint, "surface": surface, "needs": needs})
    out.sort(key=lambda c: d._RANK[c["needs"]], reverse=True)
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
        copy = {
            'week': ('Review your matches', 'Choose Like or Pass when a match opens.'),
            'align_view': ('Date preferences', 'Save your budget, diet and cuisines.'),
            'calendar_view': ('Confirm Date', 'Choose your slots, then confirm a shared time.'),
            'plan_view': ('Review your agreement', 'Read the terms and sign for this date.'),
            'boundaries_view': ('Choose your greeting', 'Let your partner know what feels comfortable.'),

        }
        if endpoint in copy and headline not in ('Your date is confirmed', 'Waiting for your partner', 'Find a shared time', 'Choose your date'):
            headline, body = copy[endpoint]
        return {"headline": headline, "body": body, "endpoint": endpoint, "cta": cta}

    if d.VERIFIED not in milestones:
        return action(
            "Get verified",
            "Four checks stand between you and the matching pool. Until they clear you can look "
            "around, but you will not appear in anyone's matches.",
            "verify_view", "Start verification")

    # 2026-09-04, user's rule: "If one of them expressed moving to next
    # stage it should be visible or first thing someone wants to see."
    # It sits above everything below it deliberately — an unsigned
    # agreement or a missing green flag can wait a day; someone asking
    # whether this becomes exclusive cannot be the ninth tile down.
    if d.RELATIONSHIP in milestones and f.get('married'):
        return action('Nothing needs you', 'Revisit your shared routines when you need to.', 'married_view', 'Open')
    if d.RELATIONSHIP in milestones:
        return action('Your relationship', 'Open your shared routines and next steps.',
                      'relationship_view', 'Open your relationship')

    if f.get("gate_open"):
        who = "%s has raised the next stage" % f["partner_name"] if (
            f.get("gate_raised_by_partner") and f.get("partner_name")
        ) else "The next stage is on the table"
        if f.get("gate_nothing_asked_yet"):
            return action(
                who,
                "Choose up to three topics to discuss together.",
                "gate_view", "Open it with Guru")
        if f.get("gate_waiting_on_me"):
            return action(
                who,
                "Answer your open questions, then take time to reflect.",
                "gate_view", "Answer with Guru")
        return action(
            who,
            "Your answers are saved. Review your reflection and next step.",
            "gate_view", "Back to the checkpoint")

    if d.MATCHED not in milestones:
        if f.get('available_match'):
            return {"headline": f"Match {f['available_match']} is available", "body": "Take a look and choose Like or Pass.", "endpoint": "week", "cta": "View match"}
        if f.get('interest_sent'):
            return action("Like saved", "Waiting for mutual interest. You can review your week.")
        return action("Waiting for a match", "Your next match will appear here when available.")

    if (d.DATE_SET not in milestones or f.get("has_current_plan") is False) and not f.get("aligned", True):
        return action(
            "Three things before the slot",
            "Budget, what you eat, and the cuisines you enjoy. They were not asked at sign-up "
            "because they mean nothing until there is a bill and a table.",
            "align_view", "Answer them")

    if (d.DATE_SET not in milestones or f.get("has_current_plan") is False) and f.get("my_slots_saved"):
        if not f.get("partner_slots_saved"):
            return action("Availability saved", "Waiting for your partner to share their slots.")
        if not f.get("overlap"):
            return action("Find a shared time", "Your slots do not overlap yet. Review your availability.", "calendar_view", "Review slots")
        return action("Choose your date", "You both have a shared slot. Confirm a time.", "calendar_view", "Confirm Date")

    if d.DATE_SET not in milestones or f.get("has_current_plan") is False:
        return action(
            "Confirm Date",
            "You have locked in with someone. Give at least two slots so a date can be found "
            "between you.",
            "calendar_view", "Confirm Date")

    if not f.get("date_done") and not f.get("agreement_signed"):
        return action(
            "Sign the agreement",
            "Both of you sign before the date is confirmed. It is a readback of what you already "
            "told us, not a negotiation.",
            "plan_view", "Read and sign")

    if not f.get("date_done") and not f.get("boundary_set"):
        return action(
            "Say how you would like to be greeted",
            "It goes into the agreement, so neither of you has to guess at the door.",
            "boundaries_view", "Set your boundary")

    if not f.get('date_done') and f.get('date_confirmed') is False:
        return action('Waiting for your partner', 'Your steps are saved. Your partner still needs to complete the agreement.', 'plan_view', 'Review playbook')

    if not f.get("debrief_open") and not f.get("date_done", d.FIRST_DATE in milestones):
        return action(
            "Your date is confirmed",
            "Review the plan before you meet. Debrief opens after your date.",
            "plan_view", "View date plan")

    if not f.get("flags_given"):
        return action(
            "Date Debrief",
            "Share two green flags and any concerns.",
            "debrief_view", "Open the debrief")

    if not f.get("decision_made"):
        return action(
            "Decide what happens next",
            "Choose another date, end the match, or discuss a relationship.",
            "debrief_view", "Make your call")

    if f.get('decision_made') and f.get('partner_decision_made') is False:
        return action('Waiting for your partner', 'Your Debrief is saved. Your partner will choose their next step.', 'debrief_view', 'View your Debrief')

    return action(
        "Nothing needs you",
        "You are up to date. Guru will surface the next thing when there is one.",
        None, None)
