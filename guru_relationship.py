"""Guru's four pillars once Relationship stage activates
(docs/relationship-stage-spec.md §D3) — deliberately thin, mirroring
guru_dating.py's "state transitions only, no narrative generation"
convention (see journey.py's _stub_guru_synthesis for this project's
established stubbing pattern for where real LLM narration will
eventually plug in). Pure functions: the caller persists whatever's
returned.

Pillar 1 (Air & Resolve) reuses the existing Difference table — it was
already shaped for this: {couple_id, raised_by, text, tag, status,
consent_to_share, week_raised}.
"""

from __future__ import annotations

from typing import Any

PILLARS = ("air_resolve", "romance", "expense", "mediator")


# ── Pillar 1 · Air & Resolve — two-step, consent-gated ───────────────────


def air_step1_raise_difference(
    couple_id: str, raised_by: str, text: str, week_raised: int, existing_differences: list[dict[str, Any]]
) -> dict[str, Any]:
    """Step 1, private: a partner airs a difference — Guru comforts and
    offers reference material (narration layered on later; this just
    builds the row). Auto-tagged 'repeated' if this couple already has
    an 'open' Difference with the same text, else 'new' (§D3)."""
    is_repeated = any(d["text"] == text and d["status"] == "open" for d in existing_differences)
    return {
        "couple_id": couple_id,
        "raised_by": raised_by,
        "text": text,
        "tag": "repeated" if is_repeated else "new",
        "status": "open",
        "consent_to_share": 0,
        "week_raised": week_raised,
    }


def air_step2_consent_to_share(difference: dict[str, Any], consent_given: bool) -> dict[str, Any]:
    """Step 2, consent-gated: only if the person who raised it agrees
    does Guru inform the partner and mediate. Doesn't itself invoke the
    Mediator — call mediator_invoke() separately once consent is True,
    keeping each function single-purpose."""
    return {**difference, "consent_to_share": int(bool(consent_given))}


def resolve_difference(difference: dict[str, Any]) -> dict[str, Any]:
    """'open' -> 'sorted' once addressed — feeds the Weekly Report's own
    sorted[]/open[] buckets (§D4), which read directly off this status."""
    return {**difference, "status": "sorted"}


# ── Pillar 2 · Keep Romance Alive ─────────────────────────────────────────


def romance_suggestion(chemistry_entries_for_couple: list[dict[str, Any]], existing_playbook_ideas: list[str]) -> dict[str, Any]:
    """Draws on the couple's Chemistry entries (vibes_to_keep_alive) plus
    whatever the playbook already has. `new_idea` stays None — this
    module has no LLM; the agent layer fills it in later, same stubbing
    pattern as journey.py's exit synthesis."""
    vibes = [e["value"] for e in chemistry_entries_for_couple if e["key"] == "vibes_to_keep_alive"]
    return {"vibes_on_file": vibes, "existing_ideas": list(existing_playbook_ideas), "new_idea": None}


def add_romance_idea(existing_playbook_ideas: list[str], idea_text: str) -> list[str]:
    """"New ideas writeable back to the playbook." Returns the updated
    list; the caller persists it (Playbook.tier_custom_json)."""
    return [*existing_playbook_ideas, idea_text]


# ── Pillar 3 · Expense Handling ───────────────────────────────────────────


def expense_check(expense_strategy: str | None, self_reported_compliant: bool) -> dict[str, Any]:
    """"Simple yes/no compliance check against the playbook's expense
    strategy. No bill-scanning at launch" — self_reported_compliant is
    exactly that, never inferred from anything else."""
    return {"expense_strategy": expense_strategy, "compliant": bool(self_reported_compliant)}


# ── Pillar 4 · Mediator ───────────────────────────────────────────────────


def mediator_invoke(couple_id: str, topic_or_difference_text: str, week: int) -> dict[str, Any]:
    """Standalone invoke, and also what Pillar 1 step 2 calls once
    consent is given (§D3: "the shared engine Pillar 1 step 2 calls").
    A structural record of the invocation — no narration."""
    return {"couple_id": couple_id, "topic": topic_or_difference_text, "week": week}
