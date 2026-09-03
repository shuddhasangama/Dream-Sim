"""Tests for generate_users.py."""

from __future__ import annotations

import unittest
from collections import Counter

from generate_users import (
    AGE_BANDS,
    BGV_STATUSES,
    CITIES,
    COHABIT_FOCUS,
    ETHNICITIES,
    GENDERS,
    INTIMACY_KINDS,
    RESTAURANT_BUDGETS,
    VISION_KEYS,
    generate_users,
)


class ReproducibilityTests(unittest.TestCase):
    def test_same_seed_reproduces(self) -> None:
        self.assertEqual(generate_users(50, seed=7), generate_users(50, seed=7))

    def test_different_seed_differs(self) -> None:
        self.assertNotEqual(generate_users(50, seed=7), generate_users(50, seed=8))


class ShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.users = generate_users(300, seed=42)

    def test_produces_requested_count(self) -> None:
        self.assertEqual(len(self.users), 300)

    def test_ids_unique(self) -> None:
        ids = [u["user_id"] for u in self.users]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_user_has_at_least_two_visions(self) -> None:
        for u in self.users:
            self.assertGreaterEqual(len(u["visions"]), 2, u["user_id"])
            keys = [v["key"] for v in u["visions"]]
            self.assertEqual(len(keys), len(set(keys)), "vision keys must not repeat")
            for key in keys:
                self.assertIn(key, VISION_KEYS)

    def test_intimacy_is_always_present_with_one_or_two_kinds(self) -> None:
        for u in self.users:
            by_key = {v["key"]: v for v in u["visions"]}
            self.assertIn("Intimacy", by_key, u["user_id"])
            kinds = by_key["Intimacy"]["stance"]
            self.assertTrue(1 <= len(kinds) <= 2, u["user_id"])
            self.assertEqual(kinds, sorted(set(kinds)), u["user_id"])
            for kind in kinds:
                self.assertIn(kind, INTIMACY_KINDS)

    def test_intimacy_kinds_never_include_sexual(self) -> None:
        # Removed at the user's request (2026-08-28) — only Emotional and
        # Physical remain.
        for u in self.users:
            kinds = next(v["stance"] for v in u["visions"] if v["key"] == "Intimacy")
            self.assertNotIn("Sexual", kinds, u["user_id"])
        self.assertNotIn("Sexual", INTIMACY_KINDS)

    def test_at_least_one_of_kids_cohabitate_travel_is_present(self) -> None:
        for u in self.users:
            keys = {v["key"] for v in u["visions"]}
            self.assertTrue(keys & {"Kids", "Cohabitate", "Travel together"}, u["user_id"])

    def test_kids_requires_physical_intimacy(self) -> None:
        # 2026-08-28: "Kids cannot be selected if Intimacy - Physical is
        # not selected."
        for u in self.users:
            by_key = {v["key"]: v for v in u["visions"]}
            if "Kids" in by_key:
                self.assertIn("Physical", by_key["Intimacy"]["stance"], u["user_id"])

    def test_kids_and_travel_have_no_stance_at_signup(self) -> None:
        # Kids is deferred to the /road/vision step once the couple reaches
        # Relationship — not decided at Dating signup (see
        # generate_users.py's KIDS_STANCES comment). Travel together never
        # carries a detail at all.
        for u in self.users:
            for v in u["visions"]:
                if v["key"] in ("Kids", "Travel together"):
                    self.assertIsNone(v["stance"], u["user_id"])

    def test_cohabitate_carries_its_focus_from_signup(self) -> None:
        # Revised 2026-09-03: choosing to cohabit without saying whether
        # you mean chores, expenses or both says almost nothing, so the
        # focus is captured at signup rather than deferred.
        for u in self.users:
            for v in u["visions"]:
                if v["key"] == "Cohabitate":
                    self.assertIsInstance(v["stance"], list, u["user_id"])
                    self.assertTrue(1 <= len(v["stance"]) <= 2, u["user_id"])
                    self.assertEqual(v["stance"], sorted(set(v["stance"])), u["user_id"])
                    for focus in v["stance"]:
                        self.assertIn(focus, COHABIT_FOCUS, u["user_id"])

    def test_every_user_has_required_stats(self) -> None:
        for u in self.users:
            stats = u["stats"]
            for field in ("age", "height_cm", "weight_kg", "waist_in", "income_band", "budget", "ethnicity", "diet", "education", "nationality", "religion"):
                self.assertIn(field, stats, u["user_id"])
            self.assertTrue(18 <= stats["age"] <= 60)
            self.assertTrue(140 <= stats["height_cm"] <= 210)
            self.assertTrue(40 <= stats["weight_kg"] <= 150)
            self.assertTrue(20 <= stats["waist_in"] <= 55)

    def test_preferences_match_reach_input_contract_shape(self) -> None:
        # Extends docs/agent-1-reach.pdf §3's documented shape:
        # preferences.fixed.dealbreakers, preferences.adjustable.{age,
        # height_cm,weight_kg,waist_in,distance_km,nationality,religion} —
        # every numeric lever is a [min, max] range (see generate_users.py's
        # module docstring for why this diverges from the PDF's single
        # height_min_cm threshold).
        range_fields = ("age", "height_cm", "weight_kg", "waist_in", "distance_km")
        for u in self.users:
            prefs = u["preferences"]
            self.assertIn("dealbreakers", prefs["fixed"])
            adj = prefs["adjustable"]
            for field in (*range_fields, "nationality", "religion"):
                self.assertIn(field, adj, u["user_id"])
            for field in range_fields:
                self.assertEqual(len(adj[field]), 2, (u["user_id"], field))
                self.assertLessEqual(adj[field][0], adj[field][1], (u["user_id"], field))
            self.assertGreaterEqual(adj["distance_km"][0], 0)

    def test_every_user_has_a_bgv_status(self) -> None:
        for u in self.users:
            self.assertIn(u["bgv_status"], BGV_STATUSES, u["user_id"])

    def test_age_falls_within_its_declared_band(self) -> None:
        bands = dict(zip((f"{lo}-{hi}" for lo, hi in AGE_BANDS), AGE_BANDS))
        for u in self.users:
            lo, hi = bands[u["age_band"]]
            self.assertTrue(lo <= u["stats"]["age"] <= hi, u["user_id"])


