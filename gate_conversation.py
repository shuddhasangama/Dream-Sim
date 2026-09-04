"""The stage gate as a Guru-brokered conversation (2026-09-04).

WHY THIS REPLACES A FORM
========================
The gate used to be fifteen questions, both people answering privately in
one sitting, compared for divergence. That is a survey. It lets someone
commit in four minutes flat, which is the exact behaviour this product
exists to prevent:

    "People not committing to things or committing too early without
    thinking is what made me take up this problem to solve."

So the gate is now an exchange that takes time on purpose:

  1. ASK      — you choose what you want to know, from a curated pool.
  2. ANSWER   — you answer the same questions you asked, and theirs.
  3. REFLECT  — a mandatory pause before anyone can commit. Nothing is
                clickable during it. This is the point of the feature.
  4. CONFIRM  — or ask another round, which resets the pause.

GURU BROKERS EVERY WORD
=======================
2026-09-04, user's rule: "There is no direct conversation, which is
totally avoided as we need to be sure about the messaging and the tone
aspects of it so that it is very conducive and collaborative."

So nothing either person writes reaches the other. Not their reasons, not
their notes, not the wording of what they asked. What crosses is:

  * WHICH question was asked — relayed in Guru's words, never "Rahul asks",
    because attributing a question turns it into an accusation; and
  * a comparison of two SCALE answers, phrased as a shared position rather
    than a verdict on either person.

Free text stays private to Guru. It is collected because writing it is
what makes someone think, not because anyone else will read it. When Guru
becomes a real agent it can summarise that text into the relay; until
then, passing it through unedited is the one thing this module must not
do, so it cannot.

Pure functions. The caller persists.
"""

from __future__ import annotations

from typing import Any

from stage_gate import STAGE_GATE_QUESTIONS

_BY_KEY = {q["key"]: q for q in STAGE_GATE_QUESTIONS}

# ── the pause ─────────────────────────────────────────────────────────────
# Overnight, deliberately. Long enough that nobody answers and commits in
# the same sitting; short enough that a couple who are ready are not made
# to wait a week. In simulated hours, so the demo clock can cross it.
REFLECTION_HOURS = 12

# How many questions one person may put in a single round. A cap, because
# twelve questions at once is a form again, and the point is to ask what
# you actually want to know.
MAX_ASKS_PER_ROUND = 3
MIN_ASKS_PER_ROUND = 1


def askable(already_asked: list[str]) -> list[dict[str, Any]]:
    """Questions still available to ask. A question asked in an earlier
    round is not offered again — re-asking reads as not having listened."""
    seen = set(already_asked)
    return [dict(q) for q in STAGE_GATE_QUESTIONS if q["key"] not in seen]


def validate_asks(keys: list[str], already_asked: list[str]) -> dict[str, Any]:
    """Check one person's chosen questions for a round."""
    available = {q["key"] for q in askable(already_asked)}
    chosen = [k for k in dict.fromkeys(keys or []) if k in available]
    if len(chosen) < MIN_ASKS_PER_ROUND:
        return {"ok": False, "error": "Choose at least one thing you want to know.", "keys": []}
    if len(chosen) > MAX_ASKS_PER_ROUND:
        return {
            "ok": False,
            "error": f"At most {MAX_ASKS_PER_ROUND} at a time — more than that is a form, "
                     "not a question you actually want answered.",
            "keys": [],
        }
    return {"ok": True, "error": None, "keys": chosen}


# ── what the other person sees ────────────────────────────────────────────


def relay(question_key: str) -> dict[str, str]:
    """Guru's framing of a question that was put to this pair.

    Unattributed on purpose. "Rahul wants to know whether you are seeing
    anyone else" is an accusation; "one of you wants to be sure you are
    both in the same place on this" is an invitation, and both of them
    answer it.
    """
    question = _BY_KEY[question_key]
    return {
        "key": question_key,
        "prompt": question["text"],
        "framing": "This came up between the two of you. You are both answering it.",
        "kind": question["kind"],
        "options": list(question.get("options", ())),
    }


