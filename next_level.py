"""The "Next Level" conversation (docs/intimacy-expectations-spec.md
Part B) — Guru-facilitated, reciprocal-unlock, user-initiated (or Guru
offers it once on a material pace mismatch — see chemistry.on_chemistry_
update() — and never re-offers if declined). Pure functions: the caller
persists NextLevelThread rows, one per question_key.

Guardrails enforced by this module's design (Part F):
    - Reciprocal unlock applies to every question — visible_answers()
      only reveals either side once BOTH have answered or declined that
      specific question (see reveal logic inside submit_answer()).
    - Reluctance is surfaced privately to the reluctant person only,
      never to their partner — visible_answers() strips
      reluctance_flagged_to for any viewer who isn't that person (see
      test_next_level.py's own assertion of this).
    - Declining is free and shown neutrally as "chose not to answer" —
      never distinguished from "hasn't answered yet" in a way that
      pressures a response.
"""

from __future__ import annotations

from typing import Any

TRIGGERS = ("user", "guru_offer")

# §B2 — the reciprocal-unlock question set, grouped exactly as the spec
# presents them. `category` mirrors stage_gate.py's STAGE_GATE_QUESTIONS
# shape for consistency across the two questionnaire modules.
NEXT_LEVEL_QUESTIONS: list[dict[str, str]] = [
    {"key": "meaning_of_next_level", "category": "intent_and_meaning", "text": "What would \"taking this to the next level\" mean to you?"},
    {"key": "hopes_and_uncertainty", "category": "intent_and_meaning", "text": "What are you hoping for, and what are you unsure about?"},
    {"key": "pace_from_here", "category": "pace", "text": "What pace feels right to you from here?"},
    {"key": "before_physical_intimacy", "category": "pace",
     "text": "Is there anything you want to happen before physical intimacy — meeting friends, family, more time, an exclusivity conversation?"},
    {"key": "not_comfortable_or_not_ready", "category": "boundaries", "text": "What are you not comfortable with, or not ready for?"},
    {"key": "how_to_check_in", "category": "boundaries", "text": "How would you want the other person to check in with you?"},
    {"key": "saying_not_now", "category": "boundaries", "text": "How do you each want to be able to say \"not now\" without it being a big deal?"},
    {"key": "health_discussion_comfort", "category": "health_and_practicalities", "text": "Are you both comfortable discussing sexual health and contraception?"},
    {"key": "protection_agreement", "category": "health_and_practicalities", "text": "Is there anything about protection or health you'd want agreed beforehand?"},
    {"key": "reluctance_check", "category": "the_honest_one",
     "text": "Is there anything you're saying yes to because you feel you should, rather than because you want to?"},
]

_QUESTION_KEYS = [q["key"] for q in NEXT_LEVEL_QUESTIONS]

RELUCTANCE_QUESTION_KEY = "reluctance_check"

# B3: "If one partner's answers indicate reluctance or pressure, Guru
# privately reflects that back to that person only." No LLM in this
# harness — a deterministic keyword heuristic stands in for real
# narration, same stubbing convention as journey.py's
# _stub_guru_synthesis / dateplan.verify_face.
_RELUCTANCE_PHRASES = (
    "feel like i should", "feel i should", "supposed to", "have to", "ought to",
    "obligated", "obligation", "pressure", "pressured", "expected of me",
    "don't really want", "not sure i want", "going along with it", "afraid to say no",
)

RELUCTANCE_REFLECTION = (
    "Some of what you've written sounds like you may feel you should, rather than that "
    "you want to — that's yours to decide, and there's no wrong answer."
)


def _detect_reluctance(answer_text: str | None) -> bool:
    if not answer_text:
        return False
    lowered = answer_text.lower()
    return any(phrase in lowered for phrase in _RELUCTANCE_PHRASES)


