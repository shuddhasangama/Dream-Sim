"""The Dating exit / Relationship entry gate (docs/relationship-stage-spec.md
Part B) — the two entry triggers (B1), the private stage-gate
questionnaire (B3), and Guru's gap analysis (B4). Pure functions: the
caller persists whatever's returned and drives the nine-step sequence in
B2 by calling these plus vision.prerequisites_met() (step 5) and
journey.enter_relationship() (steps 6-9) in order.

`pair_id` here is a LockIn.id, same invariant as escalations.py — the
gate opens from Dating ("after a pattern of sustained lock-ins"), before
any Couple record exists.

Guardrails enforced by this module's design (Part F):
    - Gate answers stay private — analyze_gate() only ever emits
      category/question-key-level notes, never a raw answer_text value
      (see test_stage_gate.py's own assertion of this).
    - Guru does not block the gate except an unresolved exclusivity
      mismatch — has_unresolved_exclusivity_mismatch() is the one thing
      a caller should treat as a hard stop before step 4/6; every other
      divergence is surface-only.
"""

from __future__ import annotations

from typing import Any

TRIGGERS = ("guru_checkin", "exclusivity_raised")
GATE_STATUSES = ("open", "must_resolve", "progressed", "declined")

# §B3 — asked privately to each partner; answers not shown directly to
# the other. kind='scale' questions carry a fixed ordered vocabulary
# (order matters — see _material_divergence()); kind='text' questions are
# free text with no programmatic comparison, by design (B4: "never quote
# one partner's raw answer to the other").
STAGE_GATE_QUESTIONS: list[dict[str, Any]] = [
    {"key": "ready_meet_friends", "category": "readiness_visibility", "kind": "scale",
     "text": "Are we ready to meet each other's friends?", "options": ("ready_now", "soon", "not_yet", "unsure")},
    {"key": "ready_meet_family", "category": "readiness_visibility", "kind": "scale",
     "text": "Are we ready to meet each other's family?", "options": ("ready_now", "soon", "not_yet", "unsure")},
    {"key": "social_media_status", "category": "readiness_visibility", "kind": "scale",
     "text": "Would you update your relationship status on social media?",
     "options": ("yes", "not_yet", "rather_not", "dont_use")},
    {"key": "who_knows", "category": "readiness_visibility", "kind": "text",
     "text": "Who in your life already knows about this person?"},
    {"key": "relationship_meaning", "category": "intent_pace", "kind": "text",
     "text": "What does moving into the Relationship stage mean to you, in your own words?"},
    {"key": "timeline_expectation", "category": "intent_pace", "kind": "text",
     "text": "What's your honest expectation on timeline from here?"},
    # Modeled as a scale (not pure free text) so an exclusivity mismatch
    # is something must-resolve logic can actually detect — B4 requires
    # a "must-resolve" flag on exclusivity divergence, which isn't
    # possible to compute from unconstrained free text.
    {"key": "exclusivity_check", "category": "intent_pace", "kind": "scale",
     "text": "Are you dating anyone else, or open to?",
     "options": ("exclusive", "seeing_others", "open_to_others", "unsure")},
    {"key": "open_question", "category": "open_question", "kind": "text",
     "text": "What's on your mind that you still want to know from them before you move forward?"},
    {"key": "step_back_reason", "category": "harder_ground", "kind": "text",
     "text": "What would make you step back from this?"},
    {"key": "undisclosed_info", "category": "harder_ground", "kind": "text",
     "text": "Is there anything you haven't told them that they'd want to know?"},
    {"key": "most_unsure", "category": "harder_ground", "kind": "text",
     "text": "What are you most unsure about?"},
    {"key": "disagreement_handling", "category": "harder_ground", "kind": "text",
     "text": "How do you each handle disagreement — and have you seen theirs yet?"},
    {"key": "family_involvement", "category": "practical", "kind": "text",
     "text": "Do you expect family involvement, and when?"},
    {"key": "money_talk", "category": "practical", "kind": "text",
     "text": "Have you talked about money at all?"},
    {"key": "surprising_circumstances", "category": "practical", "kind": "text",
     "text": "Is there anything about your life circumstances that would surprise them?"},
]

_QUESTIONS_BY_KEY = {q["key"]: q for q in STAGE_GATE_QUESTIONS}
_ALL_KEYS = frozenset(_QUESTIONS_BY_KEY)

# A scale-question divergence is "material" (B4: "readiness levels differ
# materially, e.g. one 'ready now', other 'not yet'") when the two
# answers are at least this many steps apart in the question's own
# `options` order.
_MATERIAL_GAP = 2


def open_gate(pair_id: str, trigger: str, opened_at: str) -> dict[str, Any]:
    """B1: either trigger routes into the same gate sequence."""
    if trigger not in TRIGGERS:
        raise ValueError(f"trigger must be one of {TRIGGERS}, got {trigger!r}")
    return {"pair_id": pair_id, "trigger": trigger, "status": "open", "opened_at": opened_at, "resolved_at": None}


