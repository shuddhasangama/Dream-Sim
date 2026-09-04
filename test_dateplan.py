"""Tests for dateplan.py."""

from __future__ import annotations

import unittest

import dateplan
from dateplan import (
    ACK_FIELDS,
    BILL_SPLIT_OPTIONS,
    generate_plan,
    is_confirmed,
    is_fully_acknowledged,
    payment_open,
    sign,
    verify_face,
)


def _full_acks() -> dict:
    return {f: True for f in ACK_FIELDS}


class VerifyFaceTests(unittest.TestCase):
    def test_deterministic_for_a_given_seed(self) -> None:
        self.assertEqual(verify_face("u_a", seed="attempt-1"), verify_face("u_a", seed="attempt-1"))

    def test_default_seed_is_the_user_id(self) -> None:
        self.assertEqual(verify_face("u_a"), verify_face("u_a", seed="u_a"))

    def test_success_rate_one_always_succeeds(self) -> None:
        for i in range(20):
            self.assertTrue(verify_face(f"u_{i}", success_rate=1.0))

    def test_success_rate_zero_always_fails(self) -> None:
        for i in range(20):
            self.assertFalse(verify_face(f"u_{i}", success_rate=0.0))

    def test_different_seeds_can_give_different_outcomes(self) -> None:
        outcomes = {verify_face("u_a", success_rate=0.5, seed=s) for s in range(20)}
        self.assertEqual(outcomes, {True, False})


class GeneratePlanTests(unittest.TestCase):
    def test_fills_expected_fields(self) -> None:
        plan = generate_plan(
            lockin_id="lockin-1",
            confirmed_slot={"day": "Sat", "meal_slot": "dinner"},
            venue={"venue": "Multi-cuisine bistro", "cuisine": "multi-cuisine"},
            datetime_str="2026-02-07T19:00",
            bill_split="pay-your-own",
            selections_a={"greeting": "handshake", "dietary": "no allergies", "dress": "smart casual"},
            selections_b={"greeting": "namaste", "dietary": "peanut allergy", "dress": "casual"},
        )
        self.assertEqual(plan["meal"], "dinner")
        self.assertEqual(plan["venue"], "Multi-cuisine bistro")
        self.assertEqual(plan["bill_split"], "pay-your-own")
        self.assertEqual(plan["status"], "pending_signatures")
        self.assertEqual(plan["selections_a_json"]["greeting"], "handshake")
        self.assertEqual(plan["selections_b_json"]["greeting"], "namaste")

    def test_budget_estimate_auto_filled(self) -> None:
        plan = generate_plan(
            lockin_id="lockin-1",
            confirmed_slot={"day": "Sat", "meal_slot": "dinner"},
            venue={"venue": None, "cuisine": None},
            datetime_str="2026-02-07T19:00",
            bill_split="pay-your-own",
            selections_a={},
            selections_b={},
        )
        self.assertTrue(plan["budget_estimate"])

    def test_only_two_bill_split_options(self) -> None:
        self.assertEqual(set(BILL_SPLIT_OPTIONS), {"pay-your-own", "one-third-two-thirds"})

    def test_rejects_invalid_bill_split(self) -> None:
        with self.assertRaises(ValueError):
            generate_plan(
                lockin_id="lockin-1",
                confirmed_slot={"day": "Sat", "meal_slot": "dinner"},
                venue={"venue": None, "cuisine": None},
                datetime_str="2026-02-07T19:00",
                bill_split="split-the-difference",
                selections_a={},
                selections_b={},
            )

    def test_config_overrides_defaults(self) -> None:
        plan = generate_plan(
            lockin_id="lockin-1",
            confirmed_slot={"day": "Fri", "meal_slot": "coffee"},
            venue={"venue": None, "cuisine": None},
            datetime_str="2026-02-06T18:00",
            bill_split="one-third-two-thirds",
            selections_a={},
            selections_b={},
            config={"fee": 500.0, "cancel_notice_hrs": 12},
        )
        self.assertEqual(plan["fee"], 500.0)
        self.assertEqual(plan["cancel_notice_hrs"], 12)
        self.assertEqual(plan["cancel_fee"], 0.0)  # untouched default

    def test_decide_together_venue_leaves_venue_and_cuisine_none(self) -> None:
        plan = generate_plan(
            lockin_id="lockin-1",
            confirmed_slot={"day": "Sat", "meal_slot": "lunch"},
            venue={"venue": None, "cuisine": None},
            datetime_str="2026-02-07T13:00",
            bill_split="pay-your-own",
            selections_a={},
            selections_b={},
        )
        self.assertIsNone(plan["venue"])
        self.assertIsNone(plan["cuisine"])