class NoAppearanceFieldsTests(unittest.TestCase):
    """Mirrors REACH's own hard boundary: "Appearance/skin-tone data is
    absent from the input schema entirely" (docs/agent-1-reach.pdf §2)."""

    FORBIDDEN_SUBSTRINGS = ("appearance", "skin", "complexion", "race", "ethnic")

    # `ethnicity` was added 2026-09-03 at the user's request. It is exempt
    # from the substring ban for two specific reasons, and the ban is kept
    # otherwise intact so that any OTHER ethnic-* key still fails here:
    #   1. it is self-declared, never inferred — REACH's boundary is about
    #      appearance and skin-tone data, which this is not; and
    #   2. it is not a matching lever. See test_ethnicity_is_not_a_matching
    #      _filter below, which is the assertion that actually matters.
    EXEMPT_KEYS = {"ethnicity"}

    def test_no_appearance_or_skin_tone_keys(self) -> None:
        users = generate_users(20, seed=1)

        def walk(value: object, path: str, offending: list[str]) -> None:
            if isinstance(value, dict):
                for k, v in value.items():
                    key_lower = str(k).lower()
                    if (
                        key_lower not in NoAppearanceFieldsTests.EXEMPT_KEYS
                        and any(bad in key_lower for bad in NoAppearanceFieldsTests.FORBIDDEN_SUBSTRINGS)
                    ):
                        offending.append(f"{path}.{k}")
                    walk(v, f"{path}.{k}", offending)
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    walk(v, f"{path}[{i}]", offending)

        offending: list[str] = []
        for u in users:
            walk(u, u["user_id"], offending)
        self.assertEqual(offending, [])


    def test_ethnicity_is_not_a_matching_filter(self) -> None:
        """Declaring your own descent and screening other people by theirs
        are different products. Only the first was asked for, so ethnicity
        must never appear among the adjustable REACH levers."""
        for u in generate_users(20, seed=2):
            self.assertNotIn("ethnicity", u["preferences"]["adjustable"])
            self.assertNotIn("ethnicity", u["preferences"]["fixed"])
            for tag in u["preferences"]["fixed"]["dealbreakers"]:
                self.assertNotIn("ethnic", tag.lower())

    def test_prefer_not_to_say_is_a_real_ethnicity_value(self) -> None:
        self.assertIn("Prefer not to say", ETHNICITIES)


