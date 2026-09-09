"""Tests for onboarding.py — the front door (Segment A).

Follows the existing convention: plain unittest, no fixtures, asserting on
the pure functions rather than on Flask. The most important assertions here
are the compatibility ones: a self-registered user must be shaped exactly
like a generated one, or matching/cadence/journey silently misbehave on it.

Run: python -m pytest test_onboarding.py -q
"""

from __future__ import annotations

import json
import re
import unittest

import onboarding

from test_segment_efg_routes import RouteTestCase
from generate_users import (
    COHABIT_FOCUS,
    DRINKING,
    ETHNICITIES,
    FITNESS_ROUTINES,
    INCOME_BANDS,
    NATIONALITY_OPTIONS,
    OTHER_VISION_KEYS,
    RELIGION_OPTIONS,
    RESTAURANT_BUDGETS,
    SMOKING,
    from_user_row,
    generate_users,
)


def _valid_stats() -> dict:
    return {
        "age": "31", "height_cm": "178", "weight_kg": "74", "waist_in": "32",
        "salary": "1800000",
        "budget": [RESTAURANT_BUDGETS[1]], "ethnicity": ["Indian"],
        "diet": "Everything", "cuisine": ["Italian", "Thai"],
        "smoking": "Never", "drinking": "Socially", "fitness_routine": "2-3 times a week",
        "education": "Master's", "profession": "Engineering",
        "marital_history": "Never married", "nationality": "IN", "religion": "Hindu",
        "languages": ["English", "Hindi"],
        "city": "Bangalore", "gender": "male",
    }


class SalaryBracketTests(unittest.TestCase):
    def test_thresholds_land_on_the_generated_bands(self):
        self.assertEqual(onboarding.bracket_for(500_000), INCOME_BANDS[0])
        self.assertEqual(onboarding.bracket_for(1_199_999), INCOME_BANDS[0])
        self.assertEqual(onboarding.bracket_for(1_200_000), INCOME_BANDS[1])
        self.assertEqual(onboarding.bracket_for(2_500_000), INCOME_BANDS[2])
        self.assertEqual(onboarding.bracket_for(5_000_000), INCOME_BANDS[3])
        self.assertEqual(onboarding.bracket_for(90_000_000), INCOME_BANDS[3])

    def test_blank_and_junk_return_none_rather_than_guessing(self):
        for value in (None, "", "   ", "lots", "-1", "0"):
            self.assertIsNone(onboarding.bracket_for(value), value)

    def test_formatted_input_is_accepted(self):
        self.assertEqual(onboarding.bracket_for("₹18,00,000"), INCOME_BANDS[1])


class IdentifierTests(unittest.TestCase):
    def test_either_identifier_alone_is_enough(self):
        self.assertTrue(onboarding.normalise_identifiers("a@b.com", "")["ok"])
        self.assertTrue(onboarding.normalise_identifiers("", "9876543210")["ok"])

    def test_neither_is_refused_with_a_message(self):
        result = onboarding.normalise_identifiers("", "")
        self.assertFalse(result["ok"])
        self.assertIn("email address or a phone number", result["error"])

    def test_malformed_input_is_accepted_but_flagged(self):
        # Case 1 asks for an unvalidated front door: shape is advisory only.
        result = onboarding.normalise_identifiers("not-an-email", "12")
        self.assertTrue(result["ok"])
        self.assertFalse(result["email_looks_valid"])
        self.assertFalse(result["phone_looks_valid"])

    def test_phone_is_reduced_to_digits_and_email_lowercased(self):
        result = onboarding.normalise_identifiers("  Me@Example.COM ", "+91 98765-43210")
        self.assertEqual(result["email"], "me@example.com")
        self.assertEqual(result["phone"], "919876543210")


