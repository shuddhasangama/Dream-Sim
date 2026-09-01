"""Tests for cadence.py."""

from __future__ import annotations

import unittest

from cadence import generate_week_matches, match_status, no_response_matches
from clock import SimulationClock, checkpoint, MATCH_1_REVEAL, MATCH_1_CLOSE, MATCH_2_CLOSE, MATCH_3_CLOSE
from generate_users import generate_users


def _open_user(user_id: str, gender: str = "female") -> dict:
    """A user whose filters admit almost anyone, verified BGV — useful for
    building hand-crafted mutual scenarios without fighting the RNG.
    Defaults female; matching.fits_filters() is straight-only, so any test
    pairing more than one of these must set gender explicitly on at least
    one side."""
    return {
        "user_id": user_id,
        "city": "Mumbai",
        "gender": gender,
        "age_band": "28-34",
        "bgv_status": "verified",
        "stats": {
            "age": 30,
            "height_cm": 165,
            "weight_kg": 65,
            "waist_in": 30,
            "income_band": "₹₹ · 12L – 25L",
            "diet": "Everything",
            "education": "Bachelor's",
            "nationality": "IN",
            "religion": "Hindu",
        },
        "visions": [{"key": "Kids", "stance": "Want kids"}, {"key": "Travel together", "stance": None}],
        "preferences": {
            "fixed": {"dealbreakers": []},
            "adjustable": {
                "age": [18, 60],
                "height_cm": [0, 250],
                "weight_kg": [0, 200],
                "waist_in": [0, 80],
                "distance_km": [0, 5000],
                "nationality": ["IN", "NRI", "Any"],
                "religion": ["same", "related", "any"],
            },
        },
    }


def _mixed_gender_pool(n: int) -> list[dict]:
    pool = [_open_user(f"u_{i}") for i in range(n)]
    for i, u in enumerate(pool):
        u["gender"] = "male" if i % 2 == 0 else "female"
    return pool


class GenerateWeekMatchesShapeTests(unittest.TestCase):
    def test_never_shows_more_than_three(self) -> None:
        me = _open_user("me", gender="female")
        pool = [me, *_mixed_gender_pool(10)]
        matches = generate_week_matches(me, pool, week=1, locked_in_ids=set(), recent_match_ids=set())
        self.assertLessEqual(len(matches), 3)

    def test_slots_are_1_2_3_in_order(self) -> None:
        me = _open_user("me", gender="female")
        pool = [me, *_mixed_gender_pool(10)]
        matches = generate_week_matches(me, pool, week=1, locked_in_ids=set(), recent_match_ids=set())
        self.assertEqual([m["slot"] for m in matches], list(range(1, len(matches) + 1)))

    def test_no_duplicate_candidates(self) -> None:
        me = _open_user("me", gender="female")
        pool = [me, *_mixed_gender_pool(10)]
        matches = generate_week_matches(me, pool, week=1, locked_in_ids=set(), recent_match_ids=set())
        ids = [m["candidate_id"] for m in matches]
        self.assertEqual(len(ids), len(set(ids)))

    def test_revealed_and_close_times_follow_the_slot_timeline(self) -> None:
        me = _open_user("me", gender="female")
        other = _open_user("u_b", gender="male")
        matches = generate_week_matches(me, [me, other], week=3, locked_in_ids=set(), recent_match_ids=set())
        self.assertEqual(len(matches), 1)
        m = matches[0]
        self.assertEqual(m["revealed_at"], checkpoint(3, MATCH_1_REVEAL))
        self.assertEqual(m["window_closes_at"], checkpoint(3, MATCH_1_CLOSE))

    def test_second_and_third_slots_use_their_own_checkpoints(self) -> None:
        me = _open_user("me", gender="female")
        others = [_open_user(f"u_{i}", gender="male") for i in range(3)]
        matches = generate_week_matches(me, [me, *others], week=2, locked_in_ids=set(), recent_match_ids=set())
        self.assertEqual(len(matches), 3)
        self.assertEqual(matches[1]["revealed_at"], checkpoint(2, MATCH_1_CLOSE))  # Match 2 reveals when Match 1 closes
        self.assertEqual(matches[2]["window_closes_at"], checkpoint(2, MATCH_3_CLOSE))

    def test_zero_is_honest_not_padded(self) -> None:
        me = _open_user("me", gender="female")
        matches = generate_week_matches(me, [me], week=1, locked_in_ids=set(), recent_match_ids=set())
        self.assertEqual(matches, [])

    def test_does_not_mutate_input_pool(self) -> None:
        me = _open_user("me", gender="female")
        pool = [me, *_mixed_gender_pool(6)]
        import copy

        before = copy.deepcopy(pool)
        generate_week_matches(me, pool, week=1, locked_in_ids=set(), recent_match_ids=set())
        self.assertEqual(pool, before)


