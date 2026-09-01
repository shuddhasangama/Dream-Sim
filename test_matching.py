"""Tests for matching.py."""

from __future__ import annotations

import copy
import unittest

from generate_users import generate_users
from matching import (
    LEVERS,
    RANGE_LEVERS,
    build_reach_input,
    city_distance_km,
    determine_match_count,
    fits_filters,
    mutual_open,
    reciprocity_counts,
    set_range,
    suggest_range,
    whatif_deltas,
)


def _base_user() -> dict:
    return {
        "user_id": "u_a",
        "city": "Mumbai",
        "gender": "female",
        "age_band": "28-34",
        "bgv_status": "verified",
        "stats": {
            "age": 30,
            "height_cm": 160,
            "weight_kg": 58,
            "waist_in": 30,
            "income_band": "₹₹ · 12L – 25L",
            "diet": "Vegetarian",
            "education": "Bachelor's",
            "nationality": "IN",
            "religion": "Hindu",
        },
        "visions": [
            {"key": "Kids", "stance": "Want kids"},
            {"key": "Cohabitate", "stance": ["Chores split"]},
        ],
        "preferences": {
            "fixed": {"dealbreakers": []},
            "adjustable": {
                "age": [28, 38],
                "height_cm": [165, 190],
                "weight_kg": [60, 90],
                "waist_in": [28, 38],
                "distance_km": [0, 20],
                "nationality": ["IN"],
                "religion": ["same"],
            },
        },
    }


def _candidate(**overrides) -> dict:
    c = {
        "user_id": "u_b",
        "city": "Mumbai",
        "gender": "male",
        "age_band": "28-34",
        "bgv_status": "verified",
        "stats": {
            "age": 32,
            "height_cm": 175,
            "weight_kg": 72,
            "waist_in": 33,
            "income_band": "₹₹ · 12L – 25L",
            "diet": "Everything",
            "education": "Bachelor's",
            "nationality": "IN",
            "religion": "Hindu",
        },
        "visions": [{"key": "Kids", "stance": "Want kids"}],
        "preferences": {
            "fixed": {"dealbreakers": []},
            "adjustable": {
                "age": [26, 36],
                "height_cm": [150, 175],
                "weight_kg": [45, 70],
                "waist_in": [24, 32],
                "distance_km": [0, 20],
                "nationality": ["IN"],
                "religion": ["same"],
            },
        },
    }
    for path, value in overrides.items():
        keys = path.split(".")
        target = c
        for k in keys[:-1]:
            target = target[k]
        target[keys[-1]] = value
    return c


class CityDistanceTests(unittest.TestCase):
    def test_same_city_is_zero(self) -> None:
        self.assertEqual(city_distance_km("Mumbai", "Mumbai"), 0)

    def test_symmetric(self) -> None:
        self.assertEqual(city_distance_km("Delhi", "Pune"), city_distance_km("Pune", "Delhi"))

    def test_different_cities_are_far_apart(self) -> None:
        self.assertGreater(city_distance_km("Delhi", "Chennai"), 100)