def _scale_gap(question_key: str, a: str | None, b: str | None) -> int | None:
    """How far apart two scale answers are, in steps of that question's own
    vocabulary. None when either side has not answered."""
    options = _BY_KEY[question_key].get("options")
    if not options or a not in options or b not in options:
        return None
    return abs(options.index(a) - options.index(b))


def compare(question_key: str, a: str | None, b: str | None) -> dict[str, Any]:
    """What Guru says about two answers to one question.

    Never names who said what. A gap is described as a shared position —
    "you are not in the same place on this yet" — because the alternative
    is telling one person the other is the problem, which ends the
    conversation this feature exists to start.
    """
    question = _BY_KEY[question_key]
    if question["kind"] != "scale":
        both_in = bool(a) and bool(b)
        return {
            "key": question_key,
            "prompt": question["text"],
            "state": "answered" if both_in else "waiting",
            "note": ("You have both written something here. It stays between each of you and "
                     "Guru — neither of you sees the other's words."
                     if both_in else "Waiting on both of you."),
        }

    gap = _scale_gap(question_key, a, b)
    if gap is None:
        return {"key": question_key, "prompt": question["text"], "state": "waiting",
                "note": "Waiting on both of you."}
    if gap == 0:
        return {"key": question_key, "prompt": question["text"], "state": "aligned",
                "note": "You are in the same place on this."}
    if gap == 1:
        return {"key": question_key, "prompt": question["text"], "state": "close",
                "note": "You are close on this — near enough that talking about it is easy."}
    return {"key": question_key, "prompt": question["text"], "state": "apart",
            "note": "You are not in the same place on this yet. That is worth a conversation "
                    "before either of you commits, not a reason to stop."}


def report(asked: list[str], answers_a: dict[str, str], answers_b: dict[str, str]) -> dict[str, Any]:
    """Guru's read of the round, from scales only."""
    lines = [compare(key, answers_a.get(key), answers_b.get(key)) for key in asked]
    apart = [line for line in lines if line["state"] == "apart"]
    waiting = [line for line in lines if line["state"] == "waiting"]
    return {
        "lines": lines,
        "complete": not waiting,
        "apart_count": len(apart),
        "headline": (
            "Still waiting on both of you." if waiting else
            "You are in the same place on all of this." if not apart else
            f"{len(apart)} thing{'' if len(apart) == 1 else 's'} you see differently."
        ),
    }


# ── the pause, and what it gates ──────────────────────────────────────────


def hours_elapsed(closed_at_hours: int | None, now_hours: int) -> int | None:
    """Whole simulated hours since the round's answers were all in."""
    return None if closed_at_hours is None else max(0, now_hours - closed_at_hours)


def reflection(closed_at_hours: int | None, now_hours: int) -> dict[str, Any]:
    """Where the mandatory pause stands.

    Not a cosmetic countdown — `may_commit` is false until it is over, and
    the route enforces that. Someone who has just read that they see three
    things differently should not be able to commit in the same minute.
    """
    elapsed = hours_elapsed(closed_at_hours, now_hours)
    if elapsed is None:
        return {"started": False, "elapsed": 0, "remaining": REFLECTION_HOURS,
                "may_commit": False,
                "note": "The pause starts once you have both answered."}
    remaining = max(0, REFLECTION_HOURS - elapsed)
    return {
        "started": True,
        "elapsed": elapsed,
        "remaining": remaining,
        "may_commit": remaining == 0,
        "note": ("You have both had time with this. Commit when you mean it."
                 if remaining == 0 else
                 f"{remaining}h to sit with this. Deciding tonight what you would decide "
                 "tomorrow is the thing this is here to prevent."),
    }


def may_commit(asked: list[str], answers_a: dict[str, str], answers_b: dict[str, str],
               closed_at_hours: int | None, now_hours: int) -> bool:
    """Both answered everything asked, and the pause has run."""
    return (report(asked, answers_a, answers_b)["complete"]
            and reflection(closed_at_hours, now_hours)["may_commit"])
