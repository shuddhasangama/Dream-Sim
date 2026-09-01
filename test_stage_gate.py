"""Tests for stage_gate.py."""

from __future__ import annotations

import unittest

from stage_gate import (
    STAGE_GATE_QUESTIONS,
    _ALL_KEYS,
    all_questions_answered,
    analyze_gate,
    confirm_progression,
    has_unresolved_exclusivity_mismatch,
    open_gate,
    resolve_gate,
    submit_gate_response,
)


def _answer_everything(pair_id: str, user_id: str, overrides: dict[str, dict] | None = None) -> list[dict]:
    overrides = overrides or {}
    responses = []
    for question in STAGE_GATE_QUESTIONS:
        key = question["key"]
        kwargs = overrides.get(key)
        if kwargs is not None:
            responses.append(submit_gate_response(pair_id, user_id, key, **kwargs))
        elif question["kind"] == "scale":
            responses.append(submit_gate_response(pair_id, user_id, key, readiness_scale=question["options"][0]))
        else:
            responses.append(submit_gate_response(pair_id, user_id, key, answer_text="an answer"))
    return responses


class OpenGateTests(unittest.TestCase):
    def test_builds_an_open_gate(self) -> None:
        gate = open_gate("lockin-1", "exclusivity_raised", "Mon:12")
        self.assertEqual(gate["status"], "open")
        self.assertIsNone(gate["resolved_at"])

    def test_rejects_unknown_trigger(self) -> None:
        with self.assertRaises(ValueError):
            open_gate("lockin-1", "curiosity", "Mon:12")


class SubmitGateResponseTests(unittest.TestCase):
    def test_text_question_accepts_free_text(self) -> None:
        row = submit_gate_response("lockin-1", "u_a", "open_question", answer_text="Do they want kids?")
        self.assertEqual(row["answer_text"], "Do they want kids?")

    def test_scale_question_accepts_a_valid_option(self) -> None:
        row = submit_gate_response("lockin-1", "u_a", "ready_meet_family", readiness_scale="soon")
        self.assertEqual(row["readiness_scale"], "soon")

    def test_rejects_unknown_question_key(self) -> None:
        with self.assertRaises(ValueError):
            submit_gate_response("lockin-1", "u_a", "favourite_colour", answer_text="blue")

    def test_rejects_invalid_scale_value(self) -> None:
        with self.assertRaises(ValueError):
            submit_gate_response("lockin-1", "u_a", "ready_meet_family", readiness_scale="maybe")

    def test_declining_is_free_no_answer_at_all(self) -> None:
        row = submit_gate_response("lockin-1", "u_a", "money_talk")
        self.assertIsNone(row["answer_text"])
        self.assertIsNone(row["readiness_scale"])


class AllQuestionsAnsweredTests(unittest.TestCase):
    def test_true_once_every_key_has_a_response(self) -> None:
        responses = _answer_everything("lockin-1", "u_a")
        self.assertTrue(all_questions_answered(responses))

    def test_false_when_one_key_missing(self) -> None:
        responses = _answer_everything("lockin-1", "u_a")[:-1]
        self.assertFalse(all_questions_answered(responses))

    def test_declining_still_counts_as_answered(self) -> None:
        responses = [submit_gate_response("lockin-1", "u_a", key) for key in _ALL_KEYS]
        self.assertTrue(all_questions_answered(responses))


class AnalyzeGateNeverQuotesRawAnswersTests(unittest.TestCase):
    """Part F / B4: "Guru synthesizes divergence; it never quotes one
    partner's raw answer to the other." — a structural check that none
    of analyze_gate()'s own free-text answer content ever appears in its
    output notes."""

    def test_distinctive_answer_text_never_appears_in_the_analysis(self) -> None:
        secret_a = "XYZZY_SECRET_ANSWER_FROM_A"
        secret_b = "PLUGH_SECRET_ANSWER_FROM_B"
        responses_a = _answer_everything("lockin-1", "u_a", overrides={"open_question": {"answer_text": secret_a}})
        responses_b = _answer_everything("lockin-1", "u_b", overrides={"open_question": {"answer_text": secret_b}})
        analysis = analyze_gate("lockin-1", responses_a, responses_b)
        serialized = str(analysis)
        self.assertNotIn(secret_a, serialized)
        self.assertNotIn(secret_b, serialized)


