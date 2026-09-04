"""Tests for gate_conversation.py — the stage gate as a Guru-brokered
exchange (2026-09-04).

Two rules carry the whole feature, and both are here as refusals rather
than behaviours:

  1. NOTHING EITHER PERSON WRITES REACHES THE OTHER. Not their reasons,
     not their notes, not who asked what. Guru composes every word that
     crosses. "There is no direct conversation, which is totally avoided
     as we need to be sure about the messaging and the tone."

  2. NOBODY CAN COMMIT IN THE SAME SITTING. The pause is the feature:
     "People not committing to things or committing too early without
     thinking is what made me take up this problem to solve."
"""

from __future__ import annotations

import unittest

import gate_conversation as gc
from stage_gate import STAGE_GATE_QUESTIONS

SCALE = "ready_meet_friends"
TEXT = "who_knows"
ALL_KEYS = [q["key"] for q in STAGE_GATE_QUESTIONS]


class AskingTests(unittest.TestCase):
    def test_everything_is_askable_before_anything_is_asked(self):
        self.assertEqual(len(gc.askable([])), len(STAGE_GATE_QUESTIONS))

    def test_a_question_already_asked_is_not_offered_again(self):
        """Re-asking reads as not having listened."""
        remaining = {q["key"] for q in gc.askable([SCALE])}
        self.assertNotIn(SCALE, remaining)

    def test_you_must_ask_something(self):
        self.assertFalse(gc.validate_asks([], [])["ok"])

    def test_more_than_three_at_once_is_a_form_again(self):
        result = gc.validate_asks(ALL_KEYS[:4], [])
        self.assertFalse(result["ok"])
        self.assertIn("form", result["error"])

    def test_duplicates_and_unknowns_are_dropped_not_counted(self):
        result = gc.validate_asks([SCALE, SCALE, "not_a_question"], [])
        self.assertTrue(result["ok"])
        self.assertEqual(result["keys"], [SCALE])

    def test_asking_something_already_asked_does_not_count(self):
        self.assertFalse(gc.validate_asks([SCALE], [SCALE])["ok"])


class BrokeringTests(unittest.TestCase):
    """Rule 1: Guru composes every word that crosses."""

    def test_a_relayed_question_never_names_who_asked(self):
        """"Rahul wants to know whether you are seeing anyone else" is an
        accusation. Unattributed, it is an invitation."""
        relayed = gc.relay("exclusivity_check")
        blob = " ".join(str(v) for v in relayed.values()).lower()
        for attribution in ("they ask", "asked by", "wants to know", "rahul"):
            self.assertNotIn(attribution, blob)

    def test_the_relay_says_both_of_you_are_answering(self):
        self.assertIn("both", gc.relay(SCALE)["framing"].lower())

    def test_free_text_is_never_compared_or_quoted(self):
        """A text answer produces a note about the fact of answering, and
        nothing about the content — there is nothing else it could safely
        say without a model to reframe it."""
        result = gc.compare(TEXT, "I told my sister and two friends", "Nobody yet")
        self.assertEqual(result["state"], "answered")
        for word in ("sister", "friends", "Nobody"):
            self.assertNotIn(word, result["note"])

    def test_a_scale_comparison_never_says_who_is_where(self):
        for a, b in (("ready_now", "not_yet"), ("not_yet", "ready_now")):
            with self.subTest(a=a, b=b):
                note = gc.compare(SCALE, a, b)["note"].lower()
                for blaming in ("you said", "they said", "they are", "you are not ready"):
                    self.assertNotIn(blaming, note)

    def test_the_same_gap_reads_the_same_from_either_side(self):
        """Symmetry is what makes it a shared position rather than a
        verdict on one person."""
        self.assertEqual(gc.compare(SCALE, "ready_now", "not_yet"),
                         gc.compare(SCALE, "not_yet", "ready_now"))

    def test_a_gap_is_framed_as_worth_talking_about_not_as_a_failure(self):
        note = gc.compare(SCALE, "ready_now", "not_yet")["note"].lower()
        self.assertIn("conversation", note)
        self.assertIn("not a reason to stop", note)