def submit_gate_response(
    pair_id: str, user_id: str, question_key: str, *, answer_text: str | None = None, readiness_scale: str | None = None
) -> dict[str, Any]:
    """The GateResponse row to persist for one answer. Declining is free
    — pass answer_text=None (or blank) / readiness_scale=None to record
    "chose not to answer" for that question without penalty; validation
    below only rejects an unknown question_key or a readiness_scale
    value that isn't actually one of that question's own options."""
    question = _QUESTIONS_BY_KEY.get(question_key)
    if question is None:
        raise ValueError(f"unknown stage-gate question_key {question_key!r}")
    if readiness_scale is not None and readiness_scale not in question["options"]:
        raise ValueError(f"{question_key!r} readiness_scale must be one of {question['options']}, got {readiness_scale!r}")
    return {
        "pair_id": pair_id,
        "user_id": user_id,
        "question_key": question_key,
        "answer_text": answer_text,
        "readiness_scale": readiness_scale,
    }


def all_questions_answered(responses_for_user: list[dict[str, Any]]) -> bool:
    """True once `responses_for_user` has one GateResponse row per
    question in STAGE_GATE_QUESTIONS (a declined answer still counts —
    "answered" here means "reached", not "gave real content")."""
    answered_keys = {r["question_key"] for r in responses_for_user}
    return _ALL_KEYS.issubset(answered_keys)


def _material_divergence(question: dict[str, Any], scale_a: str | None, scale_b: str | None) -> bool:
    if scale_a is None or scale_b is None or scale_a == scale_b:
        return False
    options = question["options"]
    return abs(options.index(scale_a) - options.index(scale_b)) >= _MATERIAL_GAP


def analyze_gate(pair_id: str, responses_a: list[dict[str, Any]], responses_b: list[dict[str, Any]]) -> dict[str, Any]:
    """B4's gap analysis: compares the two private answer sets and
    surfaces divergence, never content. Only ever emits question_key/
    category-level notes — see test_stage_gate.py's
    NeverQuotesRawAnswersTests for the guardrail this enforces."""
    by_key_a = {r["question_key"]: r for r in responses_a}
    by_key_b = {r["question_key"]: r for r in responses_b}

    divergences: list[dict[str, Any]] = []
    must_resolve: list[dict[str, Any]] = []
    for question in STAGE_GATE_QUESTIONS:
        if question["kind"] != "scale":
            continue
        key = question["key"]
        response_a, response_b = by_key_a.get(key), by_key_b.get(key)
        scale_a = response_a["readiness_scale"] if response_a else None
        scale_b = response_b["readiness_scale"] if response_b else None
        if scale_a is None or scale_b is None or scale_a == scale_b:
            continue
        if key == "exclusivity_check":
            must_resolve.append({
                "question_key": key,
                "note": "Exclusivity expectations differ — this needs to be resolved before moving forward.",
            })
        elif _material_divergence(question, scale_a, scale_b):
            divergences.append({
                "question_key": key,
                "category": question["category"],
                "note": "You two described meaningfully different readiness here — worth a conversation, not a problem.",
            })

    guru_prompts: list[dict[str, Any]] = []
    for user_id, by_key in (("a", by_key_a), ("b", by_key_b)):
        open_response = by_key.get("open_question")
        if open_response and (open_response.get("answer_text") or "").strip():
            guru_prompts.append({
                "for": user_id,
                "note": "There's something on your mind you haven't asked yet — this is a good moment to ask it.",
            })

    return {"pair_id": pair_id, "divergences": divergences, "must_resolve": must_resolve, "guru_prompts": guru_prompts}


def has_unresolved_exclusivity_mismatch(analysis: dict[str, Any]) -> bool:
    """The one thing Guru is allowed to block the gate on (B4's hard
    rule). Everything else in `analysis["must_resolve"]` — there is
    currently nothing else that ever lands there — is surface-only."""
    return any(item["question_key"] == "exclusivity_check" for item in analysis["must_resolve"])


def confirm_progression(confirm_a: bool, confirm_b: bool) -> dict[str, Any]:
    """B2 step 4: "Both confirm intent to progress (mutual, either may
    decline)." Purely the mutual-opt-in check — prerequisites (step 5)
    and exclusivity/consent (steps 6-7) are separate, later checks."""
    if confirm_a and confirm_b:
        return {"progressed": True, "reason": None}
    return {"progressed": False, "reason": "mutual confirmation required — at least one partner has not confirmed"}


def resolve_gate(gate: dict[str, Any], status: str, resolved_at: str) -> dict[str, Any]:
    """Close out a StageGate row once its sequence reaches a terminal
    state. `status` is 'progressed' (reached Relationship), 'declined'
    (either partner declined at step 4, or the pair chose to stay in
    Dating), or 'must_resolve' (blocked on an unresolved exclusivity
    mismatch — reopenable once resolved, not terminal in practice, but a
    real status the caller can persist and show)."""
    if status not in GATE_STATUSES:
        raise ValueError(f"status must be one of {GATE_STATUSES}, got {status!r}")
    return {**gate, "status": status, "resolved_at": resolved_at}