class FitsFiltersTests(unittest.TestCase):
    def test_matching_candidate_fits(self) -> None:
        a, b = _base_user(), _candidate()
        self.assertTrue(fits_filters(a, b))

    def test_age_out_of_range_rejected(self) -> None:
        a = _base_user()
        b = _candidate(**{"stats.age": 50})
        self.assertFalse(fits_filters(a, b))

    def test_height_below_range_rejected(self) -> None:
        a = _base_user()  # requires height_cm in [165,190]
        b = _candidate(**{"stats.height_cm": 160})
        self.assertFalse(fits_filters(a, b))

    def test_height_above_range_rejected(self) -> None:
        a = _base_user()
        b = _candidate(**{"stats.height_cm": 200})
        self.assertFalse(fits_filters(a, b))

    def test_weight_out_of_range_rejected(self) -> None:
        a = _base_user()  # requires weight_kg in [60,90]
        b = _candidate(**{"stats.weight_kg": 50})
        self.assertFalse(fits_filters(a, b))

    def test_waist_out_of_range_rejected(self) -> None:
        a = _base_user()  # requires waist_in in [28,38]
        b = _candidate(**{"stats.waist_in": 20})
        self.assertFalse(fits_filters(a, b))

    def test_same_gender_rejected_regardless_of_other_filters(self) -> None:
        # Demo scope: straight matching only, no orientation field yet —
        # a same-gender candidate never fits, even if every other filter
        # (age/height/diet/etc.) would otherwise admit them.
        a = _base_user()
        a["gender"] = "female"
        b = _candidate(**{"stats.age": a["stats"]["age"]})
        b["gender"] = "female"
        b["preferences"]["adjustable"] = copy.deepcopy(a["preferences"]["adjustable"])
        self.assertFalse(fits_filters(a, b))

    def test_too_far_rejected(self) -> None:
        a = _base_user()  # distance_km=[0,20]
        b = _candidate(city="Delhi")
        self.assertFalse(fits_filters(a, b))

    def test_below_minimum_distance_rejected(self) -> None:
        a = _base_user()
        a["preferences"]["adjustable"]["distance_km"] = [500, 2000]  # wants SOME distance
        b = _candidate(city="Mumbai")  # same city as A = 0km, below the minimum
        self.assertFalse(fits_filters(a, b))

    def test_nationality_outside_accepted_set_rejected(self) -> None:
        a = _base_user()  # nationality=["IN"]
        b = _candidate(**{"stats.nationality": "NRI"})
        self.assertFalse(fits_filters(a, b))

    def test_nationality_any_accepts_everyone(self) -> None:
        a = _base_user()
        a["preferences"]["adjustable"]["nationality"] = ["IN", "NRI", "Any"]
        b = _candidate(**{"stats.nationality": "NRI"})
        self.assertTrue(fits_filters(a, b))

    def test_religion_same_requires_own_religion_match(self) -> None:
        a = _base_user()  # own religion=Hindu, wants "same"
        b = _candidate(**{"stats.religion": "Muslim"})
        self.assertFalse(fits_filters(a, b))

    def test_religion_related_accepts_same_family(self) -> None:
        a = _base_user()  # Hindu (dharmic)
        a["preferences"]["adjustable"]["religion"] = ["same", "related"]
        b = _candidate(**{"stats.religion": "Sikh"})  # also dharmic
        self.assertTrue(fits_filters(a, b))

    def test_religion_related_still_rejects_other_family(self) -> None:
        a = _base_user()  # Hindu (dharmic)
        a["preferences"]["adjustable"]["religion"] = ["same", "related"]
        b = _candidate(**{"stats.religion": "Christian"})  # abrahamic
        self.assertFalse(fits_filters(a, b))

    def test_veg_only_dealbreaker(self) -> None:
        a = _base_user()
        a["preferences"]["fixed"]["dealbreakers"] = ["veg_only"]
        fits = _candidate(**{"stats.diet": "Vegetarian"})
        fails = _candidate(**{"stats.diet": "Everything"})
        self.assertTrue(fits_filters(a, fits))
        self.assertFalse(fits_filters(a, fails))

    def test_wants_kids_dealbreaker_uses_vision_presence(self) -> None:
        # Kids has no stance at Dating signup anymore (deferred to
        # /road/vision) — the dealbreaker checks whether "Kids" is one of
        # the candidate's selected visions at all, not its stance.
        a = _base_user()
        a["preferences"]["fixed"]["dealbreakers"] = ["wants_kids"]
        wants = _candidate(visions=[{"key": "Kids", "stance": None}])
        doesnt = _candidate(visions=[{"key": "Travel together", "stance": None}])
        self.assertTrue(fits_filters(a, wants))
        self.assertFalse(fits_filters(a, doesnt))

    def test_no_kids_wanted_dealbreaker_uses_vision_absence(self) -> None:
        a = _base_user()
        a["preferences"]["fixed"]["dealbreakers"] = ["no_kids_wanted"]
        doesnt_want = _candidate(visions=[{"key": "Travel together", "stance": None}])
        wants = _candidate(visions=[{"key": "Kids", "stance": None}])
        self.assertTrue(fits_filters(a, doesnt_want))
        self.assertFalse(fits_filters(a, wants))

    def test_unmodeled_dealbreaker_is_vacuously_satisfied(self) -> None:
        # non_smoker/non_drinker have no backing Stats field in this
        # simulation — documented in matching.py, verified here.
        a = _base_user()
        a["preferences"]["fixed"]["dealbreakers"] = ["non_smoker"]
        b = _candidate()
        self.assertTrue(fits_filters(a, b))