class AnalyzeGateDivergenceTests(unittest.TestCase):
    def test_no_divergence_when_answers_match(self) -> None:
        responses_a = _answer_everything("lockin-1", "u_a")
        responses_b = _answer_everything("lockin-1", "u_b")
        analysis = analyze_gate("lockin-1", responses_a, responses_b)
        self.assertEqual(analysis["divergences"], [])
        self.assertEqual(analysis["must_resolve"], [])

    def test_material_readiness_gap_surfaces_as_a_divergence(self) -> None:
        responses_a = _answer_everything("lockin-1", "u_a", overrides={"ready_meet_family": {"readiness_scale": "ready_now"}})
        responses_b = _answer_everything("lockin-1", "u_b", overrides={"ready_meet_family": {"readiness_scale": "not_yet"}})
        analysis = analyze_gate("lockin-1", responses_a, responses_b)
        keys = [d["question_key"] for d in analysis["divergences"]]
        self.assertIn("ready_meet_family", keys)

    def test_minor_readiness_gap_does_not_surface(self) -> None:
        responses_a = _answer_everything("lockin-1", "u_a", overrides={"ready_meet_family": {"readiness_scale": "ready_now"}})
        responses_b = _answer_everything("lockin-1", "u_b", overrides={"ready_meet_family": {"readiness_scale": "soon"}})
        analysis = analyze_gate("lockin-1", responses_a, responses_b)
        keys = [d["question_key"] for d in analysis["divergences"]]
        self.assertNotIn("ready_meet_family", keys)

    def test_exclusivity_mismatch_goes_to_must_resolve_not_divergences(self) -> None:
        responses_a = _answer_everything("lockin-1", "u_a", overrides={"exclusivity_check": {"readiness_scale": "exclusive"}})
        responses_b = _answer_everything("lockin-1", "u_b", overrides={"exclusivity_check": {"readiness_scale": "open_to_others"}})
        analysis = analyze_gate("lockin-1", responses_a, responses_b)
        self.assertTrue(has_unresolved_exclusivity_mismatch(analysis))
        divergence_keys = [d["question_key"] for d in analysis["divergences"]]
        self.assertNotIn("exclusivity_check", divergence_keys)

    def test_no_exclusivity_mismatch_when_answers_match(self) -> None:
        responses_a = _answer_everything("lockin-1", "u_a", overrides={"exclusivity_check": {"readiness_scale": "exclusive"}})
        responses_b = _answer_everything("lockin-1", "u_b", overrides={"exclusivity_check": {"readiness_scale": "exclusive"}})
        analysis = analyze_gate("lockin-1", responses_a, responses_b)
        self.assertFalse(has_unresolved_exclusivity_mismatch(analysis))

    def test_open_question_answered_by_a_prompts_only_a(self) -> None:
        responses_a = _answer_everything("lockin-1", "u_a", overrides={"open_question": {"answer_text": "Do they want kids?"}})
        responses_b = _answer_everything("lockin-1", "u_b", overrides={"open_question": {}})
        analysis = analyze_gate("lockin-1", responses_a, responses_b)
        prompted_for = [p["for"] for p in analysis["guru_prompts"]]
        self.assertIn("a", prompted_for)
        self.assertNotIn("b", prompted_for)


class ConfirmProgressionTests(unittest.TestCase):
    def test_both_confirm(self) -> None:
        result = confirm_progression(True, True)
        self.assertTrue(result["progressed"])

    def test_either_declines(self) -> None:
        self.assertFalse(confirm_progression(True, False)["progressed"])
        self.assertFalse(confirm_progression(False, True)["progressed"])
        self.assertFalse(confirm_progression(False, False)["progressed"])


class ResolveGateTests(unittest.TestCase):
    def test_marks_progressed(self) -> None:
        gate = open_gate("lockin-1", "exclusivity_raised", "Mon:12")
        resolved = resolve_gate(gate, "progressed", "Tue:09")
        self.assertEqual(resolved["status"], "progressed")
        self.assertEqual(resolved["resolved_at"], "Tue:09")

    def test_rejects_unknown_status(self) -> None:
        gate = open_gate("lockin-1", "exclusivity_raised", "Mon:12")
        with self.assertRaises(ValueError):
            resolve_gate(gate, "vibes-off", "Tue:09")


if __name__ == "__main__":
    unittest.main()