class VisionRuleTests(unittest.TestCase):
    def test_intimacy_is_mandatory(self):
        result = onboarding.validate_vision([], ["Cohabitate"])
        self.assertFalse(result["ok"])

    def test_at_least_one_other_goal_is_mandatory(self):
        result = onboarding.validate_vision(["Emotional"], [])
        self.assertFalse(result["ok"])

    def test_only_having_kids_naturally_requires_physical_intimacy(self):
        """2026-09-09 (evening), user's rule: "Kids with Surrogacy or
        Adoption doesn't require Physical Intimacy to be Mandatory."

        The rule used to hang off the GOAL, which quietly assumed one
        route to children and made the other two unreachable for anyone
        who had not also ticked Physical."""
        blocked = onboarding.validate_vision(["Emotional"], ["Kids"], None, ["Naturally"])
        self.assertFalse(blocked["ok"])
        self.assertIn("naturally", blocked["error"])

        for route in ("Surrogacy", "Adoption"):
            with self.subTest(route=route):
                got = onboarding.validate_vision(["Emotional"], ["Kids"], None, [route])
                self.assertTrue(got["ok"], got["error"])

        allowed = onboarding.validate_vision(
            ["Emotional", "Physical"], ["Kids"], None, ["Naturally"])
        self.assertTrue(allowed["ok"], allowed["error"])

    def test_unknown_values_are_dropped_not_stored(self):
        result = onboarding.validate_vision(
            ["Emotional", "Telepathic"], ["Travel together", "Yachting"],
            None, None, ["Road trips"])
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["intimacy_kinds"], ["Emotional"])
        self.assertEqual(result["other_keys"], ["Travel together"])

    def test_built_visions_match_the_generated_shape(self):
        visions = onboarding.build_visions(
            ["Physical"], ["Kids", "Travel together"], None, ["Naturally"], ["Road trips"])
        self.assertEqual(visions[0]["key"], "Intimacy")
        self.assertEqual(visions[0]["stance"], ["Physical"])
        by_key = {v["key"]: v["stance"] for v in visions[1:]}
        for key in by_key:
            self.assertIn(key, OTHER_VISION_KEYS)
        # 2026-09-09 (evening): every goal carries detail now.
        self.assertEqual(by_key["Kids"], ["Naturally"])
        self.assertEqual(by_key["Travel together"], ["Road trips"])


class CohabitateFocusTests(unittest.TestCase):
    """Revised 2026-09-03: Cohabitate carries chores / expenses / both from
    signup, because the goal on its own says almost nothing."""

    def test_cohabitate_without_a_focus_is_refused(self):
        result = onboarding.validate_vision(["Physical"], ["Cohabitate"], [])
        self.assertFalse(result["ok"])
        self.assertIn("chores, expenses, or both", result["error"])

    def test_either_focus_alone_is_enough(self):
        for focus in COHABIT_FOCUS:
            self.assertTrue(onboarding.validate_vision(["Physical"], ["Cohabitate"], [focus])["ok"], focus)

    def test_both_focuses_are_allowed(self):
        result = onboarding.validate_vision(["Physical"], ["Cohabitate"], list(COHABIT_FOCUS))
        self.assertTrue(result["ok"])
        self.assertEqual(result["cohabit_focus"], sorted(COHABIT_FOCUS))

    def test_a_focus_now_selects_cohabitate_rather_than_being_discarded(self):
        """REVERSED 2026-09-09 (evening), user's rule: "Ensure that if sub
        options are chose automatically parent option is chosen across all
        Visions."

        This used to assert the opposite — that a focus without its goal
        was thrown away. Ticking "Chores split" and not "Cohabitate" is
        not an incomplete answer, it is an obvious one, and discarding it
        taught people the form was fussy rather than that they had missed
        something."""
        result = onboarding.validate_vision(
            ["Physical"], ["Kids"], ["Chores split"], ["Naturally"])
        self.assertTrue(result["ok"], result["error"])
        self.assertIn("Cohabitate", result["other_keys"])
        self.assertEqual(result["cohabit_focus"], ["Chores split"])
        visions = onboarding.build_visions(
            ["Physical"], ["Kids"], ["Chores split"], ["Naturally"])
        self.assertIn("Cohabitate", [v["key"] for v in visions])

    def test_unknown_focus_values_are_dropped(self):
        result = onboarding.validate_vision(["Physical"], ["Cohabitate"], ["Chores split", "Cooking rota"])
        self.assertEqual(result["cohabit_focus"], ["Chores split"])

    def test_built_cohabitate_stance_is_a_sorted_list(self):
        visions = onboarding.build_visions(
            ["Physical"], ["Cohabitate", "Kids", "Travel together"],
            ["Expenses sharing", "Chores split"], ["Surrogacy", "Adoption"],
        )
        by_key = {v["key"]: v["stance"] for v in visions}
        self.assertEqual(by_key["Cohabitate"], sorted(COHABIT_FOCUS))
        self.assertEqual(by_key["Kids"], ["Adoption", "Surrogacy"])
        self.assertIsNone(by_key["Travel together"])