class MutualOpenTests(unittest.TestCase):
    def test_true_when_both_fit(self) -> None:
        a, b = _base_user(), _candidate()
        self.assertTrue(mutual_open(a, b))

    def test_false_when_only_one_direction_fits(self) -> None:
        a = _base_user()
        b = _candidate(**{"preferences.adjustable.height_cm": [300, 320]})  # A can't clear B's bar
        self.assertTrue(fits_filters(a, b))  # B fits A
        self.assertFalse(fits_filters(b, a))  # A does not fit B
        self.assertFalse(mutual_open(a, b))

    def test_symmetric(self) -> None:
        a, b = _base_user(), _candidate()
        self.assertEqual(mutual_open(a, b), mutual_open(b, a))


def _mutual_pool(n: int, prefix: str = "u_c") -> list[dict]:
    """n candidates, all mutually open with _base_user() and each other
    (same shape as _candidate(), distinct ids), all bgv_status='verified'
    by default — a clean pool for determine_match_count()'s sizing tests."""
    pool = []
    for i in range(n):
        c = _candidate(**{"user_id": f"{prefix}_{i}"})
        pool.append(c)
    return pool


class DetermineMatchCountTests(unittest.TestCase):
    def test_zero_when_viewing_user_is_lane_b(self) -> None:
        # docs/dating-stage-spec.md §2: unverified BGV = Lane B, no matches
        # at all — checked before anything else, even a rich honest pool.
        a = _base_user()
        a["bgv_status"] = "pending"
        pool = _mutual_pool(5)
        self.assertEqual(determine_match_count(a, pool, locked_in_ids=set(), recent_match_ids=set()), 0)

    def test_excludes_unverified_candidates(self) -> None:
        a = _base_user()
        pool = _mutual_pool(3)
        pool[0]["bgv_status"] = "declared"
        self.assertEqual(determine_match_count(a, pool, locked_in_ids=set(), recent_match_ids=set()), 2)

    def test_excludes_locked_in_candidates(self) -> None:
        a = _base_user()
        pool = _mutual_pool(3)
        locked = {pool[0]["user_id"]}
        self.assertEqual(determine_match_count(a, pool, locked_in_ids=locked, recent_match_ids=set()), 2)

    def test_excludes_recent_8_week_matches(self) -> None:
        a = _base_user()
        pool = _mutual_pool(3)
        recent = {pool[0]["user_id"], pool[1]["user_id"]}
        self.assertEqual(determine_match_count(a, pool, locked_in_ids=set(), recent_match_ids=recent), 1)

    def test_caps_at_three_even_with_a_larger_honest_pool(self) -> None:
        a = _base_user()
        pool = _mutual_pool(6)
        self.assertEqual(determine_match_count(a, pool, locked_in_ids=set(), recent_match_ids=set()), 3)

    def test_zero_is_a_valid_honest_outcome(self) -> None:
        # No fabricated matches — an empty eligible pool is just zero.
        a = _base_user()
        self.assertEqual(determine_match_count(a, [], locked_in_ids=set(), recent_match_ids=set()), 0)

    def test_only_mutually_open_candidates_count(self) -> None:
        a = _base_user()
        pool = _mutual_pool(2)
        pool[0]["preferences"]["adjustable"]["height_cm"] = [300, 320]  # no longer mutual
        self.assertEqual(determine_match_count(a, pool, locked_in_ids=set(), recent_match_ids=set()), 1)


