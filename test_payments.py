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

import billing_catalog
import billing_service
import payments


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
    """Only the verified billing ledger can satisfy an unwaived fee gate."""

    def setUp(self):
        self._env = mock.patch.dict(os.environ, {"DHASHU_FEES_WAIVED": "0"})
        self._env.start()
        self.addCleanup(self._env.stop)
        self.active = {("u1", "date_mechanics", "lockin-1")}
        self._ledger = mock.patch.object(
            billing_service, "entitled",
            side_effect=lambda _conn, uid, product, scope: (uid, product, scope) in self.active,
        )
        self._ledger.start()
        self.addCleanup(self._ledger.stop)

    def test_a_paid_row_entitles_its_own_scope(self):
        self.assertTrue(billing_service.fee_satisfied(None, "u1", payments.AVAILABILITY, "lockin-1"))

    def test_a_fee_is_not_paid_forever(self):
        self.assertFalse(billing_service.fee_satisfied(None, "u1", payments.AVAILABILITY, "lockin-2"))

    def test_paying_one_fee_does_not_entitle_another(self):
        self.assertFalse(billing_service.fee_satisfied(None, "u1", payments.STAGE_GATE, "lockin-1"))

    def test_one_users_payment_does_not_entitle_another(self):
        self.assertFalse(billing_service.fee_satisfied(None, "u2", payments.AVAILABILITY, "lockin-1"))

    def test_a_pending_or_failed_row_entitles_nothing(self):
        self.active.clear()
        self.assertFalse(billing_service.fee_satisfied(None, "u1", payments.AVAILABILITY, "lockin-1"))

    def test_scope_ids_compare_as_strings(self):
        self.assertFalse(billing_service.fee_satisfied(None, "u1", payments.AVAILABILITY, 7))
        self.assertFalse(billing_service.fee_satisfied(None, "u1", "unknown", "lockin-1"))

    def test_guru_uses_own_verified_subscription(self):
        self.active.add(("u1", "guru", "u1"))
        self.assertTrue(billing_service.fee_satisfied(None, "u1", payments.GURU, "week-1"))
        self.assertFalse(billing_service.fee_satisfied(None, "u2", payments.GURU, "week-1"))

    def test_invalid_identity_scope_and_purpose_fail_closed(self):
        for uid, purpose, scope in (("", payments.AVAILABILITY, "lockin-1"),
                                    (None, payments.AVAILABILITY, "lockin-1"),
                                    ("u1", payments.AVAILABILITY, ""),
                                    ("u1", payments.AVAILABILITY, None),
                                    ("u1", "availability; DROP TABLE Payment", "lockin-1")):
            self.assertFalse(billing_service.fee_satisfied(None, uid, purpose, scope))


class SwitchTests(unittest.TestCase):
    def test_fees_are_enforced_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(billing_catalog.fees_waived())
            self.assertFalse(billing_service.fee_satisfied(None, "u1", payments.AVAILABILITY, "s1"))

    def test_disabling_fees_entitles_everything(self):
        with mock.patch.dict(os.environ, {"DHASHU_FEES_WAIVED": "1"}):
            self.assertTrue(billing_catalog.fees_waived())
            self.assertTrue(billing_service.fee_satisfied(None, "u1", payments.AGREEMENT, "anything"))

    def test_the_off_switch_accepts_the_usual_spellings(self):
        for value in ("0", "false", "no", "off", "OFF", " False "):
            with mock.patch.dict(os.environ, {"DHASHU_FEES_WAIVED": value, "PAYMENTS_ENABLED": "0"}):
                self.assertFalse(billing_catalog.fees_waived(), value)
                self.assertFalse(billing_service.fee_satisfied(None, "u1", payments.AVAILABILITY, "s1"))

    def test_the_explicit_waiver_accepts_true_spellings(self):
        for value in ("1", "true", "yes", "on", " TRUE "):
            with mock.patch.dict(os.environ, {"DHASHU_FEES_WAIVED": value}):
                self.assertTrue(billing_catalog.fees_waived(), value)

    def test_an_invalid_waiver_setting_refuses_startup(self):
        for value in ("maybe", "2", "false;true"):
            with self.assertRaises(RuntimeError):
                billing_catalog.startup_check({"DHASHU_FEES_WAIVED": value})

    def test_live_billing_cannot_boot_with_fees_waived(self):
        with self.assertRaises(RuntimeError):
            billing_catalog.startup_check({'DHASHU_BILLING_MODE':'live','DHASHU_FEES_WAIVED':'1'})


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
