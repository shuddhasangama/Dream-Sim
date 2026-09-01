"""Tests for clock.py."""

from __future__ import annotations

import unittest

from clock import (
    CALENDAR_CLOSES,
    CALENDAR_OPENS,
    DATES_LIVE,
    FEEDBACK_OPENS,
    MATCH_1_CLOSE,
    MATCH_1_REVEAL,
    MATCH_2_CLOSE,
    MATCH_3_CLOSE,
    SimulationClock,
    checkpoint,
    phase,
)


class ConstructionTests(unittest.TestCase):
    def test_at_builds_from_day_name_and_hour(self) -> None:
        c = SimulationClock.at(3, "Wed", 18)
        self.assertEqual(c.week, 3)
        self.assertEqual(c.day, "Wed")
        self.assertEqual(c.hour, 18)

    def test_rejects_unknown_day(self) -> None:
        with self.assertRaises(ValueError):
            SimulationClock.at(1, "Someday", 12)

    def test_rejects_out_of_range_hour(self) -> None:
        with self.assertRaises(ValueError):
            SimulationClock.at(1, "Mon", 24)
        with self.assertRaises(ValueError):
            SimulationClock.at(1, "Mon", -1)


class StringRoundTripTests(unittest.TestCase):
    def test_str_and_parse_round_trip(self) -> None:
        c = SimulationClock.at(5, "Fri", 9)
        self.assertEqual(str(c), "Fri:09")
        self.assertEqual(SimulationClock.parse(5, str(c)), c)

    def test_parse_uses_the_given_week(self) -> None:
        c = SimulationClock.parse(7, "Mon:12")
        self.assertEqual(c.week, 7)
        self.assertEqual(c.day, "Mon")
        self.assertEqual(c.hour, 12)


class OrderingTests(unittest.TestCase):
    def test_later_day_same_week_is_greater(self) -> None:
        self.assertLess(SimulationClock.at(1, "Mon", 23), SimulationClock.at(1, "Tue", 0))

    def test_later_hour_same_day_is_greater(self) -> None:
        self.assertLess(SimulationClock.at(1, "Mon", 9), SimulationClock.at(1, "Mon", 10))

    def test_later_week_always_greater_regardless_of_day(self) -> None:
        self.assertLess(SimulationClock.at(1, "Sun", 23), SimulationClock.at(2, "Mon", 0))

    def test_equal_clocks_compare_equal(self) -> None:
        self.assertEqual(SimulationClock.at(2, "Wed", 12), SimulationClock.at(2, "Wed", 12))


class AdvanceHoursTests(unittest.TestCase):
    def test_advances_within_a_day(self) -> None:
        c = SimulationClock.at(1, "Mon", 10).advance_hours(2)
        self.assertEqual((c.week, c.day, c.hour), (1, "Mon", 12))

    def test_rolls_into_next_day(self) -> None:
        c = SimulationClock.at(1, "Mon", 23).advance_hours(2)
        self.assertEqual((c.week, c.day, c.hour), (1, "Tue", 1))

    def test_rolls_into_next_week_past_sunday(self) -> None:
        c = SimulationClock.at(1, "Sun", 23).advance_hours(2)
        self.assertEqual((c.week, c.day, c.hour), (2, "Mon", 1))

    def test_a_full_week_returns_to_the_same_day_hour_next_week(self) -> None:
        c = SimulationClock.at(1, "Wed", 14).advance_hours(24 * 7)
        self.assertEqual((c.week, c.day, c.hour), (2, "Wed", 14))


class TimelineCheckpointTests(unittest.TestCase):
    def test_match_1_reveals_monday_noon(self) -> None:
        self.assertEqual(checkpoint(4, MATCH_1_REVEAL), SimulationClock.at(4, "Mon", 12))

    def test_match_3_close_and_calendar_open_are_the_same_moment(self) -> None:
        # Both are "Wed evening" per §1's table.
        self.assertEqual(checkpoint(4, MATCH_3_CLOSE), checkpoint(4, CALENDAR_OPENS))
        self.assertEqual(checkpoint(4, CALENDAR_OPENS), SimulationClock.at(4, "Wed", 18))

    def test_full_week_order_is_strictly_increasing(self) -> None:
        points = [MATCH_1_REVEAL, MATCH_1_CLOSE, MATCH_2_CLOSE, MATCH_3_CLOSE, CALENDAR_CLOSES, DATES_LIVE, FEEDBACK_OPENS]
        clocks = [checkpoint(1, p) for p in points]
        self.assertEqual(clocks, sorted(set(clocks)))


class PhaseTests(unittest.TestCase):
    def test_before_monday_noon_is_before_week_start(self) -> None:
        self.assertEqual(phase(SimulationClock.at(1, "Mon", 11)), "before_week_start")

    def test_monday_noon_is_match_1_open(self) -> None:
        self.assertEqual(phase(SimulationClock.at(1, "Mon", 12)), "match_1_open")

    def test_tuesday_noon_is_match_2_open(self) -> None:
        self.assertEqual(phase(SimulationClock.at(1, "Tue", 12)), "match_2_open")

    def test_wednesday_noon_is_match_3_open(self) -> None:
        self.assertEqual(phase(SimulationClock.at(1, "Wed", 12)), "match_3_open")

    def test_wednesday_evening_is_calendar_open(self) -> None:
        self.assertEqual(phase(SimulationClock.at(1, "Wed", 18)), "calendar_open")

    def test_thursday_noon_is_calendar_closed(self) -> None:
        self.assertEqual(phase(SimulationClock.at(1, "Thu", 12)), "calendar_closed")

    def test_thursday_evening_is_dates_live(self) -> None:
        self.assertEqual(phase(SimulationClock.at(1, "Thu", 18)), "dates_live")

    def test_sunday_night_is_feedback_open(self) -> None:
        self.assertEqual(phase(SimulationClock.at(1, "Sun", 21)), "feedback_open")

    def test_saturday_stays_dates_live(self) -> None:
        self.assertEqual(phase(SimulationClock.at(1, "Sat", 12)), "dates_live")

    def test_phase_is_week_relative_not_absolute(self) -> None:
        # Week 5's Monday noon is still match_1_open, same as week 1's.
        self.assertEqual(phase(SimulationClock.at(5, "Mon", 12)), "match_1_open")


if __name__ == "__main__":
    unittest.main()