class ReciprocityCountsTests(unittest.TestCase):
    def test_counts_and_excludes_self(self) -> None:
        a = _base_user()
        pool = [a, _candidate(user_id="u_b1"), _candidate(user_id="u_b2", **{"stats.age": 99})]
        result = reciprocity_counts(a, pool)
        self.assertEqual(result["fits_user_filters"], 1)  # u_b2 fails age
        self.assertEqual(result["mutual_open"], 1)
        self.assertFalse(result["no_realistic_matches"])

    def test_no_realistic_matches_true_when_zero(self) -> None:
        a = _base_user()
        pool = [a, _candidate(**{"stats.age": 99})]
        result = reciprocity_counts(a, pool)
        self.assertEqual(result["mutual_open"], 0)
        self.assertTrue(result["no_realistic_matches"])


class WhatifDeltasTests(unittest.TestCase):
    def test_covers_all_seven_levers(self) -> None:
        a = _base_user()
        pool = [a, _candidate()]
        levers = [e["lever"] for e in whatif_deltas(a, pool)]
        self.assertEqual(levers, LEVERS)
        self.assertEqual(
            set(levers),
            {"age", "height_cm", "weight_kg", "waist_in", "distance_km", "nationality", "religion"},
        )

    def test_nationality_and_religion_marked_sensitive_only(self) -> None:
        a = _base_user()
        pool = [a, _candidate()]
        for entry in whatif_deltas(a, pool):
            if entry["lever"] in ("nationality", "religion"):
                self.assertTrue(entry.get("sensitive"), entry)
            else:
                self.assertNotIn("sensitive", entry)

    def test_never_narrows(self) -> None:
        a = _base_user()
        pool = [a, _candidate()]
        original = copy.deepcopy(a["preferences"]["adjustable"])
        for entry in whatif_deltas(a, pool):
            lever = entry["lever"]
            if lever in RANGE_LEVERS or lever == "distance_km":
                self.assertLessEqual(entry["to"][0], original[lever][0], lever)
                self.assertGreaterEqual(entry["to"][1], original[lever][1], lever)
            elif lever in ("nationality", "religion"):
                self.assertTrue(set(original[lever]).issubset(set(entry["to"])))
        # the input user's own preferences must be untouched
        self.assertEqual(a["preferences"]["adjustable"], original)

    def test_never_touches_dealbreakers(self) -> None:
        a = _base_user()
        a["preferences"]["fixed"]["dealbreakers"] = ["veg_only"]
        pool = [a, _candidate()]
        whatif_deltas(a, pool)
        self.assertEqual(a["preferences"]["fixed"]["dealbreakers"], ["veg_only"])

    def test_deltas_are_never_negative(self) -> None:
        # Widening a single filter can only admit more candidates, never
        # fewer — a hard invariant, checked against a real generated pool.
        pool = generate_users(150, seed=99)
        for user in pool[:30]:
            for entry in whatif_deltas(user, pool):
                self.assertGreaterEqual(entry["delta_mutual_open"], 0, (user["user_id"], entry))

    def test_widest_nationality_tier_widens_no_further(self) -> None:
        a = _base_user()
        a["preferences"]["adjustable"]["nationality"] = ["IN", "NRI", "Any"]
        pool = [a, _candidate()]
        entry = next(e for e in whatif_deltas(a, pool) if e["lever"] == "nationality")
        self.assertEqual(entry["from"], entry["to"])
        self.assertEqual(entry["delta_mutual_open"], 0)


