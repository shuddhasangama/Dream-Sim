"""Tests for demo.py — the walkthrough scaffolding (Segment C).

The load-bearing test here is PartnerPairingTests: the demo partner must
satisfy the REAL matching rules, not a relaxed copy of them. If
matching.fits_filters ever changes, these fail loudly rather than the
walkthrough quietly seeding a partner who never appears as a match.
"""

from __future__ import annotations

import itertools
import os
import random
import unittest
from unittest import mock

import clock as clock_module
import demo
import matching
import onboarding
from generate_users import (
    CITIES,
    EDUCATION,
    ETHNICITIES,
    OWN_RELIGIONS,
    PROFESSIONS,
    RESTAURANT_BUDGETS,
    from_user_row,
    generate_users,
)


def _self_registered(city, gender, religion, diet, rng):
    """A user created the way onboarding.py creates them — which is the
    only population the demo partner is promised to work for."""
    stats = onboarding.validate_stats({
        "age": str(rng.randint(24, 46)), "height_cm": str(rng.randint(150, 195)),
        "weight_kg": str(rng.randint(45, 95)), "waist_in": str(rng.randint(26, 40)),
        "salary": str(rng.randint(400000, 9000000)),
        "budget": RESTAURANT_BUDGETS[rng.randrange(len(RESTAURANT_BUDGETS))],
        "ethnicity": ETHNICITIES[rng.randrange(len(ETHNICITIES))],
        "diet": diet, "cuisine": ["South Indian"],
        "smoking": "Never", "drinking": "Socially", "fitness_routine": "Occasional",
        "education": EDUCATION[rng.randrange(len(EDUCATION))],
        "profession": PROFESSIONS[rng.randrange(len(PROFESSIONS))],
        "marital_history": "Never married", "nationality": "IN", "religion": religion,
        "languages": ["English"], "city": city, "gender": gender,
    })["stats"]
    row = onboarding.build_user_row(
        user_id=onboarding.new_user_id(), city=city, gender=gender, stats=stats,
        visions=onboarding.build_visions(["Emotional", "Physical"], ["Kids", "Cohabitate"], ["Chores split"]),
        activities={a: "good" for a in onboarding.ACTIVITIES[:4]},
    )
    return from_user_row(row)


class ClockTests(unittest.TestCase):
    def setUp(self):
        self.start = clock_module.SimulationClock.at(3, "Mon", 12)

    def test_each_named_step_moves_the_clock_forward(self):
        for step in demo.STEP_HOURS:
            moved = demo.advance(self.start, step)
            self.assertGreater((moved.week, moved.day_index, moved.hour),
                               (self.start.week, self.start.day_index, self.start.hour), step)

    def test_next_day_lands_on_the_next_day(self):
        self.assertEqual(demo.advance(self.start, "day").day, "Tue")

    def test_next_week_lands_in_the_next_week_on_the_same_day(self):
        moved = demo.advance(self.start, "week")
        self.assertEqual(moved.week, self.start.week + 1)
        self.assertEqual(moved.day, self.start.day)

    def test_walking_a_week_a_day_at_a_time_matches_one_week_step(self):
        stepwise = self.start
        for _ in range(7):
            stepwise = demo.advance(stepwise, "day")
        self.assertEqual(str(stepwise), str(demo.advance(self.start, "week")))

    def test_an_unknown_step_raises_rather_than_silently_doing_nothing(self):
        with self.assertRaises(ValueError):
            demo.advance(self.start, "fortnight")

    def test_the_bar_reports_the_current_phase(self):
        view = demo.clock_view(self.start)
        self.assertEqual(view["week"], 3)
        self.assertEqual(view["day"], "Mon")
        self.assertTrue(view["phase"])
        self.assertEqual([s["key"] for s in view["steps"]], list(demo.STEP_HOURS))


class SwitchTests(unittest.TestCase):
    def test_demo_mode_is_on_by_default(self):
        """A walkthrough that needs a hidden flag set is one nobody runs."""
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(demo.is_enabled())

    def test_it_can_be_turned_off(self):
        for value in ("0", "false", "no", "off"):
            with mock.patch.dict(os.environ, {"DEMO_MODE": value}):
                self.assertFalse(demo.is_enabled(), value)