class KidsRouteTests(unittest.TestCase):
    """2026-09-09, user's rule: "Underneath kids in Vision include 3
    sub-options - 'Naturally', 'Surrogacy', 'Adoption'."

    Same shape as Cohabitate's focus, and for the same reason: two people
    can both want children and mean routes years and lakhs apart."""

    def test_kids_without_a_route_is_refused(self):
        result = onboarding.validate_vision(["Physical"], ["Kids"], None, [])
        self.assertFalse(result["ok"])
        self.assertIn("how you are open to having kids", result["error"])

    def test_any_single_route_is_enough(self):
        for route in onboarding.KIDS_ROUTES:
            with self.subTest(route=route):
                self.assertTrue(
                    onboarding.validate_vision(["Physical"], ["Kids"], None, [route])["ok"])

    def test_all_three_together_are_allowed(self):
        """Not exclusive on purpose — someone open to more than one route
        is exactly who this distinction matters most for."""
        result = onboarding.validate_vision(
            ["Physical"], ["Kids"], None, list(onboarding.KIDS_ROUTES))
        self.assertTrue(result["ok"])
        self.assertEqual(result["kids_route"], sorted(onboarding.KIDS_ROUTES))

    def test_a_route_now_selects_kids_rather_than_being_discarded(self):
        """REVERSED 2026-09-09 (evening) — see the Cohabitate twin above.
        Ticking "Adoption" says you want kids."""
        result = onboarding.validate_vision(
            ["Physical"], ["Travel together"], None, ["Adoption"], ["Road trips"])
        self.assertTrue(result["ok"], result["error"])
        self.assertIn("Kids", result["other_keys"])
        self.assertEqual(result["kids_route"], ["Adoption"])

    def test_unknown_routes_are_dropped(self):
        result = onboarding.validate_vision(
            ["Physical"], ["Kids"], None, ["Adoption", "Cloning"])
        self.assertEqual(result["kids_route"], ["Adoption"])


class TravelStyleTests(unittest.TestCase):
    """2026-09-09 (evening), user's rule: "Also include these multiple
    selectable sub options under Travel Together - Relaxing escapes,
    Adventure & outdoors, Culture & cities, Road trips."

    Travel together was the last goal carrying no detail. "We both like
    travelling" hides the same gap Kids and Cohabitate did."""

    def test_the_four_styles_are_offered(self):
        self.assertEqual(onboarding.TRAVEL_STYLES,
                         ["Relaxing escapes", "Adventure & outdoors",
                          "Culture & cities", "Road trips"])

    def test_travel_without_a_style_is_refused(self):
        result = onboarding.validate_vision(["Physical"], ["Travel together"])
        self.assertFalse(result["ok"])
        self.assertIn("what kind of travelling", result["error"])

    def test_any_single_style_is_enough(self):
        for style in onboarding.TRAVEL_STYLES:
            with self.subTest(style=style):
                got = onboarding.validate_vision(
                    ["Physical"], ["Travel together"], None, None, [style])
                self.assertTrue(got["ok"], got["error"])

    def test_several_styles_are_allowed(self):
        result = onboarding.validate_vision(
            ["Physical"], ["Travel together"], None, None, list(onboarding.TRAVEL_STYLES))
        self.assertEqual(result["travel_style"], sorted(onboarding.TRAVEL_STYLES))

    def test_a_style_selects_travel_together(self):
        result = onboarding.validate_vision(["Physical"], [], None, None, ["Road trips"])
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["other_keys"], ["Travel together"])


