"""Tests for date_alignment.py — the fields a date needs, asked when there
is a date to need them (2026-09-04).

Two things here are worth more than the validation:

  * `lower_budget` picks the SMALLER of two bands. Averaging or taking the
    higher one commits the person with less money to an evening they did
    not choose, and the bill clause is exactly where that bites.
  * `shared_cuisines` returning nothing is a real answer. An agreement that
    invents an overlap is worse than one that says the venue was picked on
    diet alone.
"""

from __future__ import annotations

import unittest

import date_alignment as da
import locale_defaults
from generate_users import CUISINES, DIETS

BANDS = locale_defaults.budget_bands_for("Chennai")


def _answers(**over):
    return {"budget": BANDS[1], "diet": "Vegetarian", "cuisine": ["Thai", "Italian"], **over}


class FieldTests(unittest.TestCase):
    def test_the_three_fields_are_the_ones_taken_off_the_signup_form(self):
        self.assertEqual(da.FIELDS, ("budget", "diet", "cuisine"))

    def test_every_field_has_a_label_and_a_reason(self):
        for field in da.FIELDS:
            with self.subTest(field=field):
                self.assertTrue(da.LABELS[field])
                self.assertGreater(len(da.BLURBS[field]), 40)

    def test_options_come_from_the_city_where_that_matters(self):
        self.assertEqual(da.options_for("budget", "Chennai"), BANDS)
        self.assertEqual(da.options_for("diet", "Chennai")[0], "Vegetarian")
        self.assertEqual(sorted(da.options_for("cuisine")), sorted(CUISINES))

    def test_an_unknown_field_raises(self):
        with self.assertRaises(ValueError):
            da.options_for("astrology")


class CompletenessTests(unittest.TestCase):
    def test_nothing_answered_means_all_three_outstanding(self):
        self.assertEqual(da.missing({}), list(da.FIELDS))

    def test_an_empty_value_counts_as_unanswered(self):
        self.assertIn("cuisine", da.missing({**_answers(), "cuisine": []}))

    def test_all_three_answered_is_complete(self):
        self.assertTrue(da.is_complete(_answers()))

    def test_a_date_needs_both_halves(self):
        """One person answering does not settle a bill split."""
        self.assertFalse(da.ready_for_pair(_answers(), {}))
        self.assertFalse(da.ready_for_pair({}, _answers()))
        self.assertTrue(da.ready_for_pair(_answers(), _answers()))

    def test_pending_reports_each_side_separately(self):
        pending = da.pending_for_pair(_answers(), {"budget": BANDS[0]})
        self.assertEqual(pending["a"], [])
        self.assertEqual(pending["b"], ["diet", "cuisine"])


class ValidationTests(unittest.TestCase):
    def test_all_three_are_required_here_unlike_at_signup(self):
        for field in da.FIELDS:
            with self.subTest(field=field):
                form = _answers()
                form[field] = "" if field != "cuisine" else []
                self.assertFalse(da.validate(form, "Chennai")["ok"])

    def test_a_valid_answer_comes_back_shaped_like_stats(self):
        result = da.validate(_answers(), "Chennai")
        self.assertTrue(result["ok"])
        self.assertEqual(sorted(result["stats"]), ["budget", "cuisine", "diet"])
        self.assertEqual(result["stats"]["cuisine"], ["Italian", "Thai"])

    def test_a_band_from_another_currency_is_refused(self):
        self.assertFalse(da.validate(_answers(budget="$$ · 20 – 50"), "Chennai")["ok"])

    def test_an_invented_diet_is_refused(self):
        self.assertFalse(da.validate(_answers(diet="Breatharian"), "Chennai")["ok"])

    def test_a_single_cuisine_posted_as_a_string_still_works(self):
        """Flask hands back a bare string when only one box is ticked."""
        result = da.validate(_answers(cuisine="Thai"), "Chennai")
        self.assertTrue(result["ok"])
        self.assertEqual(result["stats"]["cuisine"], ["Thai"])

    def test_cuisines_outside_the_list_are_dropped_not_stored(self):
        result = da.validate(_answers(cuisine=["Thai", "Martian"]), "Chennai")
        self.assertEqual(result["stats"]["cuisine"], ["Thai"])


class BudgetReconciliationTests(unittest.TestCase):
    """The fix for a clause that used to assert a band neither party chose."""

    def test_the_lower_band_wins(self):
        self.assertEqual(da.lower_budget(BANDS[3], BANDS[1]), BANDS[1])
        self.assertEqual(da.lower_budget(BANDS[1], BANDS[3]), BANDS[1])

    def test_two_equal_bands_stay_put(self):
        self.assertEqual(da.lower_budget(BANDS[2], BANDS[2]), BANDS[2])

    def test_one_side_missing_falls_back_to_the_side_that_answered(self):
        self.assertEqual(da.lower_budget(None, BANDS[2]), BANDS[2])
        self.assertEqual(da.lower_budget(BANDS[2], None), BANDS[2])

    def test_neither_side_answering_produces_nothing_rather_than_a_default(self):
        """A default here is how the bill clause came to claim something
        that was never declared."""
        self.assertIsNone(da.lower_budget(None, None))

    def test_a_band_that_is_not_an_option_is_ignored(self):
        self.assertEqual(da.lower_budget("about 1500", BANDS[2]), BANDS[2])


class CuisineOverlapTests(unittest.TestCase):
    def test_the_overlap_is_what_both_named(self):
        self.assertEqual(da.shared_cuisines(["Thai", "Italian"], ["Italian", "Japanese"]), ["Italian"])

    def test_no_overlap_is_a_real_answer_not_an_error(self):
        self.assertEqual(da.shared_cuisines(["Thai"], ["Mexican"]), [])

    def test_a_missing_side_produces_no_overlap(self):
        self.assertEqual(da.shared_cuisines(None, ["Thai"]), [])

    def test_the_result_is_ordered_so_the_venue_pick_is_reproducible(self):
        self.assertEqual(da.shared_cuisines(["Thai", "Italian", "Japanese"],
                                            ["Japanese", "Italian", "Thai"]),
                         ["Italian", "Japanese", "Thai"])


if __name__ == "__main__":
    unittest.main()
