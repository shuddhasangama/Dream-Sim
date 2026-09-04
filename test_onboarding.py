"""Tests for onboarding.py — the front door (Segment A).

Follows the existing convention: plain unittest, no fixtures, asserting on
the pure functions rather than on Flask. The most important assertions here
are the compatibility ones: a self-registered user must be shaped exactly
like a generated one, or matching/cadence/journey silently misbehave on it.

Run: python -m pytest test_onboarding.py -q
"""

from __future__ import annotations

import json
import unittest

import onboarding
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
        "budget": RESTAURANT_BUDGETS[1], "ethnicity": "Indian",
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

    def test_kids_requires_physical_intimacy(self):
        blocked = onboarding.validate_vision(["Emotional"], ["Kids"])
        self.assertFalse(blocked["ok"])
        self.assertIn("Physical", blocked["error"])

        allowed = onboarding.validate_vision(["Emotional", "Physical"], ["Kids"])
        self.assertTrue(allowed["ok"])

    def test_unknown_values_are_dropped_not_stored(self):
        result = onboarding.validate_vision(["Emotional", "Telepathic"], ["Travel together", "Yachting"])
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["intimacy_kinds"], ["Emotional"])
        self.assertEqual(result["other_keys"], ["Travel together"])

    def test_built_visions_match_the_generated_shape(self):
        visions = onboarding.build_visions(["Physical"], ["Kids", "Travel together"])
        self.assertEqual(visions[0]["key"], "Intimacy")
        self.assertEqual(visions[0]["stance"], ["Physical"])
        for entry in visions[1:]:
            self.assertIn(entry["key"], OTHER_VISION_KEYS)
            # Kids and Travel together carry no detail at signup; Kids is
            # set later at /road/vision, once the couple reaches Relationship.
            self.assertIsNone(entry["stance"])


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

    def test_focus_is_discarded_when_cohabitate_is_not_chosen(self):
        """Unticking Cohabitate must not leave a preference behind for a
        goal the user did not pick."""
        result = onboarding.validate_vision(["Physical"], ["Kids"], ["Chores split"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["cohabit_focus"], [])
        visions = onboarding.build_visions(["Physical"], ["Kids"], ["Chores split"])
        self.assertNotIn("Cohabitate", [v["key"] for v in visions])

    def test_unknown_focus_values_are_dropped(self):
        result = onboarding.validate_vision(["Physical"], ["Cohabitate"], ["Chores split", "Cooking rota"])
        self.assertEqual(result["cohabit_focus"], ["Chores split"])

    def test_built_cohabitate_stance_is_a_sorted_list(self):
        visions = onboarding.build_visions(
            ["Physical"], ["Cohabitate", "Kids", "Travel together"], ["Expenses sharing", "Chores split"]
        )
        by_key = {v["key"]: v["stance"] for v in visions}
        self.assertEqual(by_key["Cohabitate"], sorted(COHABIT_FOCUS))
        self.assertIsNone(by_key["Kids"])
        self.assertIsNone(by_key["Travel together"])

    def test_travel_together_alone_needs_no_detail(self):
        result = onboarding.validate_vision(["Emotional"], ["Travel together"], [])
        self.assertTrue(result["ok"], result["error"])

    def test_kids_still_requires_physical_intimacy(self):
        """The 2026-08-28 rule was not repealed by the 2026-09-03 revision."""
        self.assertFalse(onboarding.validate_vision(["Emotional"], ["Kids"], [])["ok"])


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
        self.assertEqual(result["stats"]["ethnicity"], "Prefer not to say")

    def test_ethnicity_never_becomes_a_matching_filter(self):
        """Declaring your own descent and screening others by theirs are
        different products. Only the first was asked for."""
        stats = onboarding.validate_stats(_valid_stats())["stats"]
        prefs = onboarding.default_preferences(stats)
        self.assertNotIn("ethnicity", prefs["adjustable"])
        self.assertNotIn("budget", prefs["adjustable"])
        self.assertEqual(prefs["fixed"]["dealbreakers"], [])

    def test_offered_options_match_the_generated_population(self):
        by_key = {k: opts for k, _, opts in onboarding.OPTIONAL_CHOICE_STATS}
        # Budget is no longer a plain choice field: its bands come from the
        # city's currency, so locale_defaults owns the list.
        import locale_defaults
        self.assertEqual(locale_defaults.budget_bands_for("Chennai"), RESTAURANT_BUDGETS)
        self.assertEqual(by_key["ethnicity"], ETHNICITIES)


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
