"""Tests for payments.py — the four fees and the entitlement layer
(Segment D).

The assertion that matters most is scoping: a fee is not "paid once,
forever". Getting that wrong means the second date is free, which is a
revenue bug nobody notices until the numbers are wrong.
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

import payments


def _paid(user_id="u1", purpose=payments.AVAILABILITY, scope_id="lockin-1"):
    row = payments.payment_row(user_id, purpose, scope_id, "W1 Mon 12:00")
    return payments.simulate_gateway_callback(row, succeeded=True)


class FeeTableTests(unittest.TestCase):
    def test_the_four_price_points_match_the_mockup(self):
        self.assertEqual(payments.FEES[payments.AVAILABILITY]["amount_inr"], 499)
        self.assertEqual(payments.FEES[payments.AGREEMENT]["amount_inr"], 1499)
        self.assertEqual(payments.FEES[payments.STAGE_GATE]["amount_inr"], 2999)
        self.assertEqual(payments.FEES[payments.GURU]["amount_inr"], 4999)

    def test_only_guru_recurs(self):
        recurring = [p for p in payments.PURPOSES if payments.FEES[p]["recurring"]]
        self.assertEqual(recurring, [payments.GURU])

    def test_amounts_render_with_thousands_separators(self):
        self.assertEqual(payments.amount_label(payments.AGREEMENT), "₹1,499")
        self.assertEqual(payments.amount_label(payments.AVAILABILITY), "₹499")

    def test_an_unknown_purpose_raises_rather_than_charging_zero(self):
        with self.assertRaises(ValueError):
            payments.fee("premium_gold")


class EntitlementTests(unittest.TestCase):
    """These assert what the gate does when fees ARE enforced, so they pin
    the switch rather than inheriting whatever the shell happens to set.
    A test that changes its answer with the environment is not a test."""

    def setUp(self):
        self._env = mock.patch.dict(os.environ, {"PAYMENTS_ENABLED": "1"})
        self._env.start()
        self.addCleanup(self._env.stop)

    def test_a_paid_row_entitles_its_own_scope(self):
        rows = [_paid(scope_id="lockin-1")]
        self.assertTrue(payments.has_paid(rows, "u1", payments.AVAILABILITY, "lockin-1"))

    def test_a_fee_is_not_paid_forever(self):
        """The availability fee is per date. Paying for one must not
        entitle the next one."""
        rows = [_paid(scope_id="lockin-1")]
        self.assertFalse(payments.has_paid(rows, "u1", payments.AVAILABILITY, "lockin-2"))

    def test_paying_one_fee_does_not_entitle_another(self):
        rows = [_paid(purpose=payments.AVAILABILITY, scope_id="s1")]
        self.assertFalse(payments.has_paid(rows, "u1", payments.AGREEMENT, "s1"))

    def test_one_users_payment_does_not_entitle_another(self):
        rows = [_paid(user_id="u1", scope_id="s1")]
        self.assertFalse(payments.has_paid(rows, "u2", payments.AVAILABILITY, "s1"))

    def test_a_pending_or_failed_row_entitles_nothing(self):
        pending = payments.payment_row("u1", payments.AVAILABILITY, "s1", "t")
        failed = payments.simulate_gateway_callback(pending, succeeded=False)
        for rows in ([pending], [failed]):
            self.assertFalse(payments.has_paid(rows, "u1", payments.AVAILABILITY, "s1"))

    def test_scope_ids_compare_as_strings(self):
        """Scope ids arrive from the database as text and from route args
        as text, but a caller may hand over an int."""
        rows = [_paid(scope_id="7")]
        self.assertTrue(payments.has_paid(rows, "u1", payments.AVAILABILITY, 7))


class SwitchTests(unittest.TestCase):
    def test_fees_are_enforced_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(payments.is_enabled())

    def test_disabling_fees_entitles_everything(self):
        """The gate disappears rather than letting unpaid rows through,
        which would be the same behaviour with a worse audit trail."""
        with mock.patch.dict(os.environ, {"PAYMENTS_ENABLED": "0"}):
            self.assertFalse(payments.is_enabled())
            self.assertTrue(payments.has_paid([], "u1", payments.AGREEMENT, "anything"))

    def test_the_off_switch_accepts_the_usual_spellings(self):
        for value in ("0", "false", "no", "off", "OFF", " False "):
            with mock.patch.dict(os.environ, {"PAYMENTS_ENABLED": value}):
                self.assertFalse(payments.is_enabled(), value)


class RowTests(unittest.TestCase):
    def test_the_row_id_makes_a_repeated_webhook_idempotent(self):
        """The same callback arriving twice must write once. Charging
        twice for one date is the failure mode people remember."""
        a = payments.payment_row("u1", payments.AGREEMENT, "plan-9", "t")
        b = payments.payment_row("u1", payments.AGREEMENT, "plan-9", "t")
        self.assertEqual(a["id"], b["id"])

    def test_different_scopes_are_different_rows(self):
        a = payments.payment_row("u1", payments.AVAILABILITY, "lockin-1", "t")
        b = payments.payment_row("u1", payments.AVAILABILITY, "lockin-2", "t")
        self.assertNotEqual(a["id"], b["id"])

    def test_the_amount_is_taken_from_the_table_not_the_caller(self):
        row = payments.payment_row("u1", payments.STAGE_GATE, "pair-1", "t")
        self.assertEqual(row["amount_inr"], 2999)

    def test_a_new_row_starts_unpaid(self):
        self.assertEqual(payments.payment_row("u1", payments.GURU, "week-1", "t")["status"],
                         payments.PENDING)

    def test_a_bad_status_raises(self):
        with self.assertRaises(ValueError):
            payments.payment_row("u1", payments.GURU, "week-1", "t", status="probably")


class CheckoutViewTests(unittest.TestCase):
    def test_an_unpaid_checkout_offers_the_amount(self):
        view = payments.checkout_view(payments.AGREEMENT, "plan-1", paid=False)
        self.assertEqual(view["cta"], "Pay ₹1,499")
        self.assertEqual(view["period"], "one-off")

    def test_a_paid_checkout_does_not_offer_to_charge_again(self):
        view = payments.checkout_view(payments.AGREEMENT, "plan-1", paid=True)
        self.assertNotIn("Pay", view["cta"])

    def test_the_subscription_is_labelled_per_month(self):
        self.assertEqual(payments.checkout_view(payments.GURU, "week-1", False)["period"], "per month")


if __name__ == "__main__":
    unittest.main()
