"""Tests for dateplan.py."""

from __future__ import annotations

import unittest

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
