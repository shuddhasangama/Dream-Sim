"""Tests for bgv.py — background verification (Segment B).

The assertions that matter most are the ones about the account-level
roll-up: User.bgv_status is what matching.py gates Lane A on, so a wrong
aggregate silently puts an unverified person into the pool.
"""

from __future__ import annotations

import unittest

import bgv


def _all(status: str) -> dict[str, str]:
    return {key: status for key in bgv.FIELD_KEYS}


class FieldSetTests(unittest.TestCase):
    def test_the_four_fields_are_age_nationality_profession_bracket(self):
        self.assertEqual(bgv.FIELD_KEYS, ["age", "nationality", "profession", "salary_bracket"])

    def test_the_raw_salary_is_never_verified(self):
        """Revised 2026-09-03. A person declares a salary in Stats so the
        app can derive a band; the verifier confirms the BAND and never
        sees the number. Smaller disclosure, same result."""
        self.assertNotIn("salary", bgv.FIELD_KEYS)
        self.assertIn("salary_bracket", bgv.FIELD_KEYS)

    def test_nothing_is_derived_any_more(self):
        self.assertEqual(bgv.DERIVED_FROM, {})

    def test_missing_rows_default_to_pending_rather_than_raising(self):
        """A field added to FIELDS later must not break an account that
        predates it."""
        statuses = bgv.statuses_from_rows([{"field": "age", "status": bgv.VERIFIED}])
        self.assertEqual(statuses["age"], bgv.VERIFIED)
        self.assertEqual(statuses["nationality"], bgv.PENDING)
        self.assertEqual(set(statuses), set(bgv.FIELD_KEYS))

    def test_unknown_fields_in_the_table_are_ignored(self):
        statuses = bgv.statuses_from_rows([{"field": "shoe_size", "status": bgv.VERIFIED}])
        self.assertNotIn("shoe_size", statuses)


class DerivationTests(unittest.TestCase):
    """No field derives from another now that raw salary is gone. These
    keep the machinery honest so re-introducing a derived field is a
    one-line change rather than a rediscovery."""

    def test_resolving_derived_is_the_identity_today(self):
        statuses = {**_all(bgv.PENDING), "age": bgv.VERIFIED}
        self.assertEqual(bgv.resolve_derived(statuses), statuses)

    def test_the_bracket_is_now_checked_on_its_own(self):
        statuses = {**_all(bgv.PENDING), "salary_bracket": bgv.VERIFIED}
        self.assertEqual(bgv.resolve_derived(statuses)["salary_bracket"], bgv.VERIFIED)


class AggregateTests(unittest.TestCase):
    def test_nothing_started_is_declared(self):
        self.assertEqual(bgv.aggregate_status(_all(bgv.PENDING)), bgv.DECLARED)

    def test_anything_in_review_is_pending(self):
        statuses = {**_all(bgv.PENDING), "age": bgv.IN_REVIEW}
        self.assertEqual(bgv.aggregate_status(statuses), bgv.ACCOUNT_PENDING)

    def test_all_verified_is_verified(self):
        self.assertEqual(bgv.aggregate_status(_all(bgv.VERIFIED)), bgv.ACCOUNT_VERIFIED)

    def test_some_verified_some_failed_is_partially_verified(self):
        statuses = {**_all(bgv.VERIFIED), "salary_bracket": bgv.FAILED}
        self.assertEqual(bgv.aggregate_status(statuses), bgv.PARTIALLY_VERIFIED)

    def test_everything_failed_is_unverifiable(self):
        self.assertEqual(bgv.aggregate_status(_all(bgv.FAILED)), bgv.UNVERIFIABLE)

    def test_one_failed_field_blocks_full_verification(self):
        statuses = {**_all(bgv.VERIFIED), "salary_bracket": bgv.FAILED}
        self.assertFalse(bgv.is_verified(statuses))

    def test_every_aggregate_is_a_valid_user_bgv_status(self):
        """These must stay inside the User.bgv_status CHECK constraint, or
        the insert fails at runtime rather than here."""
        allowed = {"declared", "pending", "verified", "partially_verified", "unverifiable"}
        seen = set()
        for a in bgv.FIELD_STATUSES:
            for b in bgv.FIELD_STATUSES:
                seen.add(bgv.aggregate_status({**_all(a), "age": b}))
        self.assertTrue(seen <= allowed, seen - allowed)


