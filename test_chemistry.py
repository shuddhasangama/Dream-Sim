"""Tests for chemistry.py."""

from __future__ import annotations

import unittest

from chemistry import (
    INTIMACY_MANDATORY_KEYS,
    INTIMACY_PACE_OPTIONS,
    MANDATORY_KEYS,
    intimacy_fields_complete,
    on_chemistry_update,
    prerequisite_met,
    set_entry,
)

ALL_MANDATORY_KEYS = (*MANDATORY_KEYS, *INTIMACY_MANDATORY_KEYS)


def _entry(key: str, value: str = "x") -> dict:
    return {"key": key, "value": value}


class SetEntryTests(unittest.TestCase):
    def test_builds_a_row(self) -> None:
        row = set_entry("u_a", "love_language", "words of affirmation", "2026-03-01")
        self.assertEqual(row, {"user_id": "u_a", "key": "love_language", "value": "words of affirmation", "updated_at": "2026-03-01"})


class PrerequisiteMetTests(unittest.TestCase):
    def _all_entries(self) -> list[dict]:
        return [_entry(k, f"value for {k}") for k in ALL_MANDATORY_KEYS]

    def test_met_when_every_mandatory_key_present(self) -> None:
        result = prerequisite_met(self._all_entries())
        self.assertTrue(result["met"])
        self.assertEqual(result["missing"], [])

    def test_not_met_when_a_c3_key_is_missing(self) -> None:
        entries = [e for e in self._all_entries() if e["key"] != MANDATORY_KEYS[0]]
        result = prerequisite_met(entries)
        self.assertFalse(result["met"])
        self.assertIn(MANDATORY_KEYS[0], result["missing"])

    def test_not_met_when_an_intimacy_key_is_missing(self) -> None:
        entries = [e for e in self._all_entries() if e["key"] != "intimacy_pace"]
        result = prerequisite_met(entries)
        self.assertFalse(result["met"])
        self.assertIn("intimacy_pace", result["missing"])

    def test_blank_value_does_not_count_as_present(self) -> None:
        entries = self._all_entries()
        entries[0]["value"] = ""
        result = prerequisite_met(entries)
        self.assertFalse(result["met"])

    def test_empty_list_is_missing_everything(self) -> None:
        result = prerequisite_met([])
        self.assertFalse(result["met"])
        self.assertEqual(set(result["missing"]), set(ALL_MANDATORY_KEYS))

    def test_extra_non_mandatory_keys_are_ignored(self) -> None:
        entries = self._all_entries() + [_entry("some_other_field", "value")]
        result = prerequisite_met(entries)
        self.assertTrue(result["met"])


class IntimacyFieldsCompleteTests(unittest.TestCase):
    def test_true_when_all_five_present(self) -> None:
        entries = [_entry(k) for k in INTIMACY_MANDATORY_KEYS]
        self.assertTrue(intimacy_fields_complete(entries))

    def test_false_when_one_missing(self) -> None:
        entries = [_entry(k) for k in INTIMACY_MANDATORY_KEYS[:-1]]
        self.assertFalse(intimacy_fields_complete(entries))

    def test_ignores_c3_fields_entirely(self) -> None:
        entries = [_entry(k) for k in MANDATORY_KEYS]  # none of these are intimacy fields
        self.assertFalse(intimacy_fields_complete(entries))


class OnChemistryUpdateTests(unittest.TestCase):
    def _entries(self, pace: str) -> list[dict]:
        entries = [_entry(k) for k in INTIMACY_MANDATORY_KEYS]
        for e in entries:
            if e["key"] == "intimacy_pace":
                e["value"] = pace
        return entries

    def test_not_surfaced_until_both_sides_complete(self) -> None:
        entries_a = self._entries("slow")
        entries_b_incomplete = [_entry(k) for k in INTIMACY_MANDATORY_KEYS[:-1]]
        result = on_chemistry_update(entries_a, entries_b_incomplete)
        self.assertFalse(result["surfaced"])

    def test_no_mismatch_when_pace_matches(self) -> None:
        result = on_chemistry_update(self._entries("slow"), self._entries("slow"))
        self.assertFalse(result["surfaced"])

    def test_no_mismatch_for_an_adjacent_pace(self) -> None:
        # open_to_physical_intimacy_early <-> led_by_connection is a
        # 1-step gap — not material.
        result = on_chemistry_update(
            self._entries("open_to_physical_intimacy_early"), self._entries("led_by_connection")
        )
        self.assertFalse(result["surfaced"])

    def test_material_mismatch_surfaced_to_both(self) -> None:
        result = on_chemistry_update(self._entries("open_to_physical_intimacy_early"), self._entries("waiting_until_married"))
        self.assertTrue(result["surfaced"])
        self.assertTrue(result["offer_next_level"])
        self.assertIsNotNone(result["message"])

    def test_never_blocks_progression(self) -> None:
        # The result carries no "blocked"/"gate" field at all — surfacing
        # is informational only (§A2: "never blocks progression").
        result = on_chemistry_update(self._entries("slow"), self._entries("waiting_until_married"))
        self.assertNotIn("blocked", result)
        self.assertNotIn("gate", result)


class OptionVocabularyTests(unittest.TestCase):
    def test_pace_options_cover_four_values(self) -> None:
        self.assertEqual(len(INTIMACY_PACE_OPTIONS), 4)


if __name__ == "__main__":
    unittest.main()
