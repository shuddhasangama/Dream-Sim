"""Tests for outcomes.py."""

from __future__ import annotations

import unittest

from outcomes import apply_resolution, compliance_status, record_compliance_event, record_outcome, resolution


def _outcome(a_decision, b_decision, **kw) -> dict:
    return record_outcome("plan-1", happened=True, a_decision=a_decision, b_decision=b_decision, **kw)


class RecordOutcomeTests(unittest.TestCase):
    def test_defaults_photos_off(self) -> None:
        outcome = _outcome("continue", "continue")
        self.assertFalse(outcome["together_photo"])
        self.assertFalse(outcome["bill_photo"])

    def test_carries_reasons_through(self) -> None:
        outcome = _outcome("pass", "continue", a_reason="Didn't click")
        self.assertEqual(outcome["a_reason"], "Didn't click")
        self.assertIsNone(outcome["b_reason"])

    def test_flag_fields_default_to_empty_lists(self) -> None:
        outcome = _outcome("continue", "continue")
        self.assertEqual(outcome["a_green_flags"], [])
        self.assertEqual(outcome["a_red_flags"], [])
        self.assertEqual(outcome["b_green_flags"], [])
        self.assertEqual(outcome["b_red_flags"], [])

    def test_carries_flags_through(self) -> None:
        outcome = _outcome("continue", "continue", a_green_flags=["On time", "Made me laugh"], b_red_flags=["Showed up late"])
        self.assertEqual(outcome["a_green_flags"], ["On time", "Made me laugh"])
        self.assertEqual(outcome["b_red_flags"], ["Showed up late"])


class ResolutionTests(unittest.TestCase):
    def test_pending_when_either_decision_missing(self) -> None:
        self.assertEqual(resolution(_outcome(None, "continue")), "pending")
        self.assertEqual(resolution(_outcome("continue", None)), "pending")

    def test_both_relationship(self) -> None:
        self.assertEqual(resolution(_outcome("relationship", "relationship")), "both_relationship")

    def test_both_continue_is_keep_dating(self) -> None:
        self.assertEqual(resolution(_outcome("continue", "continue")), "keep_dating")

    def test_one_relationship_one_continue_is_keep_dating_not_forced(self) -> None:
        # Only BOTH picking 'relationship' advances the stage — one side
        # wanting more dates first must not be overridden.
        self.assertEqual(resolution(_outcome("relationship", "continue")), "keep_dating")
        self.assertEqual(resolution(_outcome("continue", "relationship")), "keep_dating")

    def test_either_pass_is_rejected_regardless_of_the_other_side(self) -> None:
        self.assertEqual(resolution(_outcome("pass", "pass")), "rejected")
        self.assertEqual(resolution(_outcome("continue", "pass")), "rejected")
        self.assertEqual(resolution(_outcome("relationship", "pass")), "rejected")

    def test_ghosted_takes_priority_over_an_accept(self) -> None:
        self.assertEqual(resolution(_outcome("relationship", "ghosted")), "ghosted")

    def test_ghosted_takes_priority_over_a_pass(self) -> None:
        self.assertEqual(resolution(_outcome("ghosted", "pass")), "ghosted")


class ApplyResolutionTests(unittest.TestCase):
    def test_both_relationship_advances_and_does_not_release_or_continue(self) -> None:
        result = apply_resolution(_outcome("relationship", "relationship"))
        self.assertTrue(result["advance_to_relationship"])
        self.assertFalse(result["release_lockin"])
        self.assertFalse(result["continue_dating"])
        self.assertIsNone(result["release_reason"])

    def test_keep_dating_neither_advances_nor_releases(self) -> None:
        result = apply_resolution(_outcome("continue", "continue"))
        self.assertFalse(result["advance_to_relationship"])
        self.assertFalse(result["release_lockin"])
        self.assertTrue(result["continue_dating"])

    def test_mismatched_accept_also_keeps_dating(self) -> None:
        result = apply_resolution(_outcome("relationship", "continue"))
        self.assertFalse(result["advance_to_relationship"])
        self.assertTrue(result["continue_dating"])

    def test_pending_does_nothing(self) -> None:
        result = apply_resolution(_outcome("continue", None))
        self.assertFalse(result["advance_to_relationship"])
        self.assertFalse(result["release_lockin"])
        self.assertFalse(result["continue_dating"])

    def test_rejected_releases_with_a_reason(self) -> None:
        result = apply_resolution(_outcome("continue", "pass"))
        self.assertFalse(result["advance_to_relationship"])
        self.assertTrue(result["release_lockin"])
        self.assertFalse(result["continue_dating"])
        self.assertIsNotNone(result["release_reason"])

    def test_ghosted_releases(self) -> None:
        result = apply_resolution(_outcome("ghosted", "continue"))
        self.assertTrue(result["release_lockin"])
        self.assertFalse(result["advance_to_relationship"])
        self.assertFalse(result["continue_dating"])


class RecordComplianceEventTests(unittest.TestCase):
    def test_accepts_valid_type(self) -> None:
        event = record_compliance_event("u_a", "no_show", week=3)
        self.assertEqual(event["type"], "no_show")

    def test_rejects_invalid_type(self) -> None:
        with self.assertRaises(ValueError):
            record_compliance_event("u_a", "vibe-mismatch", week=3)


class ComplianceStatusTests(unittest.TestCase):
    def test_ok_with_no_events(self) -> None:
        self.assertEqual(compliance_status([]), "ok")

    def test_ok_with_a_good_rating(self) -> None:
        events = [record_compliance_event("u_a", "rating", week=1, value="5")]
        self.assertEqual(compliance_status(events), "ok")

    def test_low_rating_counts_as_a_strike(self) -> None:
        events = [record_compliance_event("u_a", "rating", week=w, value="1") for w in range(3)]
        self.assertEqual(compliance_status(events), "warning")

    def test_non_rating_events_always_strike(self) -> None:
        events = [record_compliance_event("u_a", "no_show", week=w) for w in range(3)]
        self.assertEqual(compliance_status(events), "warning")

    def test_escalates_to_suspended_then_removed(self) -> None:
        six = [record_compliance_event("u_a", "late_cancel", week=w) for w in range(6)]
        self.assertEqual(compliance_status(six), "suspended")
        ten = [record_compliance_event("u_a", "late_cancel", week=w) for w in range(10)]
        self.assertEqual(compliance_status(ten), "removed")

    def test_romantic_outcome_alone_is_not_a_strike(self) -> None:
        # Passing on someone, or being passed on, isn't itself a
        # ComplianceEvent — ratings/no-shows/reports/violations are.
        events = [record_compliance_event("u_a", "rating", week=1, value="4")] * 20
        self.assertEqual(compliance_status(events), "ok")


if __name__ == "__main__":
    unittest.main()
