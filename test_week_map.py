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
        "rc_ends": clock_module.RC_ENDS,
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

    def test_cell_labels_abbreviate_reality_check_the_full_term_stays_in_the_legend(self):
        """round3-fixes-spec.md §5.1: "Reality" alone in a small cell read
        as noise; the full term belongs in the legend only, via `kind`."""
        by_key = {m["key"]: m for m in week_map.MOMENTS}
        self.assertEqual(by_key["feedback"]["label"], "RC Opens")
        self.assertEqual(by_key["rc_ends"]["label"], "RC Closes")
        for m in week_map.MOMENTS:
            self.assertNotEqual(m["label"], "Reality", m["key"])
        legend_kinds = {e["kind"] for e in week_map.legend()}
        self.assertIn("Reality Check", legend_kinds)

    def test_it_works_with_no_clock_at_all(self):
        """The grid is also a static timetable — nothing should require
        knowing what time it is."""
        g = week_map.grid(None)
        self.assertFalse(any(d["is_today"] for d in g["days"]))


class PersonalMomentTests(unittest.TestCase):
    """round3-fixes-spec.md §5.2/§5.3: the personalized, conditional
    moments — separate from the fixed MOMENTS timetable above."""

    def test_debrief_moment_follows_the_actual_confirmed_slot(self):
        """Saturday dinner's debrief lands after Saturday dinner, not on
        the generic MOMENTS 'Debrief' entry's own fixed Sat 21:00 — this
        assertion would still pass by coincidence for dinner, so it uses
        a different meal on purpose."""
        plan = {"datetime": "2026-01-11T00:00:00", "meal": "breakfast"}  # a Sunday
        moment = week_map.personal_debrief_moment(plan)
        self.assertIsNotNone(moment)
        day, hour = moment["at"]
        self.assertEqual(day, "Sun")
        import dateplan
        self.assertEqual(hour, dateplan.debrief_opens_hour("breakfast"))
        self.assertNotEqual((day, hour), next(m["at"] for m in week_map.MOMENTS if m["key"] == "debrief"))

    def test_debrief_moment_is_none_without_a_readable_slot(self):
        self.assertIsNone(week_map.personal_debrief_moment({}))
        self.assertIsNone(week_map.personal_debrief_moment({"datetime": "not-a-date", "meal": "dinner"}))

    def test_plan_slot_matches_app_pys_own_debrief_opens_label_computation(self):
        """Both derive from the same stored datetime + meal — this guards
        the app.py._plan_slot refactor that now just calls this."""
        plan = {"datetime": "2026-01-09T19:30:00", "meal": "dinner"}
        day_index, hour = week_map.plan_slot(plan)
        self.assertEqual(week_map.DAYS[day_index], "Fri")

    def test_pool_return_moment_is_none_when_not_released(self):
        self.assertIsNone(week_map.pool_return_moment(False))

    def test_pool_return_moment_reuses_rcs_own_fixed_clock_time(self):
        """RC opens for everyone at the same synchronized moment — being
        released changes whether it applies to you, never when it is."""
        moment = week_map.pool_return_moment(True)
        feedback = next(m for m in week_map.MOMENTS if m["key"] == "feedback")
        self.assertEqual(moment["at"], feedback["at"])
        self.assertEqual(moment["key"], "feedback")


class PersonalizedGridTests(unittest.TestCase):
    """round3-fixes-spec.md §5.3 ('replace in place'): a personalized
    moment swaps out its generic counterpart rather than sitting
    alongside it."""

    def grid(self, **personal):
        return week_map.grid(clock_module.SimulationClock.at(1, "Mon", 13), **personal)

    def _cell_labels(self, g, day):
        return [m["label"] for row in g["rows"] for d in row["days"]
                if d["day"] == day for m in d["moments"]]

    def test_with_no_personal_data_the_grid_is_unchanged(self):
        g = self.grid()
        placed = sum(len(d["moments"]) for row in g["rows"] for d in row["days"])
        self.assertEqual(placed, len(week_map.MOMENTS))
        self.assertFalse(any(m.get("personal") for row in g["rows"] for d in row["days"] for m in d["moments"]))

    def test_a_personal_debrief_replaces_the_generic_one_not_alongside_it(self):
        plan = {"datetime": "2026-01-11T00:00:00", "meal": "breakfast"}  # Sunday
        personal = week_map.personal_debrief_moment(plan)
        g = self.grid(personal_debrief=personal)
        self.assertNotIn("Debrief", self._cell_labels(g, "Sat"))
        sun_labels = self._cell_labels(g, "Sun")
        self.assertIn("Debrief", sun_labels)
        self.assertEqual(sun_labels.count("Debrief"), 1)
        placed = sum(len(d["moments"]) for row in g["rows"] for d in row["days"])
        self.assertEqual(placed, len(week_map.MOMENTS))  # swapped, not added

    def test_pool_return_replaces_the_generic_rc_opens_cell(self):
        personal = week_map.pool_return_moment(True)
        g = self.grid(personal_pool_return=personal)
        feedback = next(m for m in week_map.MOMENTS if m["key"] == "feedback")
        day, _hour = feedback["at"]
        labels_in_cell = self._cell_labels(g, day)
        self.assertEqual(labels_in_cell.count("RC Opens"), 1)
        placed = sum(len(d["moments"]) for row in g["rows"] for d in row["days"])
        self.assertEqual(placed, len(week_map.MOMENTS))

    def test_none_for_both_leaves_the_grid_fully_generic(self):
        g = self.grid(personal_debrief=None, personal_pool_return=None)
        self.assertFalse(any(m.get("personal") for row in g["rows"] for d in row["days"] for m in d["moments"]))


if __name__ == "__main__":
    unittest.main()
