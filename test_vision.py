"""Tests for vision.py — especially the additive-only guardrail (Part F:
"Vision is additive-only. No delete operation exists.")."""

from __future__ import annotations

import ast
import unittest
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