class ParentSelectionTests(unittest.TestCase):
    """2026-09-09 (evening), user's rule: "Ensure that if sub options are
    chose automatically parent option is chosen across all Visions."

    Across ALL of them — asserted by looping the table rather than by
    three hand-written cases, so a goal added later cannot miss it."""

    def test_every_goal_is_selected_by_any_of_its_own_sub_options(self):
        for goal, options in onboarding.DETAILED_GOALS.items():
            for option in options:
                with self.subTest(goal=goal, option=option):
                    details = {g: [] for g in onboarding.DETAILED_GOALS}
                    details[goal] = [option]
                    self.assertIn(goal, onboarding.selected_goals([], details))

    def test_a_goal_ticked_without_details_is_still_selected(self):
        """Selecting the parent directly has to keep working — this adds a
        way in, it does not replace the obvious one."""
        details = {g: [] for g in onboarding.DETAILED_GOALS}
        self.assertEqual(onboarding.selected_goals(["Kids"], details), ["Kids"])

    def test_nothing_is_selected_by_nothing(self):
        details = {g: [] for g in onboarding.DETAILED_GOALS}
        self.assertEqual(onboarding.selected_goals([], details), [])

    def test_every_goal_has_a_form_field_a_hint_and_a_prompt(self):
        """A goal missing any of the three renders a detail block the
        validator cannot read back."""
        for goal in onboarding.DETAILED_GOALS:
            with self.subTest(goal=goal):
                self.assertIn(goal, onboarding.DETAIL_FIELD)
                self.assertIn(goal, onboarding.DETAIL_HINT)
                self.assertIn(goal, onboarding.DETAIL_PROMPT)

    def test_travel_together_now_carries_detail_too(self):
        """REVERSED 2026-09-09 (evening): it was the last goal taking no
        detail, and "we both like travelling" hides the same gap Kids and
        Cohabitate did."""
        self.assertFalse(onboarding.validate_vision(["Emotional"], ["Travel together"], [])["ok"])
        self.assertTrue(onboarding.validate_vision(
            ["Emotional"], ["Travel together"], None, None, ["Road trips"])["ok"])

    def test_physical_is_required_by_the_route_not_by_the_goal(self):
        """REVERSED 2026-09-09 (evening), user's rule: "Kids with
        Surrogacy or Adoption doesn't require Physical Intimacy to be
        Mandatory"."""
        self.assertFalse(onboarding.validate_vision(
            ["Emotional"], ["Kids"], None, ["Naturally"])["ok"])
        self.assertTrue(onboarding.validate_vision(
            ["Emotional"], ["Kids"], None, ["Surrogacy"])["ok"])


class StatsValidationTests(unittest.TestCase):
    def test_a_complete_form_passes_and_derives_the_band(self):
        result = onboarding.validate_stats(_valid_stats())
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["stats"]["income_band"], INCOME_BANDS[1])
        self.assertEqual(result["stats"]["age"], 31)
        self.assertEqual(result["stats"]["languages"], ["English", "Hindi"])

    def test_every_mandatory_field_is_actually_required(self):
        """2026-09-04, user's rule: five mandatory fields, no more. Salary
        is checked separately because only its derived band is stored."""
        for key in ("age", "education", "nationality", "profession"):
            form = _valid_stats()
            form[key] = ""
            self.assertFalse(onboarding.validate_stats(form)["ok"], key)

    def test_the_five_mandatory_fields_are_the_ones_that_were_asked_for(self):
        self.assertEqual(onboarding.REQUIRED_STAT_KEYS,
                         ["age", "education", "nationality", "profession"])
        self.assertEqual(onboarding.MANDATORY_FIELD_LABELS,
                         ("Age", "Education", "Nationality", "Salary", "Profession"))

    def test_the_five_alone_are_enough_to_register(self):
        """The whole point of the split: a stranger who has not seen a
        single match answers five questions, not seventeen."""
        minimal = {
            "age": "31", "education": "Master's", "nationality": "IN",
            "profession": "Law", "salary": "1800000",
            "city": "Chennai", "gender": "female",
        }
        result = onboarding.validate_stats(minimal)
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(sorted(result["stats"]),
                         ["age", "education", "income_band", "nationality", "profession"])

    def test_an_optional_field_left_blank_is_absent_not_empty(self):
        """Absence is load-bearing — REACH offers a lever only for a stat
        that is actually there, and "" would hand someone a filter they
        never filled in."""
        result = onboarding.validate_stats(_valid_stats() | {"height_cm": ""})
        self.assertTrue(result["ok"])
        self.assertNotIn("height_cm", result["stats"])

    def test_a_nonsense_optional_value_is_still_refused(self):
        """Optional means skippable, not unchecked."""
        self.assertFalse(onboarding.validate_stats(_valid_stats() | {"height_cm": "tall"})["ok"])
        self.assertFalse(onboarding.validate_stats(_valid_stats() | {"religion": "Pastafarian"})["ok"])

    def test_out_of_range_numbers_are_refused(self):
        form = _valid_stats()
        form["height_cm"] = "12"
        self.assertFalse(onboarding.validate_stats(form)["ok"])

    def test_salary_is_required_because_the_band_derives_from_it(self):
        form = _valid_stats()
        form["salary"] = ""
        self.assertFalse(onboarding.validate_stats(form)["ok"])

    def test_stats_keys_match_the_generated_population_exactly(self):
        mine = set(onboarding.validate_stats(_valid_stats())["stats"])
        generated = set(generate_users(1, seed=7)[0]["stats"])
        self.assertEqual(mine, generated)


