"""Tests for lockin.py."""

from __future__ import annotations

import unittest

from clock import SimulationClock
from lockin import (
    candidates_to_clear,
    complete,
    increment_dates_completed,
    is_locked_in,
    on_mutual_interest,
    release,
)


class OnMutualInterestTests(unittest.TestCase):
    def test_builds_an_active_lockin_row(self) -> None:
        row = on_mutual_interest("u_a", "u_b", week=3, created_at=SimulationClock.at(3, "Tue", 13))
        self.assertEqual(row["user_a"], "u_a")
        self.assertEqual(row["user_b"], "u_b")
        self.assertEqual(row["week"], 3)
        self.assertEqual(row["created_at"], "Tue:13")
        self.assertEqual(row["status"], "active")


class CandidatesToClearTests(unittest.TestCase):
    def test_clears_everyone_except_the_locked_partner(self) -> None:
        a_matches = [{"candidate_id": "u_b"}, {"candidate_id": "u_c"}, {"candidate_id": "u_d"}]
        b_matches = [{"candidate_id": "u_a"}, {"candidate_id": "u_e"}]
        result = candidates_to_clear(a_matches, b_matches, locked_a_id="u_a", locked_b_id="u_b")
        self.assertEqual(set(result["user_a"]), {"u_c", "u_d"})
        self.assertEqual(set(result["user_b"]), {"u_e"})

    def test_empty_when_the_locked_match_was_the_only_one(self) -> None:
        a_matches = [{"candidate_id": "u_b"}]
        b_matches = [{"candidate_id": "u_a"}]
        result = candidates_to_clear(a_matches, b_matches, locked_a_id="u_a", locked_b_id="u_b")
        self.assertEqual(result["user_a"], [])
        self.assertEqual(result["user_b"], [])


class ReleaseTests(unittest.TestCase):
    def test_marks_released_with_reason(self) -> None:
        lockin = {"user_a": "u_a", "user_b": "u_b", "week": 3, "created_at": "Mon:14", "status": "active"}
        released = release(lockin, "no calendar overlap")
        self.assertEqual(released["status"], "released")
        self.assertEqual(released["release_reason"], "no calendar overlap")

    def test_does_not_mutate_input(self) -> None:
        lockin = {"user_a": "u_a", "user_b": "u_b", "week": 3, "created_at": "Mon:14", "status": "active"}
        release(lockin, "no-show")
        self.assertEqual(lockin["status"], "active")
        self.assertNotIn("release_reason", lockin)


class CompleteTests(unittest.TestCase):
    def test_marks_completed(self) -> None:
        lockin = {"user_a": "u_a", "user_b": "u_b", "week": 3, "created_at": "Mon:14", "status": "active"}
        done = complete(lockin)
        self.assertEqual(done["status"], "completed")

    def test_does_not_mutate_input(self) -> None:
        lockin = {"user_a": "u_a", "user_b": "u_b", "week": 3, "created_at": "Mon:14", "status": "active"}
        complete(lockin)
        self.assertEqual(lockin["status"], "active")


class IsLockedInTests(unittest.TestCase):
    def test_true_when_user_is_either_side(self) -> None:
        active = [{"user_a": "u_a", "user_b": "u_b"}]
        self.assertTrue(is_locked_in("u_a", active))
        self.assertTrue(is_locked_in("u_b", active))

    def test_false_when_not_present(self) -> None:
        active = [{"user_a": "u_a", "user_b": "u_b"}]
        self.assertFalse(is_locked_in("u_c", active))

    def test_false_for_empty_lockins(self) -> None:
        self.assertFalse(is_locked_in("u_a", []))


class IncrementDatesCompletedTests(unittest.TestCase):
    def test_starts_from_missing_field_as_zero(self) -> None:
        lockin = {"user_a": "u_a", "user_b": "u_b", "week": 1, "created_at": "Mon:14", "status": "active"}
        bumped = increment_dates_completed(lockin)
        self.assertEqual(bumped["dates_completed"], 1)

    def test_increments_existing_count(self) -> None:
        lockin = {"user_a": "u_a", "user_b": "u_b", "dates_completed": 1, "status": "active"}
        bumped = increment_dates_completed(lockin)
        self.assertEqual(bumped["dates_completed"], 2)

    def test_does_not_mutate_input(self) -> None:
        lockin = {"user_a": "u_a", "user_b": "u_b", "dates_completed": 1, "status": "active"}
        increment_dates_completed(lockin)
        self.assertEqual(lockin["dates_completed"], 1)


if __name__ == "__main__":
    unittest.main()