class PartnerPairingTests(unittest.TestCase):
    """The load-bearing tests. The partner is built to SATISFY the real
    matching rules, never to bypass them."""

    def test_every_self_registered_user_gets_a_working_partner(self):
        rng = random.Random(7)
        failures = []
        for city, gender, religion, diet in itertools.product(
            CITIES, ["male", "female"], OWN_RELIGIONS, ["Vegetarian", "Everything"]
        ):
            user = _self_registered(city, gender, religion, diet, rng)
            partner = demo.build_partner_for(user, demo.partner_id_for(user["user_id"]))
            checks = demo.verify_pairing(user, partner)
            if not all(checks.values()):
                failures.append((city, gender, religion, diet, checks))
        self.assertEqual(failures, [], f"{len(failures)} self-registered users had no working partner")

    def test_the_pairing_uses_the_real_matching_function(self):
        """Guards against the partner being validated by a relaxed copy of
        the rules that drifts away from matching.py."""
        user = _self_registered("Pune", "male", "Hindu", "Everything", random.Random(1))
        partner = demo.build_partner_for(user, "dp_x")
        self.assertEqual(
            demo.verify_pairing(user, partner)["a_accepts_b"],
            matching.fits_filters(user, partner),
        )

    def test_the_partner_is_the_opposite_gender(self):
        for gender in ("male", "female"):
            user = _self_registered("Delhi", gender, "Hindu", "Everything", random.Random(2))
            partner = demo.build_partner_for(user, "dp_x")
            self.assertNotEqual(partner["gender"], gender)

    def test_a_veg_only_dealbreaker_is_honoured(self):
        user = _self_registered("Mumbai", "male", "Hindu", "Everything", random.Random(3))
        user["preferences"]["fixed"]["dealbreakers"] = ["veg_only"]
        partner = demo.build_partner_for(user, "dp_x")
        self.assertIn(partner["stats"]["diet"], ("Vegetarian", "Vegan", "Jain"))
        self.assertTrue(matching.fits_filters(user, partner))

    def test_a_no_kids_dealbreaker_is_honoured(self):
        user = _self_registered("Chennai", "female", "Hindu", "Everything", random.Random(4))
        user["preferences"]["fixed"]["dealbreakers"] = ["no_kids_wanted"]
        partner = demo.build_partner_for(user, "dp_x")
        self.assertNotIn("Kids", [v["key"] for v in partner["visions"]])
        self.assertTrue(matching.fits_filters(user, partner))

    def test_the_partner_vision_obeys_the_kids_requires_physical_rule(self):
        user = _self_registered("Pune", "male", "Hindu", "Everything", random.Random(5))
        partner = demo.build_partner_for(user, "dp_x")
        by_key = {v["key"]: v["stance"] for v in partner["visions"]}
        if "Kids" in by_key:
            self.assertIn("Physical", by_key["Intimacy"])

    def test_the_partner_carries_every_stat_a_real_user_has(self):
        """The partner mirrors the user's stats rather than listing its
        own, so a field added to generate_users appears here without
        anyone remembering to update demo.py. This is the test that keeps
        that promise."""
        user = _self_registered("Delhi", "male", "Hindu", "Everything", random.Random(6))
        partner = demo.build_partner_for(user, "dp_x")
        self.assertEqual(set(partner["stats"]), set(user["stats"]))
        for field in ("budget", "ethnicity", "cuisine", "smoking", "drinking", "fitness_routine"):
            self.assertIn(field, partner["stats"], field)

    def test_the_partner_matches_the_generated_population_shape(self):
        user = _self_registered("Pune", "female", "Hindu", "Everything", random.Random(9))
        partner = demo.build_partner_for(user, "dp_x")
        self.assertEqual(set(partner["stats"]), set(generate_users(1, seed=3)[0]["stats"]))

    def test_the_partner_is_verified_so_the_walkthrough_can_reach_matching(self):
        user = _self_registered("Delhi", "male", "Hindu", "Everything", random.Random(8))
        self.assertEqual(demo.build_partner_for(user, "dp_x")["bgv_status"], "verified")

    def test_partner_ids_are_deterministic_and_recognisable(self):
        """Re-running the walkthrough reuses one partner instead of
        littering the pool with a new stranger every time."""
        self.assertEqual(demo.partner_id_for("su_abc"), demo.partner_id_for("su_abc"))
        self.assertTrue(demo.is_demo_partner(demo.partner_id_for("su_abc")))
        self.assertFalse(demo.is_demo_partner("u_0042"))


class KnownDistanceLimitationTests(unittest.TestCase):
    """A PRE-EXISTING issue in the simulation, documented here so it is
    tracked rather than rediscovered.

    Distance is modelled city to city, so the only values that exist are
    0 km (same city) or 120 km and up. generate_users gives a minority of
    users a distance MINIMUM between 3 and 12 km — a band no pair can ever
    land in. Those users match nobody at all, and no demo partner can be
    built for them either.

    Self-registered users are unaffected: onboarding.default_preferences
    sets the minimum to 0.
    """

    def test_self_registered_users_never_have_an_impossible_minimum(self):
        prefs = onboarding.default_preferences({"age": 31})
        self.assertEqual(prefs["adjustable"]["distance_km"][0], 0)

    def test_the_gap_between_same_city_and_the_nearest_other_city(self):
        distances = {matching.city_distance_km(a, b) for a in CITIES for b in CITIES}
        self.assertEqual(min(distances), 0)
        self.assertGreater(min(d for d in distances if d > 0), 100)

    def test_seeded_users_with_a_nonzero_minimum_can_match_nobody(self):
        pool = generate_users(200, seed=42)
        stranded = [
            u for u in pool
            if u["preferences"]["adjustable"]["distance_km"][0] > 0
            and not any(matching.fits_filters(u, c) for c in pool if c["user_id"] != u["user_id"])
        ]
        # Documenting the size of the problem, not asserting it is fine.
        self.assertGreater(len(stranded), 0, "if this now passes, the distance model was fixed — delete this test")


if __name__ == "__main__":
    unittest.main()
