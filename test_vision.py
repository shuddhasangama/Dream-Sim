"""Tests for vision.py — especially the additive-only guardrail (Part F:
"Vision is additive-only. No delete operation exists.")."""

from __future__ import annotations

import ast
import unittest

import matching
import onboarding
from pathlib import Path

from chemistry import INTIMACY_MANDATORY_KEYS as CHEMISTRY_INTIMACY_KEYS
from chemistry import MANDATORY_KEYS as CHEMISTRY_MANDATORY_KEYS
from vision import (
    MANDATORY_STATS_FIELDS,
    add_vision_detail,
    declare_vision_change,
    prerequisites_met,
    stats_prerequisite_met,
    unlocked_specific_topics,
    vision_history,
)


class AdditiveOnlyGuardrailTests(unittest.TestCase):
    """Structural check that vision.py never defines a way to delete or
    edit a VisionEntry in place — only add_vision_detail() (free) and
    declare_vision_change() (gated)."""

    def test_no_delete_or_remove_function_defined(self) -> None:
        source = Path(__file__).with_name("vision.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        for name in function_names:
            self.assertFalse(name.startswith("delete"), f"unexpected delete function: {name}")
            self.assertFalse(name.startswith("remove"), f"unexpected remove function: {name}")
            self.assertFalse(name.startswith("edit"), f"unexpected in-place edit function: {name}")


class AddVisionDetailTests(unittest.TestCase):
    def test_builds_a_row_with_no_parent(self) -> None:
        row = add_vision_detail("u_a", "children", "wants children · 2 · within 3-4 years", "2026-03-01")
        self.assertEqual(row["user_id"], "u_a")
        self.assertEqual(row["element_key"], "children")
        self.assertIsNone(row["parent_id"])

    def test_can_chain_beneath_a_parent(self) -> None:
        first = add_vision_detail("u_a", "relocation", "open to relocation", "2026-03-01")
        second = add_vision_detail("u_a", "relocation", "within India, not before 2028", "2026-03-15", parent_id="entry-1")
        self.assertEqual(second["parent_id"], "entry-1")
        self.assertIsNone(first["parent_id"])


class DeclareVisionChangeTests(unittest.TestCase):
    def test_builds_a_row_when_disclosed(self) -> None:
        row = declare_vision_change(
            "u_a", "children", "wants children", "does not want children", "2026-03-01",
            disclosed_to_partner=True, guru_conversation_id="conv-1",
        )
        self.assertTrue(row["disclosed_to_partner"])
        self.assertEqual(row["guru_conversation_id"], "conv-1")

    def test_rejects_an_undisclosed_change(self) -> None:
        with self.assertRaises(ValueError):
            declare_vision_change(
                "u_a", "children", "wants children", "does not want children", "2026-03-01",
                disclosed_to_partner=False,
            )


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
        vision_entries = [{"user_id": "u_a", "element_key": "children"}]
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
        vision_entries = [{"user_id": "u_a", "element_key": "children"}]
        stats = {field: "x" for field in MANDATORY_STATS_FIELDS}
        result = prerequisites_met(vision_entries, stats, [])
        self.assertFalse(result["met"])
        self.assertTrue(result["chemistry_missing"])


class UnlockedSpecificTopicsTests(unittest.TestCase):
    def test_empty_when_no_vision_entries(self) -> None:
        self.assertEqual(unlocked_specific_topics([]), [])

    def test_children_unlocks_children_topic(self) -> None:
        entries = [{"element_key": "children"}]
        self.assertEqual(unlocked_specific_topics(entries), ["children"])

    def test_cohabitation_unlocks_two_topics_in_fixed_order(self) -> None:
        entries = [{"element_key": "cohabitation"}]
        self.assertEqual(unlocked_specific_topics(entries), ["household_and_shared_space", "shared_expenses"])

    def test_career_and_relocation_collapse_to_one_topic(self) -> None:
        entries = [{"element_key": "career"}, {"element_key": "relocation"}]
        self.assertEqual(unlocked_specific_topics(entries), ["career_and_relocation"])

    def test_unrecognized_element_key_unlocks_nothing(self) -> None:
        entries = [{"element_key": "intimacy"}]
        self.assertEqual(unlocked_specific_topics(entries), [])

    def test_fixed_order_regardless_of_insertion_order(self) -> None:
        entries = [{"element_key": "career"}, {"element_key": "children"}, {"element_key": "cohabitation"}]
        self.assertEqual(
            unlocked_specific_topics(entries),
            ["household_and_shared_space", "shared_expenses", "children", "career_and_relocation"],
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
        picked = onboarding.preset_selection(onboarding.PRESET_MARRIAGE)
        self.assertEqual(sorted(picked["other_keys"]), sorted(onboarding.DETAILED_GOALS))
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
            picked["cohabit_focus"], picked["kids_route"], picked["travel_style"])
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