class SignTests(unittest.TestCase):
    def test_records_all_ack_fields(self) -> None:
        sig = sign("plan-1", "u_a", _full_acks(), signed_at="Thu:19", face_verified=True)
        for field in ACK_FIELDS:
            self.assertTrue(sig[field])
        self.assertTrue(sig["face_verified"])

    def test_missing_ack_recorded_as_false_not_omitted(self) -> None:
        partial = {f: True for f in ACK_FIELDS if f != "ack_liability"}
        sig = sign("plan-1", "u_a", partial, signed_at="Thu:19", face_verified=True)
        self.assertFalse(sig["ack_liability"])


class IsFullyAcknowledgedTests(unittest.TestCase):
    def test_true_when_all_acks_and_face_verified(self) -> None:
        sig = sign("plan-1", "u_a", _full_acks(), "Thu:19", face_verified=True)
        self.assertTrue(is_fully_acknowledged(sig))

    def test_false_if_face_not_verified(self) -> None:
        sig = sign("plan-1", "u_a", _full_acks(), "Thu:19", face_verified=False)
        self.assertFalse(is_fully_acknowledged(sig))

    def test_false_if_any_ack_missing(self) -> None:
        partial = {f: True for f in ACK_FIELDS if f != "ack_conduct"}
        sig = sign("plan-1", "u_a", partial, "Thu:19", face_verified=True)
        self.assertFalse(is_fully_acknowledged(sig))


class IsConfirmedTests(unittest.TestCase):
    def test_false_with_no_signatures(self) -> None:
        self.assertFalse(is_confirmed([], "u_a", "u_b"))

    def test_false_with_only_one_signature(self) -> None:
        sigs = [sign("plan-1", "u_a", _full_acks(), "Thu:19", True)]
        self.assertFalse(is_confirmed(sigs, "u_a", "u_b"))

    def test_true_once_both_have_fully_signed(self) -> None:
        sigs = [
            sign("plan-1", "u_a", _full_acks(), "Thu:19", True),
            sign("plan-1", "u_b", _full_acks(), "Thu:20", True),
        ]
        self.assertTrue(is_confirmed(sigs, "u_a", "u_b"))

    def test_false_if_one_signature_is_incomplete(self) -> None:
        sigs = [
            sign("plan-1", "u_a", _full_acks(), "Thu:19", True),
            sign("plan-1", "u_b", {}, "Thu:20", True),
        ]
        self.assertFalse(is_confirmed(sigs, "u_a", "u_b"))


class PaymentOpenTests(unittest.TestCase):
    def test_closed_before_dual_signature(self) -> None:
        sigs = [sign("plan-1", "u_a", _full_acks(), "Thu:19", True)]
        self.assertFalse(payment_open(sigs, "u_a", "u_b"))

    def test_open_once_confirmed(self) -> None:
        sigs = [
            sign("plan-1", "u_a", _full_acks(), "Thu:19", True),
            sign("plan-1", "u_b", _full_acks(), "Thu:20", True),
        ]
        self.assertTrue(payment_open(sigs, "u_a", "u_b"))


