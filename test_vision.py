"""Tests for vision.py — the four-pillar structure and validation rules
(round3-fixes-spec.md §7), and the additive-only guardrail (Part F:
"Vision is additive-only. No delete operation exists.")."""

from __future__ import annotations

import ast
import unittest

import clock as clock_module
import matching
import onboarding
from pathlib import Path

from chemistry import INTIMACY_MANDATORY_KEYS as CHEMISTRY_INTIMACY_KEYS
from chemistry import MANDATORY_KEYS as CHEMISTRY_MANDATORY_KEYS
from vision import (
    MANDATORY_STATS_FIELDS,
    PILLAR_OPTIONS,
    add_detail,
    declare_change,
    prerequisites_met,
    rc_open,
    stats_prerequisite_met,
    unlocked_specific_topics,
    validate_pillars,
    vision_history,
)


class AdditiveOnlyGuardrailTests(unittest.TestCase):
    """Structural check that vision.py never defines a way to delete or
    edit a VisionEntry in place. declare_change() is the one function
    that can drop a sub-selection — gated on disclosure and rc_open(),
    exactly what Part F calls for ("reversals require an explicit,
    partner-disclosed declaration"), so it is not itself a "delete"."""

    def test_no_delete_or_remove_function_defined(self) -> None:
        source = Path(__file__).with_name("vision.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        for name in function_names:
            self.assertFalse(name.startswith("delete"), f"unexpected delete function: {name}")
            self.assertFalse(name.startswith("remove"), f"unexpected remove function: {name}")
            self.assertFalse(name.startswith("edit"), f"unexpected in-place edit function: {name}")


# A minimal, always-valid starting Vision — Intimacy (Physical) + Travel
# together — used as the base fixture across the tests below so each one
# only has to describe what it is actually testing.
BASE_VISION = [{"key": "Intimacy", "stance": ["Physical"]}, {"key": "Travel together", "stance": None}]


class PillarOptionsTests(unittest.TestCase):
    def test_exactly_four_pillars_relocation_and_career_are_gone(self):
        """round3-fixes-spec.md §7.1: "Remove Relocation and Career
        entirely.\""""
        self.assertEqual(set(PILLAR_OPTIONS), {"Intimacy", "Travel together", "Kids", "Cohabitate"})
        self.assertNotIn("Relocation", PILLAR_OPTIONS)
        self.assertNotIn("Career", PILLAR_OPTIONS)

    def test_travel_together_has_no_sub_selections(self):
        self.assertEqual(PILLAR_OPTIONS["Travel together"], ())

    def test_the_other_three_match_the_signup_vocabulary_exactly(self):
        """Never redefined here — imported straight from generate_users.py,
        the same source onboarding.py's signup flow uses, so a pillar
        cannot drift between sign-up and Relationship-stage editing."""
        self.assertEqual(set(PILLAR_OPTIONS["Intimacy"]), {"Emotional", "Physical"})
        self.assertEqual(set(PILLAR_OPTIONS["Kids"]), {"Naturally", "Surrogacy", "Adoption"})
        self.assertEqual(set(PILLAR_OPTIONS["Cohabitate"]), {"Chores split", "Expenses sharing"})


class ValidatePillarsTests(unittest.TestCase):
    """round3-fixes-spec.md §7.1's five validation rules, checked against
    a full pillar state — the same function add_detail()/declare_change()
    both call before accepting any mutation."""

    def test_a_minimal_valid_vision_passes(self):
        self.assertTrue(validate_pillars({"Intimacy": ["Physical"], "Travel together": []})["ok"])

    def test_intimacy_is_mandatory(self):
        result = validate_pillars({"Travel together": []})
        self.assertFalse(result["ok"])
        self.assertIn("Intimacy is mandatory", result["error"])

    def test_at_least_two_pillars_overall(self):
        result = validate_pillars({"Intimacy": ["Emotional"]})
        self.assertFalse(result["ok"])
        self.assertIn("at least one more pillar", result["error"])

    def test_kids_naturally_requires_physical(self):
        blocked = validate_pillars({"Intimacy": ["Emotional"], "Kids": ["Naturally"]})
        self.assertFalse(blocked["ok"])
        self.assertIn("naturally needs Physical", blocked["error"])
        allowed = validate_pillars({"Intimacy": ["Physical"], "Kids": ["Naturally"]})
        self.assertTrue(allowed["ok"], allowed["error"])

    def test_kids_surrogacy_or_adoption_do_not_require_physical(self):
        """2026-09-09 (evening) rule, kept — round3-fixes-spec.md's own
        table reads as requiring Physical for Kids as a whole, but the
        explicit prior decision (Surrogacy/Adoption involve no physical
        intimacy at all) is preserved rather than reversed."""
        for route in ("Surrogacy", "Adoption"):
            with self.subTest(route=route):
                result = validate_pillars({"Intimacy": ["Emotional"], "Kids": [route]})
                self.assertTrue(result["ok"], result["error"])

    def test_kids_needs_at_least_one_sub_selection(self):
        result = validate_pillars({"Intimacy": ["Physical"], "Kids": []})
        self.assertFalse(result["ok"])
        self.assertIn("Kids needs at least one sub-selection", result["error"])

    def test_cohabitate_needs_at_least_one_sub_selection(self):
        result = validate_pillars({"Intimacy": ["Physical"], "Cohabitate": []})
        self.assertFalse(result["ok"])
        self.assertIn("Cohabitate needs at least one sub-selection", result["error"])

    def test_travel_together_needs_none(self):
        result = validate_pillars({"Intimacy": ["Physical"], "Travel together": []})
        self.assertTrue(result["ok"], result["error"])

    def test_unknown_pillar_is_refused(self):
        self.assertFalse(validate_pillars({"Intimacy": ["Physical"], "Relocation": []})["ok"])

    def test_unknown_sub_selection_is_refused(self):
        result = validate_pillars({"Intimacy": ["Physical"], "Kids": ["Cloning"]})
        self.assertFalse(result["ok"])


class AddDetailTests(unittest.TestCase):
    """round3-fixes-spec.md §7.2: additive only — a pillar or
    sub-selection not previously present."""

    def test_adds_a_brand_new_pillar_with_a_sub_selection(self):
        result = add_detail(BASE_VISION, "Kids", "Adoption")
        self.assertTrue(result["ok"], result["error"])
        by_key = {v["key"]: v["stance"] for v in result["vision_json"]}
        self.assertEqual(by_key["Kids"], ["Adoption"])

    def test_adds_travel_together_with_no_sub_selection(self):
        vision_json = [{"key": "Intimacy", "stance": ["Physical"]}]  # Travel not yet present
        result = add_detail(vision_json, "Travel together")
        self.assertTrue(result["ok"], result["error"])
        by_key = {v["key"]: v["stance"] for v in result["vision_json"]}
        self.assertIsNone(by_key["Travel together"])

    def test_adds_a_sub_selection_alongside_an_existing_one(self):
        """e.g. "adding Adoption alongside Surrogacy" — round3-fixes-spec.md
        §7.2's own example."""
        vision_json = [{"key": "Intimacy", "stance": ["Emotional"]},
                       {"key": "Kids", "stance": ["Surrogacy"]}]
        result = add_detail(vision_json, "Kids", "Adoption")
        self.assertTrue(result["ok"], result["error"])
        by_key = {v["key"]: v["stance"] for v in result["vision_json"]}
        self.assertEqual(sorted(by_key["Kids"]), ["Adoption", "Surrogacy"])

    def test_refuses_a_sub_selection_already_present(self):
        vision_json = [{"key": "Intimacy", "stance": ["Emotional"]},
                       {"key": "Kids", "stance": ["Surrogacy"]}]
        result = add_detail(vision_json, "Kids", "Surrogacy")
        self.assertFalse(result["ok"])
        self.assertIn("already part", result["error"])

    def test_refuses_travel_together_a_second_time(self):
        result = add_detail(BASE_VISION, "Travel together")
        self.assertFalse(result["ok"])

    def test_travel_together_takes_no_sub_selection(self):
        result = add_detail([{"key": "Intimacy", "stance": ["Physical"]}], "Travel together", "Road trips")
        self.assertFalse(result["ok"])

    def test_never_removes_anything(self):
        """Not a general edit affordance — adding one sub-selection must
        never drop another already present."""
        vision_json = [{"key": "Intimacy", "stance": ["Emotional", "Physical"]},
                       {"key": "Kids", "stance": ["Surrogacy"]}]
        result = add_detail(vision_json, "Kids", "Adoption")
        by_key = {v["key"]: v["stance"] for v in result["vision_json"]}
        self.assertEqual(sorted(by_key["Intimacy"]), ["Emotional", "Physical"])
        self.assertIn("Surrogacy", by_key["Kids"])

    def test_a_new_pillar_still_has_to_pass_validation(self):
        """Adding Kids with a route that needs Physical, when Physical is
        not selected, is refused — add_detail() re-validates the whole
        resulting state, not just that the addition itself is well-formed."""
        vision_json = [{"key": "Intimacy", "stance": ["Emotional"]}]
        result = add_detail(vision_json, "Kids", "Naturally")
        self.assertFalse(result["ok"])
        self.assertIn("naturally needs Physical", result["error"])

    def test_unknown_pillar_or_sub_selection_is_refused(self):
        self.assertFalse(add_detail(BASE_VISION, "Relocation")["ok"])
        self.assertFalse(add_detail(BASE_VISION, "Kids", "Cloning")["ok"])


class DeclareChangeTests(unittest.TestCase):
    """round3-fixes-spec.md §7.3: add and/or remove sub-selections within
    an existing pillar, disclosed, and only while RC is open."""

    def _kids(self, *routes):
        return [{"key": "Intimacy", "stance": ["Emotional"]},
                {"key": "Kids", "stance": list(routes)}]

    def test_rejects_an_undisclosed_change(self):
        result = declare_change(self._kids("Surrogacy"), "Kids", add=["Adoption"], disclosed_to_partner=False)
        self.assertFalse(result["ok"])
        self.assertIn("disclosed", result["error"])

    def test_adds_a_sub_selection_when_disclosed(self):
        result = declare_change(self._kids("Surrogacy"), "Kids", add=["Adoption"], disclosed_to_partner=True)
        self.assertTrue(result["ok"], result["error"])
        by_key = {v["key"]: v["stance"] for v in result["vision_json"]}
        self.assertEqual(sorted(by_key["Kids"]), ["Adoption", "Surrogacy"])
        self.assertEqual(result["from"], ["Surrogacy"])
        self.assertEqual(sorted(result["to"]), ["Adoption", "Surrogacy"])

    def test_removes_a_sub_selection_when_disclosed(self):
        result = declare_change(self._kids("Surrogacy", "Adoption"), "Kids", remove=["Surrogacy"], disclosed_to_partner=True)
        self.assertTrue(result["ok"], result["error"])
        by_key = {v["key"]: v["stance"] for v in result["vision_json"]}
        self.assertEqual(by_key["Kids"], ["Adoption"])

    def test_removing_the_last_sub_selection_drops_the_pillar_entirely(self):
        """§7.1 rule 4 still applies to the RESULT — Kids with zero
        sub-selections is not a valid state, so it is removed outright
        rather than left present-but-empty."""
        vision_json = [{"key": "Intimacy", "stance": ["Emotional"]},
                       {"key": "Kids", "stance": ["Surrogacy"]},
                       {"key": "Travel together", "stance": None}]
        result = declare_change(vision_json, "Kids", remove=["Surrogacy"], disclosed_to_partner=True)
        self.assertTrue(result["ok"], result["error"])
        self.assertNotIn("Kids", {v["key"] for v in result["vision_json"]})

    def test_a_removal_that_breaks_the_minimum_pillar_count_is_refused(self):
        """Kids + Intimacy is only two pillars; removing Kids's only
        sub-selection would leave one — refused, not silently applied."""
        vision_json = [{"key": "Intimacy", "stance": ["Emotional"]},
                       {"key": "Kids", "stance": ["Surrogacy"]}]
        result = declare_change(vision_json, "Kids", remove=["Surrogacy"], disclosed_to_partner=True)
        self.assertFalse(result["ok"])
        self.assertIn("at least one more pillar", result["error"])

    def test_removing_physical_while_kids_naturally_is_selected_is_refused(self):
        vision_json = [{"key": "Intimacy", "stance": ["Emotional", "Physical"]},
                       {"key": "Kids", "stance": ["Naturally"]}]
        result = declare_change(vision_json, "Intimacy", remove=["Physical"], disclosed_to_partner=True)
        self.assertFalse(result["ok"])
        self.assertIn("naturally needs Physical", result["error"])

    def test_cannot_change_a_pillar_never_set(self):
        result = declare_change(BASE_VISION, "Kids", add=["Adoption"], disclosed_to_partner=True)
        self.assertFalse(result["ok"])
        self.assertIn("Add Detail instead", result["error"])

    def test_travel_together_has_nothing_to_change(self):
        result = declare_change(BASE_VISION, "Travel together", add=["Road trips"], disclosed_to_partner=True)
        self.assertFalse(result["ok"])

    def test_nothing_to_change_is_refused(self):
        result = declare_change(self._kids("Surrogacy"), "Kids", disclosed_to_partner=True)
        self.assertFalse(result["ok"])
        self.assertIn("Nothing to change", result["error"])

    def test_gated_on_rc_open_when_a_clock_is_given(self):
        closed = clock_module.SimulationClock.at(1, "Wed", 12)
        result = declare_change(self._kids("Surrogacy"), "Kids", add=["Adoption"],
                                 disclosed_to_partner=True, clock=closed)
        self.assertFalse(result["ok"])
        self.assertIn("Reality Check", result["error"])

        open_clock = clock_module.SimulationClock.at(1, "Sun", 22)
        result = declare_change(self._kids("Surrogacy"), "Kids", add=["Adoption"],
                                 disclosed_to_partner=True, clock=open_clock)
        self.assertTrue(result["ok"], result["error"])

    def test_no_clock_means_no_rc_gate(self):
        """The pure function itself is clock-optional — the caller
        (evolution_service.declare_vision_change) is what always supplies
        one for a real request; tests of the validation rules alone
        should not have to fake a clock too."""
        result = declare_change(self._kids("Surrogacy"), "Kids", add=["Adoption"], disclosed_to_partner=True)
        self.assertTrue(result["ok"], result["error"])


class RcOpenTests(unittest.TestCase):
    def test_open_from_sunday_night_through_monday_morning(self):
        self.assertTrue(rc_open(clock_module.SimulationClock.at(1, "Sun", 21)))
        self.assertTrue(rc_open(clock_module.SimulationClock.at(1, "Sun", 23)))
        self.assertTrue(rc_open(clock_module.SimulationClock.at(1, "Mon", 0)))
        self.assertTrue(rc_open(clock_module.SimulationClock.at(1, "Mon", 10)))

    def test_closed_outside_the_window(self):
        self.assertFalse(rc_open(clock_module.SimulationClock.at(1, "Sun", 20)))
        self.assertFalse(rc_open(clock_module.SimulationClock.at(1, "Mon", 11)))
        self.assertFalse(rc_open(clock_module.SimulationClock.at(1, "Wed", 12)))


class VisionHistoryTests(unittest.TestCase):
    def test_returns_every_entry_untouched(self) -> None:
        entries = [{"id": "1"}, {"id": "2"}]
        self.assertEqual(vision_history(entries), entries)
        self.assertIsNot(vision_history(entries), entries)  # a copy, not the same list object


class StatsPrerequisiteMetTests(unittest.TestCase):
    def _full_stats(self) -> dict:
        return {field: "x" for field in MANDATORY_STATS_FIELDS}

    def test_met_when_every_field_present(self) -> None:
        result = stats_prerequisite_met(self._full_stats())
        self.assertTrue(result["met"])

    def test_not_met_when_a_field_missing(self) -> None:
        stats = self._full_stats()
        del stats["profession"]
        result = stats_prerequisite_met(stats)
        self.assertFalse(result["met"])
        self.assertIn("profession", result["missing"])


class PrerequisitesMetTests(unittest.TestCase):
    def test_all_three_met(self) -> None:
        vision_entries = [{"user_id": "u_a", "element_key": "Kids"}]
        stats = {field: "x" for field in MANDATORY_STATS_FIELDS}
        chemistry_entries = [{"key": k, "value": "x"} for k in (*CHEMISTRY_MANDATORY_KEYS, *CHEMISTRY_INTIMACY_KEYS)]
        result = prerequisites_met(vision_entries, stats, chemistry_entries)
        self.assertTrue(result["met"])

    def test_not_met_without_any_vision_entries(self) -> None:
        stats = {field: "x" for field in MANDATORY_STATS_FIELDS}
        chemistry_entries = [{"key": k, "value": "x"} for k in (*CHEMISTRY_MANDATORY_KEYS, *CHEMISTRY_INTIMACY_KEYS)]
        result = prerequisites_met([], stats, chemistry_entries)
        self.assertFalse(result["met"])
        self.assertFalse(result["vision_met"])

    def test_not_met_with_incomplete_chemistry(self) -> None:
        vision_entries = [{"user_id": "u_a", "element_key": "Kids"}]
        stats = {field: "x" for field in MANDATORY_STATS_FIELDS}
        result = prerequisites_met(vision_entries, stats, [])
        self.assertFalse(result["met"])
        self.assertTrue(result["chemistry_missing"])


class UnlockedSpecificTopicsTests(unittest.TestCase):
    """round3-fixes-spec.md §7: keyed on the real pillar names now
    (element_key IS the pillar, since add_detail()/declare_change() write
    vision_json's own vocabulary). career_and_relocation is gone along
    with the Relocation/Career pillars that used to unlock it."""

    def test_empty_when_no_vision_entries(self) -> None:
        self.assertEqual(unlocked_specific_topics([]), [])

    def test_kids_unlocks_children_topic(self) -> None:
        entries = [{"element_key": "Kids"}]
        self.assertEqual(unlocked_specific_topics(entries), ["children"])

    def test_cohabitate_unlocks_two_topics_in_fixed_order(self) -> None:
        entries = [{"element_key": "Cohabitate"}]
        self.assertEqual(unlocked_specific_topics(entries), ["household_and_shared_space", "shared_expenses"])

    def test_unrecognized_element_key_unlocks_nothing(self) -> None:
        entries = [{"element_key": "Intimacy"}]
        self.assertEqual(unlocked_specific_topics(entries), [])

    def test_relocation_and_career_no_longer_unlock_anything(self):
        """They are not valid pillars any more, so nothing new can ever
        produce these element_keys — asserted anyway, since a stale
        historical VisionEntry row could still carry one."""
        entries = [{"element_key": "Relocation"}, {"element_key": "Career"}]
        self.assertEqual(unlocked_specific_topics(entries), [])

    def test_fixed_order_regardless_of_insertion_order(self) -> None:
        entries = [{"element_key": "Kids"}, {"element_key": "Cohabitate"}]
        self.assertEqual(
            unlocked_specific_topics(entries),
            ["household_and_shared_space", "shared_expenses", "children"],
        )


if __name__ == "__main__":
    unittest.main()


class VisionCompatibilityTests(unittest.TestCase):
    """2026-09-10, user's two rules, which are one rule:

      "matches can be selected if their bare minimum matches. Like say
       someone selects intimacy emotional and another one selects both.
       Then it should be a match, as there is a point for later
       correction."

      "if someone selects kids Naturally and another one selects
       Surrogacy or Adoption or both then it is excluded."

    For a pillar they have BOTH chosen, their stances must overlap.
    """

    def u(self, **pillars):
        return {"visions": [{"key": k, "stance": v} for k, v in pillars.items()]}

    def test_a_narrower_intimacy_still_matches_a_wider_one(self):
        self.assertTrue(matching.visions_compatible(
            self.u(Intimacy=["Emotional"]),
            self.u(Intimacy=["Emotional", "Physical"])))

    def test_two_intimacies_that_do_not_meet_at_all_are_excluded(self):
        self.assertFalse(matching.visions_compatible(
            self.u(Intimacy=["Emotional"]), self.u(Intimacy=["Physical"])))

    def test_naturally_against_surrogacy_is_excluded(self):
        for other in (["Surrogacy"], ["Adoption"], ["Surrogacy", "Adoption"]):
            with self.subTest(other=other):
                self.assertFalse(matching.visions_compatible(
                    self.u(Kids=["Naturally"]), self.u(Kids=other)))

    def test_but_any_shared_route_is_a_match(self):
        self.assertTrue(matching.visions_compatible(
            self.u(Kids=["Naturally"]), self.u(Kids=["Naturally", "Adoption"])))

    def test_a_pillar_only_one_of_them_chose_is_not_a_disagreement(self):
        """Silence is not dissent — that is what the kids dealbreakers are
        for, and they are switchable."""
        self.assertTrue(matching.visions_compatible(
            self.u(Intimacy=["Emotional"]),
            self.u(Intimacy=["Emotional"], Kids=["Naturally"])))

    def test_a_pillar_with_no_stance_yet_cannot_disagree(self):
        self.assertTrue(matching.visions_compatible(
            self.u(Kids=[]), self.u(Kids=["Surrogacy"])))

    def test_the_rule_is_symmetric(self):
        pairs = [(["Emotional"], ["Emotional", "Physical"]),
                 (["Emotional"], ["Physical"]),
                 (["Emotional", "Physical"], ["Physical"])]
        for a, b in pairs:
            with self.subTest(a=a, b=b):
                self.assertEqual(
                    matching.visions_compatible(self.u(Intimacy=a), self.u(Intimacy=b)),
                    matching.visions_compatible(self.u(Intimacy=b), self.u(Intimacy=a)))

    def test_fits_filters_refuses_an_incompatible_vision(self):
        """And it is NOT ignorable — a vision that cannot meet is the
        product saying no, not a preference set too narrow."""
        base = {"user_id": "a", "gender": "female", "city": "Bangalore",
                "stats": {"age": 30},
                "preferences": {"fixed": {"dealbreakers": []},
                                "adjustable": {"distance_km": [0, 100]},
                                "ignored": sorted(matching.IGNORABLE)}}
        a = {**base, "visions": [{"key": "Kids", "stance": ["Naturally"]}]}
        b = {**base, "user_id": "b", "gender": "male",
             "visions": [{"key": "Kids", "stance": ["Adoption"]}]}
        self.assertFalse(matching.fits_filters(a, b))


class MarriagePresetTests(unittest.TestCase):
    """2026-09-10: "I want Vision also to be selected all as an option...
    like 'Traditional' or 'marriage' which will select all by default."
    """

    def test_it_ticks_every_pillar(self):
        """round3-fixes-spec.md §7.1: "ticks all four" means all four
        pillars (OTHER_VISION_KEYS), not just the ones with sub-options
        (DETAILED_GOALS) — Travel together has none of its own any more."""
        picked = onboarding.preset_selection(onboarding.PRESET_MARRIAGE)
        self.assertEqual(sorted(picked["other_keys"]), sorted(onboarding.OTHER_VISION_KEYS))
        self.assertEqual(sorted(picked["intimacy_kinds"]), sorted(onboarding.INTIMACY_KINDS))

    def test_and_every_sub_option_under_them(self):
        picked = onboarding.preset_selection(onboarding.PRESET_MARRIAGE)
        for goal, options in onboarding.DETAILED_GOALS.items():
            with self.subTest(goal=goal):
                self.assertEqual(sorted(picked[onboarding.DETAIL_FIELD[goal]]), sorted(options))

    def test_what_it_produces_passes_the_normal_validation(self):
        """The preset takes no path of its own through validation — that
        is what stops it drifting from what the form can express."""
        picked = onboarding.preset_selection(onboarding.PRESET_MARRIAGE)
        got = onboarding.validate_vision(
            picked["intimacy_kinds"], picked["other_keys"],
            picked["cohabit_focus"], picked["kids_route"])
        self.assertTrue(got["ok"], got.get("error"))

    def test_an_unknown_preset_ticks_nothing(self):
        self.assertEqual(onboarding.preset_selection("traditional"), {})
        self.assertEqual(onboarding.preset_selection(""), {})


class RecommendedRangeTests(unittest.TestCase):
    """2026-09-10, user's report: "AI recommended part is not right. Even
    for 65 year old it recommends age of 31-40... Make it a generic + or
    - 10."
    """

    def test_it_is_anchored_on_the_person_not_the_population(self):
        self.assertEqual(matching.recommend_range(65, "age"), (55, 75))
        self.assertEqual(matching.recommend_range(24, "age"), (18, 34))

    def test_a_sixty_five_year_old_is_never_told_thirty_one(self):
        lo, hi = matching.recommend_range(65, "age")
        self.assertGreater(lo, 40)

    def test_it_never_recommends_below_the_floor(self):
        self.assertEqual(matching.recommend_range(19, "age")[0], 18)

    def test_no_own_value_means_no_recommendation(self):
        for value in (None, "", [], True):
            with self.subTest(value=value):
                self.assertIsNone(matching.recommend_range(value, "age"))

    def test_waist_keeps_a_tighter_spread(self):
        """Ten inches either way would span the whole scale."""
        lo, hi = matching.recommend_range(32, "waist_in")
        self.assertEqual((lo, hi), (27, 37))


class IntimacyParentChipTests(unittest.TestCase):
    """2026-09-11, user's rule: "select Intimacy automatically when
    Emotional/Physical or both are selected, keeping it consistent."

    Consistency is the point: Kids, Cohabitate and Travel each had a
    parent chip a sub-option ticked for you. Intimacy had a heading.
    """

    TEMPLATE = Path(__file__).parent / "templates" / "onboard_vision.html"

    def markup(self):
        return self.TEMPLATE.read_text(encoding="utf-8")

    def test_intimacy_has_a_parent_chip_like_the_other_pillars(self):
        markup = self.markup()
        self.assertIn('value="Intimacy"', markup)
        self.assertIn("goal-parent", markup)

    def test_all_four_pillars_share_one_parent_class(self):
        """One rule, not four — the script keys off the class, so a new
        pillar inherits the behaviour by being a .goal-block."""
        markup = self.markup()
        self.assertEqual(markup.count("goal-parent"), 3)   # class, Intimacy, loop
        self.assertIn("input.goal-parent", markup)

    def test_intimacy_shows_ticked_when_a_kind_is_already_chosen(self):
        self.assertIn("{% if chosen_kinds %}checked{% endif %}", self.markup())

    def test_the_parent_chip_cannot_bypass_validation(self):
        """It posts as `pillars`, which validate_vision never reads — at
        least one kind is still required."""
        got = onboarding.validate_vision([], ["Kids"], [], ["Naturally"])
        self.assertFalse(got["ok"])

    def test_the_selection_colour_is_no_longer_the_alarm_colour(self):
        """2026-09-11: "the selection are highlighted in red, can you
        change it to more pleasing color choice." Coral marks red flags,
        cancellation charges and errors; on a screen where every tick is
        something you want, it is the wrong signal."""
        css = (Path(__file__).parent / "static" / "style.css").read_text(encoding="utf-8")
        self.assertIn(".vision-form .chip-check input:checked + span", css)
        block = css.split(".vision-form .chip-check input:checked + span")[1].split("}")[0]
        self.assertIn("--mint", block)
        self.assertNotIn("--coral", block)