class ComparisonTests(unittest.TestCase):
    def test_identical_answers_are_aligned(self):
        self.assertEqual(gc.compare(SCALE, "soon", "soon")["state"], "aligned")

    def test_one_step_apart_is_close(self):
        self.assertEqual(gc.compare(SCALE, "ready_now", "soon")["state"], "close")

    def test_two_or_more_steps_apart_is_apart(self):
        self.assertEqual(gc.compare(SCALE, "ready_now", "not_yet")["state"], "apart")

    def test_a_missing_answer_is_waiting_not_a_gap(self):
        """Silence is not disagreement."""
        self.assertEqual(gc.compare(SCALE, "ready_now", None)["state"], "waiting")
        self.assertEqual(gc.compare(SCALE, None, None)["state"], "waiting")

    def test_the_report_counts_only_real_gaps(self):
        report = gc.report([SCALE], {SCALE: "ready_now"}, {SCALE: "not_yet"})
        self.assertEqual(report["apart_count"], 1)
        self.assertTrue(report["complete"])

    def test_the_report_is_incomplete_while_anyone_is_owed_an_answer(self):
        report = gc.report([SCALE], {SCALE: "ready_now"}, {})
        self.assertFalse(report["complete"])
        self.assertIn("waiting", report["headline"].lower())

    def test_full_agreement_says_so_plainly(self):
        report = gc.report([SCALE], {SCALE: "soon"}, {SCALE: "soon"})
        self.assertEqual(report["apart_count"], 0)
        self.assertIn("same place", report["headline"])


class ReflectionTests(unittest.TestCase):
    """Rule 2: the pause is the feature."""

    def test_the_pause_has_not_started_until_both_have_answered(self):
        state = gc.reflection(None, 100)
        self.assertFalse(state["started"])
        self.assertFalse(state["may_commit"])

    def test_nobody_can_commit_in_the_same_hour_they_answered(self):
        self.assertFalse(gc.reflection(0, 0)["may_commit"])

    def test_nobody_can_commit_an_hour_short(self):
        self.assertFalse(gc.reflection(0, gc.REFLECTION_HOURS - 1)["may_commit"])

    def test_the_pause_ends_exactly_when_it_says_it_does(self):
        self.assertTrue(gc.reflection(0, gc.REFLECTION_HOURS)["may_commit"])

    def test_it_is_long_enough_to_cross_a_night(self):
        """Deciding tonight what you would decide tomorrow is the thing
        this exists to prevent."""
        self.assertGreaterEqual(gc.REFLECTION_HOURS, 12)

    def test_the_remaining_time_counts_down(self):
        self.assertEqual(gc.reflection(0, 4)["remaining"], gc.REFLECTION_HOURS - 4)

    def test_it_survives_a_clock_that_has_gone_backwards(self):
        """The demo clock is resettable. A negative elapsed must not read
        as a finished pause."""
        state = gc.reflection(100, 50)
        self.assertEqual(state["elapsed"], 0)
        self.assertFalse(state["may_commit"])

    def test_committing_needs_both_the_answers_and_the_pause(self):
        answered = ({SCALE: "soon"}, {SCALE: "soon"})
        self.assertFalse(gc.may_commit([SCALE], *answered, None, 100))
        self.assertFalse(gc.may_commit([SCALE], *answered, 0, 1))
        self.assertFalse(gc.may_commit([SCALE], {SCALE: "soon"}, {}, 0, 99))
        self.assertTrue(gc.may_commit([SCALE], *answered, 0, 99))

    def test_disagreeing_does_not_block_committing(self):
        """A gap is worth a conversation, not a veto. The product's job is
        to make sure they SAW it, not to decide for them."""
        self.assertTrue(gc.may_commit(
            [SCALE], {SCALE: "ready_now"}, {SCALE: "not_yet"}, 0, 99))


if __name__ == "__main__":
    unittest.main()