class DistributionTests(unittest.TestCase):
    """Statistical sanity checks, not exact-value assertions — confirms the
    generator draws from weighted/mixture distributions rather than uniform
    ones, using a large sample and generous tolerances."""

    def setUp(self) -> None:
        self.users = generate_users(4000, seed=123)

    def test_cities_are_not_uniform(self) -> None:
        counts = Counter(u["city"] for u in self.users)
        self.assertEqual(set(counts), set(CITIES))
        # Kolkata (lowest weight) should be visibly smaller than Mumbai (highest weight)
        self.assertLess(counts["Kolkata"], counts["Mumbai"])

    def test_age_bands_are_not_uniform(self) -> None:
        counts = Counter(u["age_band"] for u in self.users)
        youngest = counts["28-34"]
        oldest = counts["42-48"]
        self.assertGreater(youngest, oldest)

    def test_genders_present(self) -> None:
        counts = Counter(u["gender"] for u in self.users)
        self.assertEqual(set(counts), set(GENDERS))

    def test_most_distance_filters_are_moderate_a_minority_are_narrow(self) -> None:
        distance_maxes = [u["preferences"]["adjustable"]["distance_km"][1] for u in self.users]
        # The narrow mixture component tops out at 9km; the moderate one
        # starts at 8km, so <=9 slightly over-counts narrow draws — still a
        # clean minority-vs-majority check with real headroom either side.
        narrow_fraction = sum(1 for d in distance_maxes if d <= 9) / len(distance_maxes)
        self.assertGreater(narrow_fraction, 0.10)
        self.assertLess(narrow_fraction, 0.40)

    def test_most_distance_filters_have_zero_minimum_a_minority_want_a_buffer(self) -> None:
        distance_mins = [u["preferences"]["adjustable"]["distance_km"][0] for u in self.users]
        zero_fraction = sum(1 for d in distance_mins if d == 0) / len(distance_mins)
        self.assertGreater(zero_fraction, 0.5)
        self.assertTrue(any(d > 0 for d in distance_mins))

    def test_narrowest_nationality_and_religion_options_are_the_majority(self) -> None:
        nat_narrow = sum(1 for u in self.users if u["preferences"]["adjustable"]["nationality"] == ["IN"])
        rel_narrow = sum(1 for u in self.users if u["preferences"]["adjustable"]["religion"] == ["same"])
        self.assertGreater(nat_narrow / len(self.users), 0.5)
        self.assertGreater(rel_narrow / len(self.users), 0.5)

    def test_verified_bgv_is_the_majority_but_other_lanes_exist(self) -> None:
        # Lane A ("verified") needs real depth for Dating to be testable at
        # all, but Lane B (every other status) must exist too, or the
        # two-lane gating (docs/dating-stage-spec.md §2) is untestable.
        counts = Counter(u["bgv_status"] for u in self.users)
        self.assertGreater(counts["verified"] / len(self.users), 0.5)
        self.assertTrue(set(counts) - {"verified"})


if __name__ == "__main__":
    unittest.main()
