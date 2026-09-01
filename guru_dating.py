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
