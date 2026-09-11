"""THE WEEK agrees with the clock.

2026-09-10, user's rule: show "the Calendar process which is available in
the mock-up to give the brief summary of the calendar days and respective
stages."

The one thing that can go wrong here is the grid becoming a second copy
of the timeline and drifting from the first. These tests hold it to
clock.py.
"""

from __future__ import annotations

import unittest

import clock as clock_module
import week_map


class DerivedFromTheClockTests(unittest.TestCase):

    CHECKPOINTS = {
        "match_1": clock_module.MATCH_1_REVEAL,
        "match_2": clock_module.MATCH_2_REVEAL,
        "match_3": clock_module.MATCH_3_REVEAL,
        "slots": clock_module.CALENDAR_OPENS,
        "calendar_closes": clock_module.CALENDAR_CLOSES,
        "sign": clock_module.DATES_LIVE,
        "feedback": clock_module.FEEDBACK_OPENS,
    }

    def moments(self):
        return {m["key"]: m for m in week_map.MOMENTS}

    def test_every_scheduled_moment_matches_the_clock(self):
        found = self.moments()
        for key, checkpoint in self.CHECKPOINTS.items():
            with self.subTest(key=key):
                self.assertIn(key, found)
                self.assertEqual(found[key]["at"], checkpoint)

    def test_every_moment_falls_on_a_real_day_and_hour(self):
        for m in week_map.MOMENTS:
            day, hour = m["at"]
            with self.subTest(key=m["key"]):
                self.assertIn(day, clock_module.DAYS_OF_WEEK)
                self.assertTrue(0 <= hour < 24)

    def test_every_phase_has_a_sentence(self):
        for phase in clock_module.PHASES:
            with self.subTest(phase=phase):
                self.assertTrue(week_map.phase_copy(phase))


class GridTests(unittest.TestCase):

    def grid(self, day="Mon", hour=13):
        return week_map.grid(clock_module.SimulationClock.at(1, day, hour))

    def test_seven_days_and_four_bands(self):
        g = self.grid()
        self.assertEqual([d["day"] for d in g["days"]], clock_module.DAYS_OF_WEEK)
        self.assertEqual([r["label"] for r in g["rows"]], ["MORN", "AFT", "EVE", "NIGHT"])

    def test_matches_land_in_the_afternoon_band(self):
        """They reveal at midday, so they belong below the midday line."""
        aft = {r["key"]: r for r in self.grid()["rows"]}["aft"]
        by_day = {d["day"]: [m["label"] for m in d["moments"]] for d in aft["days"]}
        self.assertIn("Match 1", by_day["Mon"])
        self.assertIn("Match 2", by_day["Tue"])
        self.assertIn("Match 3", by_day["Wed"])

    def test_today_is_marked(self):
        g = self.grid(day="Thu")
        self.assertEqual([d["day"] for d in g["days"] if d["is_today"]], ["Thu"])

    def test_what_is_behind_you_is_marked_past(self):
        g = self.grid(day="Wed", hour=13)
        past = {m["key"] for row in g["rows"] for d in row["days"]
                for m in d["moments"] if m["past"]}
        self.assertIn("match_1", past)          # Monday
        self.assertNotIn("feedback", past)      # Sunday

    def test_nothing_is_lost_between_the_table_and_the_grid(self):
        g = self.grid()
        placed = sum(len(d["moments"]) for row in g["rows"] for d in row["days"])
        self.assertEqual(placed, len(week_map.MOMENTS))

    def test_the_legend_covers_every_tone_used(self):
        tones_used = {m["tone"] for m in week_map.MOMENTS}
        tones_shown = {e["tone"] for e in week_map.legend()}
        self.assertTrue(tones_shown <= tones_used)

    def test_the_explanations_are_in_the_order_they_happen(self):
        order = clock_module.DAYS_OF_WEEK
        keys = [(order.index(m["at"][0]), m["at"][1]) for m in week_map.explained()]
        self.assertEqual(keys, sorted(keys))

    def test_it_works_with_no_clock_at_all(self):
        """The grid is also a static timetable — nothing should require
        knowing what time it is."""
        g = week_map.grid(None)
        self.assertFalse(any(d["is_today"] for d in g["days"]))


if __name__ == "__main__":
    unittest.main()