if __name__ == "__main__":
    unittest.main()


class SlotTimingTests(unittest.TestCase):
    """2026-09-04, user's rule: the debrief opens an hour after the date
    starts, not on Sunday night. That timing is what makes a no-show
    reportable the same evening instead of three days later."""

    def test_every_meal_slot_has_a_start_time(self):
        for meal in ("breakfast", "lunch", "coffee", "dinner"):
            with self.subTest(meal=meal):
                hour, minute = dateplan.slot_start(meal)
                self.assertTrue(0 <= hour <= 23 and 0 <= minute <= 59)

    def test_an_unknown_slot_raises_rather_than_guessing_a_time(self):
        with self.assertRaises(ValueError):
            dateplan.slot_start("brunch")

    def test_the_debrief_opens_an_hour_after_a_whole_hour_slot(self):
        self.assertEqual(dateplan.debrief_opens_hour("lunch"), 14)
        self.assertEqual(dateplan.debrief_opens_hour("breakfast"), 10)
        self.assertEqual(dateplan.debrief_opens_hour("coffee"), 18)

    def test_a_half_hour_slot_rounds_up_rather_than_down(self):
        """Dinner starts 19:30, so an hour later is 20:30. Opening at
        20:00 would put "how was it?" in front of someone still at the
        table; 21:00 is the first whole hour that is genuinely after."""
        self.assertEqual(dateplan.debrief_opens_hour("dinner"), 21)

    def test_it_never_runs_past_the_end_of_the_day(self):
        for meal in dateplan.MEAL_SLOT_TIMES:
            self.assertLessEqual(dateplan.debrief_opens_hour(meal), 23)


class CancellationPolicyTests(unittest.TestCase):
    """Dates are set on Thursday for the weekend, so a free cancellation is
    an invitation to change your mind at everyone else's expense."""

    FEE = 999

    def test_inside_the_window_it_costs_and_is_recorded(self):
        result = dateplan.cancellation(6, self.FEE)
        self.assertTrue(result["late"])
        self.assertEqual(result["fee_inr"], self.FEE)
        self.assertEqual(result["compliance_event"], "late_cancel")

    def test_outside_the_window_it_is_free_and_unrecorded(self):
        """Punishing honest early notice teaches people to no-show
        instead, which is the behaviour the fee exists to prevent."""
        result = dateplan.cancellation(48, self.FEE)
        self.assertFalse(result["late"])
        self.assertEqual(result["fee_inr"], 0)
        self.assertIsNone(result["compliance_event"])

    def test_the_boundary_is_inclusive_of_the_full_notice_period(self):
        self.assertFalse(dateplan.cancellation(dateplan.CANCELLATION_NOTICE_HOURS, self.FEE)["late"])
        self.assertTrue(dateplan.cancellation(dateplan.CANCELLATION_NOTICE_HOURS - 1, self.FEE)["late"])

    def test_cancelling_after_the_slot_has_passed_is_still_late(self):
        self.assertTrue(dateplan.cancellation(-3, self.FEE)["late"])

    def test_the_reason_states_the_notice_and_the_window(self):
        self.assertIn("6h notice", dateplan.cancellation(6, self.FEE)["reason"])
        self.assertIn("24h window", dateplan.cancellation(6, self.FEE)["reason"])

    def test_a_thursday_set_weekend_date_is_outside_the_window(self):
        """The scenario the rule was written for: set Thursday noon, date
        Saturday evening."""
        notice = dateplan.hours_between((3, 12), (5, 19))
        self.assertEqual(notice, 55)
        self.assertFalse(dateplan.cancellation(notice, self.FEE)["late"])

    def test_the_morning_of_the_date_is_inside_it(self):
        notice = dateplan.hours_between((5, 10), (5, 19))
        self.assertEqual(notice, 9)
        self.assertTrue(dateplan.cancellation(notice, self.FEE)["late"])