class MultiSelectStatTests(unittest.TestCase):
    """Cuisine and languages are lists. The route reads them with
    getlist(), because to_dict() keeps only the FIRST value of a repeated
    field — which silently drops every choice but one and looks like the
    user only picked one thing."""

    def test_every_chosen_value_survives(self):
        form = _valid_stats()
        form["cuisine"] = ["Italian", "Thai", "Korean"]
        stats = onboarding.validate_stats(form)["stats"]
        self.assertEqual(stats["cuisine"], ["Italian", "Korean", "Thai"])

    def test_a_single_string_is_accepted_as_one_choice(self):
        form = _valid_stats()
        form["cuisine"] = "Italian"
        self.assertEqual(onboarding.validate_stats(form)["stats"]["cuisine"], ["Italian"])

    def test_each_multi_field_is_mandatory(self):
        for key, label, _opts, _hint in onboarding.MULTI_STATS:
            form = _valid_stats()
            form[key] = []
            result = onboarding.validate_stats(form)
            self.assertFalse(result["ok"], key)
            self.assertIn(label, result["error"], key)

    def test_unknown_values_are_dropped(self):
        form = _valid_stats()
        form["cuisine"] = ["Italian", "Martian"]
        self.assertEqual(onboarding.validate_stats(form)["stats"]["cuisine"], ["Italian"])


class LifestyleStatTests(unittest.TestCase):
    """Smoking, drinking and fitness routine — collected, but OPTIONAL
    since 2026-09-04. Sign-up asks five questions; these are offered
    underneath and skipped without complaint."""

    def test_all_three_are_offered_but_optional(self):
        for key in ("smoking", "drinking", "fitness_routine"):
            form = _valid_stats()
            form[key] = ""
            result = onboarding.validate_stats(form)
            self.assertTrue(result["ok"], key)
            self.assertNotIn(key, result["stats"], f"{key} left blank should be absent, not empty")

    def test_they_offer_the_generated_populations_options(self):
        by_key = {k: opts for k, _, opts in onboarding.OPTIONAL_CHOICE_STATS}
        self.assertEqual(by_key["smoking"], SMOKING)
        self.assertEqual(by_key["drinking"], DRINKING)
        self.assertEqual(by_key["fitness_routine"], FITNESS_ROUTINES)

    def test_smoking_and_drinking_are_not_matching_filters_yet(self):
        """matching.py's non_smoker / non_drinker dealbreakers now HAVE a
        field to check, but wiring them up changes who matches whom across
        the whole pool. That is a product decision — see the note in
        generate_users. This test records that it has not been taken."""
        stats = onboarding.validate_stats(_valid_stats())["stats"]
        adjustable = onboarding.default_preferences(stats)["adjustable"]
        for field in ("smoking", "drinking", "fitness_routine", "cuisine"):
            self.assertNotIn(field, adjustable, field)


