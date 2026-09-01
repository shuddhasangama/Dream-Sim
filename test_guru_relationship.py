"""Tests for guru_relationship.py."""

from __future__ import annotations

import unittest

from guru_relationship import (
    add_romance_idea,
    air_step1_raise_difference,
    air_step2_consent_to_share,
    expense_check,
    mediator_invoke,
    resolve_difference,
    romance_suggestion,
)


class AirStep1Tests(unittest.TestCase):
    def test_tags_new_when_nothing_similar_is_open(self) -> None:
        row = air_step1_raise_difference("couple-1", "u_a", "leaves dishes in the sink", 3, [])
        self.assertEqual(row["tag"], "new")
        self.assertEqual(row["status"], "open")
        self.assertEqual(row["consent_to_share"], 0)

    def test_tags_repeated_when_the_same_open_text_exists(self) -> None:
        existing = [{"text": "leaves dishes in the sink", "status": "open"}]
        row = air_step1_raise_difference("couple-1", "u_a", "leaves dishes in the sink", 4, existing)
        self.assertEqual(row["tag"], "repeated")

    def test_does_not_tag_repeated_if_the_prior_one_was_sorted(self) -> None:
        existing = [{"text": "leaves dishes in the sink", "status": "sorted"}]
        row = air_step1_raise_difference("couple-1", "u_a", "leaves dishes in the sink", 4, existing)
        self.assertEqual(row["tag"], "new")


class AirStep2Tests(unittest.TestCase):
    def test_consent_given(self) -> None:
        difference = air_step1_raise_difference("couple-1", "u_a", "text", 3, [])
        updated = air_step2_consent_to_share(difference, True)
        self.assertEqual(updated["consent_to_share"], 1)

    def test_consent_withheld(self) -> None:
        difference = air_step1_raise_difference("couple-1", "u_a", "text", 3, [])
        updated = air_step2_consent_to_share(difference, False)
        self.assertEqual(updated["consent_to_share"], 0)


class ResolveDifferenceTests(unittest.TestCase):
    def test_moves_to_sorted(self) -> None:
        difference = air_step1_raise_difference("couple-1", "u_a", "text", 3, [])
        resolved = resolve_difference(difference)
        self.assertEqual(resolved["status"], "sorted")


class RomanceSuggestionTests(unittest.TestCase):
    def test_pulls_vibes_from_chemistry_entries(self) -> None:
        entries = [
            {"key": "vibes_to_keep_alive", "value": "surprise dates"},
            {"key": "love_language", "value": "words of affirmation"},
        ]
        result = romance_suggestion(entries, ["existing idea"])
        self.assertEqual(result["vibes_on_file"], ["surprise dates"])
        self.assertEqual(result["existing_ideas"], ["existing idea"])
        self.assertIsNone(result["new_idea"])


class AddRomanceIdeaTests(unittest.TestCase):
    def test_appends_without_mutating_input(self) -> None:
        existing = ["idea one"]
        updated = add_romance_idea(existing, "idea two")
        self.assertEqual(updated, ["idea one", "idea two"])
        self.assertEqual(existing, ["idea one"])


class ExpenseCheckTests(unittest.TestCase):
    def test_compliant(self) -> None:
        result = expense_check("50/50 split", True)
        self.assertTrue(result["compliant"])

    def test_not_compliant(self) -> None:
        result = expense_check("50/50 split", False)
        self.assertFalse(result["compliant"])


class MediatorInvokeTests(unittest.TestCase):
    def test_builds_a_record(self) -> None:
        record = mediator_invoke("couple-1", "money stress", 5)
        self.assertEqual(record, {"couple_id": "couple-1", "topic": "money stress", "week": 5})


if __name__ == "__main__":
    unittest.main()