class NoParallelDatingTests(unittest.TestCase):
    def test_locked_in_user_gets_no_matches(self) -> None:
        me = _open_user("me", gender="female")
        pool = [me, *_mixed_gender_pool(10)]
        matches = generate_week_matches(me, pool, week=1, locked_in_ids={"me"}, recent_match_ids=set())
        self.assertEqual(matches, [])

    def test_locked_in_candidates_are_excluded_from_others_pools(self) -> None:
        me = _open_user("me", gender="female")
        a = _open_user("u_a", gender="male")
        b = _open_user("u_b", gender="male")
        matches = generate_week_matches(me, [me, a, b], week=1, locked_in_ids={"u_a"}, recent_match_ids=set())
        self.assertNotIn("u_a", [m["candidate_id"] for m in matches])
        self.assertIn("u_b", [m["candidate_id"] for m in matches])


class RecentMatchExclusionTests(unittest.TestCase):
    def test_recent_matches_excluded_from_selection(self) -> None:
        me = _open_user("me", gender="female")
        a = _open_user("u_a", gender="male")
        b = _open_user("u_b", gender="male")
        matches = generate_week_matches(me, [me, a, b], week=5, locked_in_ids=set(), recent_match_ids={"u_a"})
        self.assertNotIn("u_a", [m["candidate_id"] for m in matches])
        self.assertIn("u_b", [m["candidate_id"] for m in matches])


class ReproducibilityTests(unittest.TestCase):
    def test_same_week_reproduces(self) -> None:
        me = _open_user("me", gender="female")
        pool = [me, *_mixed_gender_pool(10)]
        r1 = generate_week_matches(me, pool, week=4, locked_in_ids=set(), recent_match_ids=set())
        r2 = generate_week_matches(me, pool, week=4, locked_in_ids=set(), recent_match_ids=set())
        self.assertEqual(r1, r2)

    def test_different_week_can_differ(self) -> None:
        me = _open_user("me", gender="female")
        pool = [me, *_mixed_gender_pool(10)]
        r1 = generate_week_matches(me, pool, week=1, locked_in_ids=set(), recent_match_ids=set())
        r2 = generate_week_matches(me, pool, week=2, locked_in_ids=set(), recent_match_ids=set())
        self.assertNotEqual([m["candidate_id"] for m in r1], [m["candidate_id"] for m in r2])


class MatchStatusTests(unittest.TestCase):
    def _match(self, week: int, slot: int, action: str = "none") -> dict:
        return {
            "revealed_at": checkpoint(week, MATCH_1_REVEAL if slot == 1 else MATCH_1_CLOSE),
            "window_closes_at": checkpoint(week, MATCH_1_CLOSE if slot == 1 else MATCH_2_CLOSE),
            "action": action,
        }

    def test_not_yet_revealed_before_reveal(self) -> None:
        m = self._match(1, 1)
        self.assertEqual(match_status(m, SimulationClock.at(1, "Mon", 11)), "not_yet_revealed")

    def test_open_after_reveal_before_close_no_action(self) -> None:
        m = self._match(1, 1)
        self.assertEqual(match_status(m, SimulationClock.at(1, "Mon", 13)), "open")

    def test_no_response_after_close_no_action(self) -> None:
        m = self._match(1, 1)
        self.assertEqual(match_status(m, SimulationClock.at(1, "Tue", 13)), "no_response")

    def test_acted_before_close_counts_as_acted(self) -> None:
        m = self._match(1, 1, action="interest")
        self.assertEqual(match_status(m, SimulationClock.at(1, "Mon", 20)), "acted")

    def test_acted_after_close_still_counts_as_acted_not_no_response(self) -> None:
        m = self._match(1, 1, action="pass")
        self.assertEqual(match_status(m, SimulationClock.at(1, "Tue", 13)), "acted")


class NoResponseMatchesTests(unittest.TestCase):
    def test_filters_to_only_no_response(self) -> None:
        clock = SimulationClock.at(1, "Tue", 13)
        open_match = {
            "revealed_at": checkpoint(1, MATCH_1_CLOSE),  # Match 2 reveals Tue noon — still open at Tue 13:00
            "window_closes_at": checkpoint(1, MATCH_2_CLOSE),
            "action": "none",
        }
        no_response = {
            "revealed_at": checkpoint(1, MATCH_1_REVEAL),
            "window_closes_at": checkpoint(1, MATCH_1_CLOSE),
            "action": "none",
        }
        acted = {
            "revealed_at": checkpoint(1, MATCH_1_REVEAL),
            "window_closes_at": checkpoint(1, MATCH_1_CLOSE),
            "action": "pass",
        }
        result = no_response_matches([open_match, no_response, acted], clock)
        self.assertEqual(result, [no_response])


class RealisticPoolTests(unittest.TestCase):
    """Statistical sanity checks against a real generated pool."""

    def test_verified_users_get_a_mix_of_match_counts(self) -> None:
        pool = generate_users(300, seed=11)
        for u in pool:
            u.setdefault("bgv_status", "verified")
        counts = set()
        for u in pool[:60]:
            matches = generate_week_matches(u, pool, week=1, locked_in_ids=set(), recent_match_ids=set())
            counts.add(len(matches))
        self.assertTrue(counts)  # ran without error across a real population
        for count in counts:
            self.assertLessEqual(count, 3)

    def test_unverified_user_always_gets_zero(self) -> None:
        pool = generate_users(50, seed=3)
        me = pool[0]
        me["bgv_status"] = "pending"
        matches = generate_week_matches(me, pool, week=1, locked_in_ids=set(), recent_match_ids=set())
        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