class BudgetAndEthnicityTests(unittest.TestCase):
    """Added 2026-09-03."""

    def test_both_fields_are_offered_but_optional(self):
        """Budget moved to the date-alignment set on 2026-09-04 — it only
        means something once there is a bill to split."""
        for key in ("budget", "ethnicity"):
            form = _valid_stats()
            form[key] = ""
            result = onboarding.validate_stats(form)
            self.assertTrue(result["ok"], key)
            self.assertNotIn(key, result["stats"], key)

    def test_budget_is_a_declared_band_not_a_free_number(self):
        form = _valid_stats()
        form["budget"] = "about 1500"
        self.assertFalse(onboarding.validate_stats(form)["ok"])

    def test_budget_is_separate_from_the_salary_bracket(self):
        """Two people can share an income band and still be uncomfortable
        in each other's restaurants — that is the whole point of the field."""
        stats = onboarding.validate_stats(_valid_stats())["stats"]
        self.assertIn("budget", stats)
        self.assertIn("income_band", stats)
        self.assertIsNot(stats["budget"], stats["income_band"])

    def test_prefer_not_to_say_is_accepted_for_ethnicity(self):
        form = _valid_stats()
        form["ethnicity"] = "Prefer not to say"
        result = onboarding.validate_stats(form)
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["stats"]["ethnicity"], ["Prefer not to say"])

    def test_ethnicity_never_becomes_a_matching_filter(self):
        """Declaring your own descent and screening others by theirs are
        different products. Only the first was asked for."""
        stats = onboarding.validate_stats(_valid_stats())["stats"]
        prefs = onboarding.default_preferences(stats)
        self.assertNotIn("ethnicity", prefs["adjustable"])
        self.assertNotIn("budget", prefs["adjustable"])
        self.assertEqual(prefs["fixed"]["dealbreakers"], [])

    def test_offered_options_match_the_generated_population(self):
        by_key = {k: opts for k, _, opts, _hint in onboarding.OPTIONAL_MULTI_STATS}
        import locale_defaults
        self.assertEqual(locale_defaults.budget_bands_for("Chennai"), RESTAURANT_BUDGETS)
        self.assertEqual(by_key["ethnicity"], ETHNICITIES)

    def test_ethnicity_allows_two_but_not_three(self):
        form = _valid_stats()
        form["ethnicity"] = ETHNICITIES[:2]
        self.assertTrue(onboarding.validate_stats(form)["ok"])
        form["ethnicity"] = ETHNICITIES[:3]
        result = onboarding.validate_stats(form)
        self.assertFalse(result["ok"])
        self.assertIn("at most 2", result["error"])

    def test_budget_is_multi_select(self):
        form = _valid_stats()
        form["budget"] = RESTAURANT_BUDGETS[:2]
        result = onboarding.validate_stats(form)
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["stats"]["budget"], RESTAURANT_BUDGETS[:2])


class ActivitySortTests(unittest.TestCase):
    def test_below_the_minimum_is_refused(self):
        result = onboarding.validate_activities({"Cooking": "good", "Yoga": "improve"})
        self.assertFalse(result["ok"])
        self.assertIn(str(onboarding.MIN_SORTED), result["error"])

    def test_at_the_minimum_passes(self):
        picks = {a: "maybe" for a in onboarding.ACTIVITIES[: onboarding.MIN_SORTED]}
        self.assertTrue(onboarding.validate_activities(picks)["ok"])

    def test_unknown_activities_and_buckets_are_dropped(self):
        picks = {a: "good" for a in onboarding.ACTIVITIES[:4]}
        picks["Falconry"] = "good"
        picks["Yoga"] = "brilliant"
        result = onboarding.validate_activities(picks)
        self.assertTrue(result["ok"])
        self.assertNotIn("Falconry", result["activities"])
        self.assertNotIn("Yoga", result["activities"])

    def test_skills_payload_indexes_every_bucket(self):
        skills = onboarding.build_skills({"Cooking": "good", "Salsa": "improve"})
        self.assertEqual(set(skills["by_bucket"]), {b[0] for b in onboarding.BUCKETS})
        self.assertEqual(skills["by_bucket"]["good"], ["Cooking"])
        self.assertEqual(skills["by_bucket"]["no"], [])


