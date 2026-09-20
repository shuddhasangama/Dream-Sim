"""Guru's narrowly-scoped Dating role (docs/dating-stage-spec.md §7-8).

Guru's four pillars are Relationship-stage only. In Dating, Guru appears in
exactly three places: before the date (courtesies), after the date
(feedback capture), and on a pass (free-text reason capture, never
inferred). Guru does NOT mediate, does not run pillars, does not generate
weekly reports in Dating — all of that begins at Relationship entry
(journey.py's PILLARS/STAGE_TOPICS/GuruTopic machinery). This module has
no import of and no dependency on any of that, by design — see
test_guru_dating.py's own assertion of that boundary.

Deliberately thin: static content plus plain, non-leading pass-throughs.
Nothing here infers a reason, asks about appearance, or scores anything.
"""

from __future__ import annotations

from typing import Any

PRE_DATE_COURTESIES = [
    "Arrive on time; message through the app if delayed",
    "Be present — phone away, genuine attention",
    "Basic table courtesy, and politeness to venue staff",
    "Honour the agreed bill split gracefully — no scene over payment",
    "End the date respectfully regardless of romantic outcome",
]

PRE_DATE_SAFETY = [
    "Meet at the confirmed public venue",
    "Share date details with a trusted contact outside the platform",
    "In-app reporting is available at any time",
]

PRE_DATE_BOUNDARIES = [
    "The other person's stated greeting preference is shown before you meet — respect it",
    "No recording or photographing without consent",
    "Contact exchange happens in-app, by mutual choice",
]


# round3-fixes-spec.md §6.2: Guru, in its own voice, explaining the two
# things underneath every screen in Dating rather than leaving them
# implicit — the consent model, and the rules of engagement someone would
# otherwise only ever discover by running into them. Informational only:
# no step here is a suggestion to do anything, which is the same §12
# guardrail pre_date_briefing() already keeps ("reflects and structures,
# never nudges escalation").
CONSENT_EXPLAINER = (
    "Every yes here is a real yes. Nothing moves forward unless both of you choose it, "
    "and the other person only ever sees that something didn't happen, never that you said no."
)

# round4-fixes-spec.md §10: the consent-driven approach, as the three things
# it actually promises — a preview of how Dating works. Descriptive only:
# none of these suggests progressing, inviting anyone anywhere, or sharing
# contact details (guru_dating never nudges escalation).
CONSENT_POINTS = [
    "Declining anything is always free. It carries no penalty and is never shown to the other person as a rejection.",
    "Contact details are exchanged in-app, when both of you choose — they are never asked for in person.",
    "The greeting or physical-boundary preference each person states is shown before you meet, and it is expected to be respected.",
]

DATING_PLAYBOOK = [
    "Matches are drawn for you through the week — there is no searching or swiping.",
    "Interest is private until it's mutual. A pass is never shown to the other person.",
    "Once you lock in with someone, you stop appearing to anyone else, and REACH closes for you.",
    "A date is confirmed once both of you sign the same agreement — one signature holds nothing.",
]


def dating_context() -> dict[str, Any]:
    """§6.2's consent explainer and rules-of-engagement summary. Static
    and stage-scoped — this module stays Dating-only by design (see the
    module docstring), so this is not "the playbook", only Dating's."""
    return {"consent": CONSENT_EXPLAINER, "consent_points": list(CONSENT_POINTS),
            "playbook": list(DATING_PLAYBOOK)}


def pre_date_briefing(partner_greeting: str | None) -> dict[str, Any]:
    """Everything Guru surfaces before a date (§8), framed as shared
    etiquette — never as rules or threats. `partner_greeting` is the OTHER
    person's stated greeting/physical-boundary preference (from their
    DatePlan selection), shown so it's respected before they meet (§7:
    "respect the stated greeting preference")."""
    return {
        "courtesies": list(PRE_DATE_COURTESIES),
        "safety": list(PRE_DATE_SAFETY),
        "boundaries": list(PRE_DATE_BOUNDARIES),
        "partner_greeting": partner_greeting,
        "note": "Contact details are exchanged in-app when both are ready — never asked for in person.",
    }


# Post-date flag feedback (§7's "facilitates feedback capture", extended
# 2026-08-28 at the user's explicit request: mandatory green flags,
# optional red flags, collected BEFORE the accept/reject decision and
# required regardless of which way that decision goes — "a journey of
# improvement", not just an explanation for a rejection). Copy stays
# gender-neutral and behaviour-only — never appearance (§12 guardrail).
GREEN_FLAGS = [
    "Actually listened",
    "On time",
    "Asked good questions",
    "Kind to staff",
    "Honest about their week",
    "Made me laugh",
    "Phone stayed away",
]

RED_FLAGS = [
    "Talked over me",
    "Showed up late",
    "Phone face-up the whole time",
    "Interrogated my finances",
    "Rude to staff",
    "Rewrote their own stats mid-date",
]

MIN_GREEN_FLAGS = 2
MAX_GREEN_FLAGS = 2
MAX_RED_FLAGS = 2


def capture_flags(green: list[str], red: list[str]) -> dict[str, Any]:
    """Validates and caps one partner's flag picks. Green: exactly
    MIN_GREEN_FLAGS-MAX_GREEN_FLAGS valid entries (both currently 2 — see
    the module comment above for why it's mandatory). Red: up to
    MAX_RED_FLAGS, always optional. Unknown labels and anything past the
    cap are silently dropped rather than raising — app.py is responsible
    for gating the actual submit button on `meets_minimum` in the UI,
    this just guarantees the stored data is never malformed even if that
    gate is somehow bypassed."""
    green_valid = [g for g in green if g in GREEN_FLAGS][:MAX_GREEN_FLAGS]
    red_valid = [r for r in red if r in RED_FLAGS][:MAX_RED_FLAGS]
    return {"green": green_valid, "red": red_valid, "meets_minimum": len(green_valid) >= MIN_GREEN_FLAGS}


def capture_pass_reason(free_text: str | None) -> dict[str, Any]:
    """On a pass, if a reason is volunteered, receive it as free text —
    §7: "never infers a reason, never asks about appearance". No prompt
    here ever asks about looks; `free_text` is optional and passed through
    exactly as given, never rewritten or summarized."""
    volunteered = free_text is not None and free_text.strip() != ""
    return {"volunteered": volunteered, "reason": free_text if volunteered else None}
