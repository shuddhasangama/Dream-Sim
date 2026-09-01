"""Tests for next_level.py."""

from __future__ import annotations

import unittest

from next_level import (
    NEXT_LEVEL_QUESTIONS,
    RELUCTANCE_QUESTION_KEY,
    guru_already_offered,
    open_conversation,
    submit_answer,
    visible_answers,
)


def _thread(question_key: str = "pace_from_here") -> dict:
    threads = open_conversation("lockin-1", "user", "Mon:12")
    return next(t for t in threads if t["question_key"] == question_key)


class OpenConversationTests(unittest.TestCase):
    def test_one_row_per_question(self) -> None:
        threads = open_conversation("lockin-1", "user", "Mon:12")
        self.assertEqual(len(threads), len(NEXT_LEVEL_QUESTIONS))
        self.assertEqual({t["question_key"] for t in threads}, {q["key"] for q in NEXT_LEVEL_QUESTIONS})

    def test_rejects_unknown_opened_by(self) -> None:
        with self.assertRaises(ValueError):
            open_conversation("lockin-1", "curiosity", "Mon:12")

    def test_starts_unrevealed_and_unanswered(self) -> None:
        for thread in open_conversation("lockin-1", "user", "Mon:12"):
            self.assertIsNone(thread["revealed_at"])
            self.assertIsNone(thread["answer_a"])
            self.assertIsNone(thread["answer_b"])


class GuruAlreadyOfferedTests(unittest.TestCase):
    def test_false_with_no_prior_threads(self) -> None:
        self.assertFalse(guru_already_offered([]))

    def test_false_when_only_user_opened_ones_exist(self) -> None:
        self.assertFalse(guru_already_offered([{"opened_by": "user"}]))

    def test_true_once_guru_has_offered(self) -> None:
        self.assertTrue(guru_already_offered([{"opened_by": "guru_offer"}]))


class SubmitAnswerTests(unittest.TestCase):
    def test_rejects_unknown_side(self) -> None:
        with self.assertRaises(ValueError):
            submit_answer(_thread(), "c", answered_at="Tue:09", answer_text="x")

    def test_records_an_answer(self) -> None:
        updated = submit_answer(_thread(), "a", answered_at="Tue:09", answer_text="Slow, I think.")
        self.assertEqual(updated["answer_a"], "Slow, I think.")
        self.assertFalse(updated["declined_a"])

    def test_declining_is_free(self) -> None:
        updated = submit_answer(_thread(), "a", answered_at="Tue:09", declined=True)
        self.assertTrue(updated["declined_a"])
        self.assertIsNone(updated["answer_a"])

    def test_does_not_mutate_input(self) -> None:
        thread = _thread()
        submit_answer(thread, "a", answered_at="Tue:09", answer_text="x")
        self.assertIsNone(thread["answer_a"])


class ReciprocalUnlockTests(unittest.TestCase):
    """Part F: "Reciprocal unlock applies to every Next Level question" —
    neither side's answer becomes visible until BOTH have answered (or
    declined) that specific question."""

    def test_not_revealed_after_only_one_side_answers(self) -> None:
        thread = _thread()
        thread = submit_answer(thread, "a", answered_at="Tue:09", answer_text="Slow.")
        self.assertIsNone(thread["revealed_at"])
        seen_by_b = visible_answers(thread, "b")
        self.assertFalse(seen_by_b["revealed"])
        self.assertIsNone(seen_by_b["partner_answer"])

    def test_revealed_the_moment_the_second_side_answers(self) -> None:
        thread = _thread()
        thread = submit_answer(thread, "a", answered_at="Tue:09", answer_text="Slow.")
        thread = submit_answer(thread, "b", answered_at="Tue:10", answer_text="Also slow.")
        self.assertEqual(thread["revealed_at"], "Tue:10")
        seen_by_a = visible_answers(thread, "a")
        self.assertTrue(seen_by_a["revealed"])
        self.assertEqual(seen_by_a["partner_answer"], "Also slow.")

    def test_a_decline_still_counts_as_completing_that_side(self) -> None:
        thread = _thread()
        thread = submit_answer(thread, "a", answered_at="Tue:09", declined=True)
        thread = submit_answer(thread, "b", answered_at="Tue:10", answer_text="Some answer.")
        self.assertIsNotNone(thread["revealed_at"])
        seen_by_b = visible_answers(thread, "b")
        self.assertEqual(seen_by_b["partner_answer"], "chose not to answer")

    def test_own_answer_always_visible_before_reveal(self) -> None:
        thread = _thread()
        thread = submit_answer(thread, "a", answered_at="Tue:09", answer_text="Slow.")
        seen_by_a = visible_answers(thread, "a")
        self.assertEqual(seen_by_a["own_answer"], "Slow.")


class ReluctanceReflectionTests(unittest.TestCase):
    """"The reluctance flag is never visible to the partner." — the
    core guardrail of Pass B."""

    def _reluctance_thread(self) -> dict:
        return _thread(RELUCTANCE_QUESTION_KEY)

    def test_reluctant_language_flags_the_answering_side_only(self) -> None:
        thread = submit_answer(
            self._reluctance_thread(), "a", answered_at="Tue:09",
            answer_text="I guess I feel like I should, even though I'm not totally sure.",
        )
        self.assertEqual(thread["reluctance_flagged_to"], "a")

    def test_confident_language_does_not_flag(self) -> None:
        thread = submit_answer(self._reluctance_thread(), "a", answered_at="Tue:09", answer_text="No, I genuinely want this.")
        self.assertIsNone(thread["reluctance_flagged_to"])

    def test_flagged_side_sees_the_reflection(self) -> None:
        thread = submit_answer(
            self._reluctance_thread(), "a", answered_at="Tue:09", answer_text="I feel like I should say yes."
        )
        seen_by_a = visible_answers(thread, "a")
        self.assertIsNotNone(seen_by_a["reluctance_reflection"])

    def test_partner_never_sees_the_reflection_even_after_reveal(self) -> None:
        thread = self._reluctance_thread()
        thread = submit_answer(thread, "a", answered_at="Tue:09", answer_text="I feel like I should say yes.")
        thread = submit_answer(thread, "b", answered_at="Tue:10", answer_text="I'm genuinely excited.")
        self.assertIsNotNone(thread["revealed_at"])  # fully revealed to both...
        seen_by_b = visible_answers(thread, "b")
        self.assertEqual(seen_by_b["partner_answer"], "I feel like I should say yes.")  # ...the answer text, yes...
        self.assertIsNone(seen_by_b["reluctance_reflection"])  # ...but never the reluctance flag itself

    def test_declining_the_reluctance_question_never_flags_anyone(self) -> None:
        thread = submit_answer(self._reluctance_thread(), "a", answered_at="Tue:09", declined=True)
        self.assertIsNone(thread["reluctance_flagged_to"])

    def test_reluctance_detection_is_scoped_to_its_own_question(self) -> None:
        # The same "I feel like I should" phrasing on an unrelated
        # question must never set reluctance_flagged_to.
        thread = submit_answer(_thread("pace_from_here"), "a", answered_at="Tue:09", answer_text="I feel like I should slow down.")
        self.assertIsNone(thread["reluctance_flagged_to"])


if __name__ == "__main__":
    unittest.main()
