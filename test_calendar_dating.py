"""Tests for calendar_dating.py."""

from __future__ import annotations

import unittest

from calendar_dating import DAY_SLOTS, compute_overlap, no_overlap_options, suggest_venue, valid_slots


class ValidSlotsTests(unittest.TestCase):
    def test_friday_has_no_breakfast_or_lunch(self) -> None:
        friday = [s for s in valid_slots() if s[0] == "Fri"]
        self.assertEqual(friday, [("Fri", "coffee"), ("Fri", "dinner")])

    def test_saturday_and_sunday_have_all_four_slots(self) -> None:
        for day in ("Sat", "Sun"):
            slots = [s for s in valid_slots() if s[0] == day]
            self.assertEqual([s[1] for s in slots], ["breakfast", "lunch", "coffee", "dinner"])

    def test_only_fri_sat_sun(self) -> None:
        self.assertEqual(set(DAY_SLOTS.keys()), {"Fri", "Sat", "Sun"})


class ComputeOverlapTests(unittest.TestCase):
    def test_finds_common_slots(self) -> None:
        a = [("Fri", "dinner"), ("Sat", "lunch"), ("Sun", "breakfast")]
        b = [("Sat", "lunch"), ("Sun", "breakfast"), ("Sun", "dinner")]
        self.assertEqual(compute_overlap(a, b), [("Sat", "lunch"), ("Sun", "breakfast")])

    def test_empty_when_nothing_in_common(self) -> None:
        a = [("Fri", "coffee")]
        b = [("Sat", "dinner")]
        self.assertEqual(compute_overlap(a, b), [])

    def test_result_is_in_canonical_order_regardless_of_input_order(self) -> None:
        a = [("Sun", "dinner"), ("Fri", "coffee")]
        b = [("Fri", "coffee"), ("Sun", "dinner")]
        self.assertEqual(compute_overlap(a, b), [("Fri", "coffee"), ("Sun", "dinner")])


class SuggestVenueTests(unittest.TestCase):
    def test_matching_diets_get_that_diets_venue(self) -> None:
        result = suggest_venue("Sat", "dinner", "Vegetarian", "Vegetarian")
        self.assertEqual(result["cuisine"], "vegetarian")

    def test_picks_the_stricter_of_two_different_diets(self) -> None:
        result = suggest_venue("Sat", "dinner", "Everything", "Vegan")
        self.assertEqual(result["cuisine"], "vegan")

    def test_jain_is_stricter_than_halal(self) -> None:
        result = suggest_venue("Sat", "dinner", "Jain", "Halal")
        self.assertEqual(result["cuisine"], "Jain")

    def test_unknown_diet_falls_back_to_any(self) -> None:
        result = suggest_venue("Sat", "dinner", "Vegetarian", "SomethingNew")
        self.assertEqual(result["cuisine"], "vegetarian")  # veg is still stricter than the any fallback

    def test_carries_day_and_meal_slot_through(self) -> None:
        result = suggest_venue("Sun", "breakfast", "Everything", "Everything")
        self.assertEqual(result["day"], "Sun")
        self.assertEqual(result["meal_slot"], "breakfast")


class NoOverlapOptionsTests(unittest.TestCase):
    def test_offers_next_weekend_and_pool_return(self) -> None:
        options = no_overlap_options(week=4)
        self.assertEqual(options["next_weekend_week"], 5)
        self.assertTrue(options["return_to_pool"])


if __name__ == "__main__":
    unittest.main()
