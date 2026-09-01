"""Tests for guru_dating.py."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from guru_dating import GREEN_FLAGS, RED_FLAGS, capture_flags, capture_pass_reason, pre_date_briefing


class ScopeBoundaryTests(unittest.TestCase):
    """§7: "Guru does not mediate, does not run pillars, does not generate
    weekly reports in Dating." Enforced structurally, not just by
    docstring — this module must never import journey.py's pillar/topic
    machinery at all."""

    def test_never_imports_journey_module(self) -> None:
        source = Path(__file__).with_name("guru_dating.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_names.add(node.module)
        self.assertNotIn("journey", imported_names)


class PreDateBriefingTests(unittest.TestCase):
    def test_includes_courtesies_safety_and_boundaries(self) -> None:
        briefing = pre_date_briefing("handshake")
        self.assertTrue(briefing["courtesies"])
        self.assertTrue(briefing["safety"])
        self.assertTrue(briefing["boundaries"])

    def test_carries_the_partners_greeting_preference(self) -> None:
        briefing = pre_date_briefing("side-hug")
        self.assertEqual(briefing["partner_greeting"], "side-hug")

    def test_notes_in_app_only_contact_exchange(self) -> None:
        briefing = pre_date_briefing(None)
        self.assertIn("in-app", briefing["note"])


class CaptureFlagsTests(unittest.TestCase):
    def test_exactly_two_valid_green_flags_meets_minimum(self) -> None:
        result = capture_flags([GREEN_FLAGS[0], GREEN_FLAGS[1]], [])
        self.assertEqual(result["green"], [GREEN_FLAGS[0], GREEN_FLAGS[1]])
        self.assertTrue(result["meets_minimum"])

    def test_one_green_flag_does_not_meet_minimum(self) -> None:
        result = capture_flags([GREEN_FLAGS[0]], [])
        self.assertFalse(result["meets_minimum"])

    def test_zero_green_flags_does_not_meet_minimum(self) -> None:
        result = capture_flags([], [])
        self.assertFalse(result["meets_minimum"])

    def test_green_flags_capped_at_two(self) -> None:
        result = capture_flags(list(GREEN_FLAGS), [])
        self.assertEqual(len(result["green"]), 2)

    def test_red_flags_optional_and_capped_at_two(self) -> None:
        result = capture_flags(GREEN_FLAGS[:2], list(RED_FLAGS))
        self.assertEqual(len(result["red"]), 2)
        empty_red = capture_flags(GREEN_FLAGS[:2], [])
        self.assertEqual(empty_red["red"], [])
        self.assertTrue(empty_red["meets_minimum"])  # red is never required

    def test_unknown_labels_are_dropped(self) -> None:
        result = capture_flags(["Not a real flag", GREEN_FLAGS[0]], ["Also not real"])
        self.assertEqual(result["green"], [GREEN_FLAGS[0]])
        self.assertEqual(result["red"], [])


class CapturePassReasonTests(unittest.TestCase):
    def test_volunteered_reason_is_kept_verbatim(self) -> None:
        result = capture_pass_reason("Didn't feel a connection")
        self.assertTrue(result["volunteered"])
        self.assertEqual(result["reason"], "Didn't feel a connection")

    def test_none_is_not_volunteered(self) -> None:
        result = capture_pass_reason(None)
        self.assertFalse(result["volunteered"])
        self.assertIsNone(result["reason"])

    def test_blank_string_is_not_volunteered(self) -> None:
        result = capture_pass_reason("   ")
        self.assertFalse(result["volunteered"])
        self.assertIsNone(result["reason"])


if __name__ == "__main__":
    unittest.main()