class ReviewFlowTests(unittest.TestCase):
    def test_starting_review_moves_pending_fields_to_in_review(self):
        statuses = bgv.start_review(_all(bgv.PENDING))
        self.assertTrue(all(v == bgv.IN_REVIEW for v in statuses.values()))

    def test_starting_review_retries_failed_fields(self):
        """A retry is the whole point of an appeal."""
        statuses = bgv.start_review({**_all(bgv.VERIFIED), "salary_bracket": bgv.FAILED})
        self.assertEqual(statuses["salary_bracket"], bgv.IN_REVIEW)

    def test_starting_review_does_not_re_check_verified_fields(self):
        statuses = bgv.start_review(_all(bgv.VERIFIED))
        self.assertTrue(all(v == bgv.VERIFIED for v in statuses.values()))


class ProviderStubTests(unittest.TestCase):
    def test_all_pass_verifies_everything_in_review(self):
        statuses = bgv.simulate_provider_callback(_all(bgv.IN_REVIEW), "all_pass")
        self.assertTrue(bgv.is_verified(statuses))

    def test_bracket_fails_leaves_the_account_partially_verified(self):
        statuses = bgv.simulate_provider_callback(_all(bgv.IN_REVIEW), "bracket_fails")
        self.assertEqual(statuses["salary_bracket"], bgv.FAILED)
        self.assertEqual(statuses["age"], bgv.VERIFIED)
        self.assertEqual(bgv.aggregate_status(statuses), bgv.PARTIALLY_VERIFIED)

    def test_all_fail_is_unverifiable(self):
        statuses = bgv.simulate_provider_callback(_all(bgv.IN_REVIEW), "all_fail")
        self.assertEqual(bgv.aggregate_status(statuses), bgv.UNVERIFIABLE)

    def test_fields_not_submitted_are_not_decided_for_the_user(self):
        statuses = bgv.simulate_provider_callback(_all(bgv.PENDING), "all_pass")
        self.assertTrue(all(v == bgv.PENDING for v in statuses.values()))

    def test_an_unknown_outcome_raises_rather_than_guessing(self):
        with self.assertRaises(ValueError):
            bgv.simulate_provider_callback(_all(bgv.IN_REVIEW), "probably_fine")


class PromotionTests(unittest.TestCase):
    def test_verification_promotes_onboarding_to_dating(self):
        self.assertEqual(bgv.promotion_for("onboarding", _all(bgv.VERIFIED)), "dating")

    def test_unverified_users_are_not_promoted(self):
        for status in (bgv.PENDING, bgv.IN_REVIEW, bgv.FAILED):
            self.assertIsNone(bgv.promotion_for("onboarding", _all(status)), status)

    def test_promotion_never_touches_a_later_stage(self):
        """Every transition after dating is a couple-level decision that
        goes through journey.advance_stage(). This must never shortcut it."""
        for state in ("dating", "relationship", "engaged", "married", "exiting", "cooloff"):
            self.assertIsNone(bgv.promotion_for(state, _all(bgv.VERIFIED)), state)


class ScreenTests(unittest.TestCase):
    def test_every_field_reports_its_own_status(self):
        rows = {r["key"]: r for r in bgv.field_view({**_all(bgv.IN_REVIEW), "age": bgv.VERIFIED})}
        self.assertEqual(rows["age"]["status_label"], "Verified")
        self.assertEqual(rows["salary_bracket"]["status_label"], "In review")

    def test_every_field_renders_a_label_and_a_reason(self):
        for row in bgv.field_view(_all(bgv.PENDING)):
            self.assertTrue(row["label"])
            self.assertTrue(row["why"])

    def test_the_next_action_never_contradicts_the_status(self):
        cases = {
            bgv.DECLARED: "not_started",
            bgv.ACCOUNT_PENDING: "in_review",
            bgv.ACCOUNT_VERIFIED: "verified",
        }
        self.assertEqual(bgv.next_action(_all(bgv.PENDING))["state"], cases[bgv.DECLARED])
        self.assertEqual(bgv.next_action(_all(bgv.IN_REVIEW))["state"], cases[bgv.ACCOUNT_PENDING])
        self.assertEqual(bgv.next_action(_all(bgv.VERIFIED))["state"], cases[bgv.ACCOUNT_VERIFIED])
        self.assertEqual(bgv.next_action(_all(bgv.FAILED))["state"], "failed")

    def test_a_verified_user_is_offered_nothing_further(self):
        self.assertIsNone(bgv.next_action(_all(bgv.VERIFIED))["cta"])


if __name__ == "__main__":
    unittest.main()