def open_conversation(pair_id: str, opened_by: str, opened_at: str) -> list[dict[str, Any]]:
    """B1: either partner opens it, or Guru offers once. Returns one
    NextLevelThread row per NEXT_LEVEL_QUESTIONS key — the caller bulk-
    inserts all of them, so the whole conversation opens as one unit
    even though reveal happens per-question."""
    if opened_by not in TRIGGERS:
        raise ValueError(f"opened_by must be one of {TRIGGERS}, got {opened_by!r}")
    return [
        {
            "pair_id": pair_id,
            "opened_by": opened_by,
            "question_key": question["key"],
            "answer_a": None,
            "answer_b": None,
            "declined_a": False,
            "declined_b": False,
            "answered_at_a": None,
            "answered_at_b": None,
            "revealed_at": None,
            "reluctance_flagged_to": None,
            "opened_at": opened_at,
        }
        for question in NEXT_LEVEL_QUESTIONS
    ]


def guru_already_offered(existing_threads: list[dict[str, Any]]) -> bool:
    """B1: "Guru may offer it once... it never re-offers if declined." A
    caller checks this before calling open_conversation(opened_by=
    'guru_offer') again for the same pair."""
    return any(t["opened_by"] == "guru_offer" for t in existing_threads)


def _side_complete(thread: dict[str, Any], side: str) -> bool:
    return bool(thread[f"declined_{side}"]) or thread[f"answer_{side}"] is not None


def submit_answer(
    thread: dict[str, Any], side: str, *, answered_at: str, answer_text: str | None = None, declined: bool = False
) -> dict[str, Any]:
    """Records one partner's answer (or free decline — B3: "Declining any
    question is free and shown neutrally as 'chose not to answer'") for
    this thread's question. Reveals both sides the moment the SECOND one
    completes (reciprocal unlock) by setting revealed_at; does nothing
    special if this is the first side to answer. Also runs the private
    reluctance check on the honest-one question, flagging only the
    answering side — never the partner."""
    if side not in ("a", "b"):
        raise ValueError(f"side must be 'a' or 'b', got {side!r}")

    updated = dict(thread)
    if declined:
        updated[f"declined_{side}"] = True
        updated[f"answer_{side}"] = None
    else:
        updated[f"answer_{side}"] = answer_text
        updated[f"declined_{side}"] = False
    updated[f"answered_at_{side}"] = answered_at

    if not declined and thread["question_key"] == RELUCTANCE_QUESTION_KEY and _detect_reluctance(answer_text):
        updated["reluctance_flagged_to"] = side

    other_side = "b" if side == "a" else "a"
    if updated["revealed_at"] is None and _side_complete(updated, side) and _side_complete(updated, other_side):
        updated["revealed_at"] = answered_at

    return updated


def visible_answers(thread: dict[str, Any], viewer_side: str) -> dict[str, Any]:
    """What `viewer_side` ('a' or 'b') should be shown for this thread.
    Before reveal: only the viewer's own side, plus whether the partner
    has answered yet (not what they said). After reveal: both sides, with
    a decline on either shown as the same neutral "chose not to answer"
    string a real answer would otherwise occupy. `reluctance_flagged_to`
    is INCLUDED only when it's the viewer's own flag — stripped to None
    for anyone else, always, revealed or not (Part F: "never to their
    partner")."""
    if viewer_side not in ("a", "b"):
        raise ValueError(f"viewer_side must be 'a' or 'b', got {viewer_side!r}")

    own_answer = "chose not to answer" if thread[f"declined_{viewer_side}"] else thread[f"answer_{viewer_side}"]
    result: dict[str, Any] = {
        "question_key": thread["question_key"],
        "own_answer": own_answer,
        "revealed": thread["revealed_at"] is not None,
        "partner_answer": None,
    }
    if thread["revealed_at"] is not None:
        other_side = "b" if viewer_side == "a" else "a"
        result["partner_answer"] = "chose not to answer" if thread[f"declined_{other_side}"] else thread[f"answer_{other_side}"]

    result["reluctance_reflection"] = (
        RELUCTANCE_REFLECTION if thread.get("reluctance_flagged_to") == viewer_side else None
    )
    return result