class PreferenceCompatibilityTests(unittest.TestCase):
    """The REACH widen levers look the current value up in the canonical
    option lists. An off-list default would make the lever a silent no-op,
    which is the kind of bug that only shows up as 'the button does
    nothing' three weeks later."""

    def test_nationality_default_is_a_canonical_option(self):
        prefs = onboarding.default_preferences({"age": 31})
        self.assertIn(prefs["adjustable"]["nationality"], NATIONALITY_OPTIONS)

    def test_religion_default_is_a_canonical_option(self):
        prefs = onboarding.default_preferences({"age": 31, "religion": "Hindu"})
        self.assertIn(prefs["adjustable"]["religion"], RELIGION_OPTIONS)

    def test_defaults_leave_room_to_widen(self):
        prefs = onboarding.default_preferences({"age": 31, "religion": "Hindu"})
        self.assertLess(NATIONALITY_OPTIONS.index(prefs["adjustable"]["nationality"]), len(NATIONALITY_OPTIONS) - 1)
        self.assertLess(RELIGION_OPTIONS.index(prefs["adjustable"]["religion"]), len(RELIGION_OPTIONS) - 1)

    def test_no_dealbreakers_are_invented_on_the_users_behalf(self):
        self.assertEqual(onboarding.default_preferences({"age": 31})["fixed"]["dealbreakers"], [])

    def test_preference_keys_match_the_generated_population(self):
        """A user who filled everything in gets the generator's full lever
        set. The generated population declares every stat, so this is the
        comparison that has to hold."""
        full = {"age": 31, "height_cm": 170, "weight_kg": 65, "waist_in": 30, "religion": "Hindu"}
        mine = onboarding.default_preferences(full)
        generated = generate_users(1, seed=7)[0]["preferences"]
        self.assertEqual(set(mine), set(generated))
        self.assertEqual(set(mine["adjustable"]), set(generated["adjustable"]))

    def test_a_lever_is_only_created_for_a_stat_that_was_given(self):
        """2026-09-04, user's rule: REACH filters on what you keyed in.
        A height filter belonging to someone who never gave their height
        is a filter that means nothing."""
        sparse = onboarding.default_preferences({"age": 31})["adjustable"]
        self.assertEqual(sorted(sparse), ["age", "distance_km", "nationality"])
        for absent in ("height_cm", "weight_kg", "waist_in", "religion"):
            self.assertNotIn(absent, sparse, absent)

    def test_levers_appear_one_by_one_as_stats_are_filled_in(self):
        stats = {"age": 31}
        for key in ("height_cm", "weight_kg", "waist_in"):
            self.assertNotIn(key, onboarding.default_preferences(stats)["adjustable"])
            stats[key] = 100
            self.assertIn(key, onboarding.default_preferences(stats)["adjustable"])

    def test_distance_is_always_available_because_city_always_is(self):
        """Distance is derived from two cities rather than a stat, and city
        is mandatory — so it is the one lever nobody has to unlock."""
        self.assertIn("distance_km", onboarding.default_preferences({"age": 31})["adjustable"])


class UserRowTests(unittest.TestCase):
    def _row(self):
        return onboarding.build_user_row(
            user_id=onboarding.new_user_id(),
            city="Bangalore",
            gender="male",
            stats=onboarding.validate_stats(_valid_stats())["stats"],
            visions=onboarding.build_visions(["Physical"], ["Kids"], []),
            activities={a: "good" for a in onboarding.ACTIVITIES[:4]},
        )

    def test_the_row_round_trips_through_from_user_row(self):
        """The real compatibility check: everything downstream reads users
        through from_user_row(), so a self-registered row has to survive it."""
        record = from_user_row(self._row())
        self.assertEqual(record["city"], "Bangalore")
        self.assertEqual(record["gender"], "male")
        self.assertEqual(record["age_band"], "28-34")
        self.assertEqual(record["journey_state"], "onboarding")
        self.assertEqual(record["stats"]["income_band"], INCOME_BANDS[1])
        self.assertEqual(record["visions"][0]["key"], "Intimacy")

    def test_a_new_user_starts_in_onboarding_not_dating(self):
        # Reaching the weekly rotation is Segment B's job, after BGV.
        self.assertEqual(self._row()["journey_state"], "onboarding")

    def test_a_new_user_is_not_verified(self):
        self.assertEqual(self._row()["bgv_status"], "declared")

    def test_activity_sort_lands_in_the_previously_unused_skills_column(self):
        skills = json.loads(self._row()["skills_json"])
        self.assertIn("by_bucket", skills)
        self.assertEqual(len(skills["activities"]), 4)

    def test_self_signups_are_distinguishable_from_seeded_users(self):
        """Phase 1 of the roadmap: demo data must be separable from real
        users. One prefix makes that a single WHERE clause."""
        self.assertTrue(onboarding.is_self_signup(self._row()["id"]))
        self.assertFalse(onboarding.is_self_signup("u_0042"))

    def test_ids_are_unique(self):
        self.assertEqual(len({onboarding.new_user_id() for _ in range(500)}), 500)