class SetRangeTests(unittest.TestCase):
    def test_sets_exact_bounds(self) -> None:
        a = _base_user()
        updated = set_range(a, "height_cm", 170, 185)
        self.assertEqual(updated["preferences"]["adjustable"]["height_cm"], [170, 185])

    def test_sorts_reversed_bounds(self) -> None:
        a = _base_user()
        updated = set_range(a, "weight_kg", 90, 60)
        self.assertEqual(updated["preferences"]["adjustable"]["weight_kg"], [60, 90])

    def test_can_narrow_unlike_widen(self) -> None:
        # This is the one place narrowing is allowed — the person editing
        # their own filter directly, not REACH suggesting a widen.
        a = _base_user()
        original = [165, 190]
        self.assertEqual(a["preferences"]["adjustable"]["height_cm"], original)
        updated = set_range(a, "height_cm", 170, 175)  # narrower than original
        self.assertEqual(updated["preferences"]["adjustable"]["height_cm"], [170, 175])

    def test_does_not_mutate_input(self) -> None:
        a = _base_user()
        before = copy.deepcopy(a)
        set_range(a, "waist_in", 25, 35)
        self.assertEqual(a, before)

    def test_rejects_sensitive_or_unknown_lever(self) -> None:
        a = _base_user()
        with self.assertRaises(ValueError):
            set_range(a, "religion", 0, 1)
        with self.assertRaises(ValueError):
            set_range(a, "not_a_lever", 0, 1)


class SuggestRangeTests(unittest.TestCase):
    def test_returns_interquartile_range_for_a_gender(self) -> None:
        pool = [
            {"gender": "male", "stats": {"height_cm": h}} for h in [170, 172, 174, 176, 178, 180, 182, 184]
        ]
        lo, hi = suggest_range(pool, "height_cm", gender="male")
        # middle 50% of a uniform 170..184 spread should sit inside it
        self.assertGreaterEqual(lo, 170)
        self.assertLessEqual(hi, 184)
        self.assertLess(lo, hi)

    def test_narrower_percentiles_give_a_narrower_range(self) -> None:
        pool = [{"gender": "male", "stats": {"weight_kg": w}} for w in range(60, 90)]
        wide = suggest_range(pool, "weight_kg", gender="male", lo_percentile=10, hi_percentile=90)
        narrow = suggest_range(pool, "weight_kg", gender="male", lo_percentile=40, hi_percentile=60)
        self.assertGreater(wide[1] - wide[0], narrow[1] - narrow[0])

    def test_empty_filtered_pool_returns_none(self) -> None:
        pool = [{"gender": "male", "stats": {"height_cm": 175}}]
        self.assertIsNone(suggest_range(pool, "height_cm", gender="female"))

    def test_rejects_non_range_lever(self) -> None:
        with self.assertRaises(ValueError):
            suggest_range([], "religion")

    def test_against_a_real_generated_pool(self) -> None:
        pool = generate_users(300, seed=11)
        result = suggest_range(pool, "waist_in", gender="female")
        self.assertIsNotNone(result)
        lo, hi = result
        self.assertLess(lo, hi)
        self.assertTrue(20 <= lo <= 55 and 20 <= hi <= 55)


class BuildReachInputTests(unittest.TestCase):
    def test_matches_section_3_shape(self) -> None:
        a = _base_user()
        pool = [a, _candidate()]
        payload = build_reach_input(a, pool)
        self.assertEqual(
            set(payload.keys()), {"user_id", "phase", "preferences", "reciprocity", "whatif"}
        )
        self.assertEqual(payload["phase"], "searching")
        self.assertEqual(payload["preferences"], a["preferences"])
        self.assertEqual(set(payload["reciprocity"].keys()), {"fits_user_filters", "mutual_open", "no_realistic_matches"})
        self.assertEqual(len(payload["whatif"]), len(LEVERS))


if __name__ == "__main__":
    unittest.main()