class AgeBandTests(unittest.TestCase):
    def test_ages_inside_the_generated_span(self):
        self.assertEqual(onboarding.age_band_for(28), "28-34")
        self.assertEqual(onboarding.age_band_for(34), "28-34")
        self.assertEqual(onboarding.age_band_for(35), "35-41")
        self.assertEqual(onboarding.age_band_for(48), "42-48")

    def test_ages_outside_it_clamp_to_the_nearest_band(self):
        self.assertEqual(onboarding.age_band_for(22), "28-34")
        self.assertEqual(onboarding.age_band_for(70), "42-48")


class AccountRowTests(unittest.TestCase):
    def test_password_hash_is_left_empty_for_phase_3(self):
        row = onboarding.account_row("su_abc", "a@b.com", "9876543210", "W1 Mon 12:00")
        self.assertIsNone(row["password_hash"])
        self.assertEqual(row["verified_email"], 0)
        self.assertEqual(row["verified_phone"], 0)

    def test_account_id_is_derived_from_the_user_id(self):
        self.assertEqual(onboarding.account_row("su_abc", None, None, "x")["id"], "acct_su_abc")


if __name__ == "__main__":
    unittest.main()


class RetainOnFailureTests(RouteTestCase):
    """2026-09-09, user's rule: "Retain/remember selections if 'Continue
    to Stats' fails."

    The step re-rendered from the saved draft — which validation had just
    declined to write — so a rejected submit came back blank and the
    error read as "start again" rather than "fix this one thing".
    """

    def post_vision(self, **form):
        """The rendered page with runs of whitespace collapsed.

        Attributes wrap across lines in the template, so a raw
        `value="Kids" checked` never matches even when the box IS
        ticked — the assertion would fail on formatting rather than on
        behaviour.
        """
        body = self.client.post("/onboarding/vision", data=form).get_data(as_text=True)
        return re.sub(r"\s+", " ", body)

    def test_a_rejected_submit_keeps_what_was_ticked(self):
        body = self.post_vision(intimacy_kinds=["Emotional"], other_keys=["Kids"])
        self.assertIn("how you are open to having kids", body)
        # both of their choices survive the rejection
        self.assertIn('value="Emotional" checked', body)
        self.assertIn('value="Kids" checked', body)

    def test_it_keeps_the_sub_options_too(self):
        """Rejected for the missing travel style, so the Kids answers
        beside it have to come back."""
        body = self.post_vision(intimacy_kinds=["Emotional"],
                                other_keys=["Kids", "Travel together"],
                                kids_route=["Adoption"])
        self.assertIn("what kind of travelling", body)
        self.assertIn('value="Adoption" checked', body)

    def test_a_sub_option_shows_its_parent_ticked_after_a_rejection(self):
        """The screen must not argue with the rule: if a detail selects
        its goal, a rejected submit shows the goal selected.

        Rejected on the missing intimacy kind, so the Kids tick that the
        route implies is what has to survive."""
        body = self.post_vision(kids_route=["Adoption"])
        self.assertIn("at least one kind of intimacy", body)
        self.assertIn('value="Kids" checked', body)

    def test_a_rejected_submit_beats_an_older_saved_draft(self):
        """Save a valid vision, come back, submit something invalid. The
        newer rejected answer is still the most recent thing they said."""
        self.client.post("/onboarding/vision", data={
            "intimacy_kinds": ["Physical"], "other_keys": ["Travel together"],
            "travel_style": ["Road trips"]})
        body = self.post_vision(intimacy_kinds=[], other_keys=["Cohabitate"],
                                cohabit_focus=["Chores split"])
        self.assertIn('value="Cohabitate" checked', body)
        self.assertNotIn('value="Travel together" checked', body)

    def test_the_stats_step_already_kept_its_input(self):
        """It read `submitted` before `saved` all along — asserted so the
        two steps cannot drift apart again."""
        body = self.client.post("/onboarding/stats", data={
            "city": "Bangalore", "age": "34"}).get_data(as_text=True)
        self.assertIn('value="34"', body)
        self.assertIn('value="Bangalore" selected', body)
