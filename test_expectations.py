"""Tests for expectations.py — pacing the intimacy questions.

2026-09-09, user's rule: "We don't want to burden the user, not corner
them to answer, but help them pace out details to be answered."

The unit half is which question is showing and why. The route half is
whether the screen honours it, and whether a locked question actually
blocks anything (it must not — it decides what is SHOWN, nothing else).
"""

from __future__ import annotations

import unittest

import chemistry
import db
import expectations as e

from test_segment_efg_routes import RouteTestCase, app_module


PACE = {"intimacy_pace": "led_by_connection"}


class SequenceTests(unittest.TestCase):
    def test_nothing_but_the_pace_is_shown_first(self):
        self.assertEqual(e.visible_keys({}, None, 100), ["intimacy_pace"])

    def test_the_follow_ups_appear_once_a_pace_exists(self):
        keys = e.visible_keys(PACE, 100, 101)
        self.assertIn("intimacy_importance", keys)
        self.assertIn("intimacy_notes", keys)

    def test_how_much_it_matters_is_tied_to_the_pace(self):
        """user's rule: "'How much it matters to you' ... somehow seems
        misplaced. Doesn't tie it to Pace of physical intimacy."

        It cannot appear without one, which is what makes it a follow-up
        rather than a fifth unrelated question."""
        self.assertNotIn("intimacy_importance", e.visible_keys({}, None, 100))

    def test_health_waits_for_a_pace_and_then_a_day(self):
        self.assertFalse(e.health_open({}, None, 100))
        self.assertFalse(e.health_open(PACE, 100, 100))
        self.assertFalse(e.health_open(PACE, 100, 123))
        self.assertTrue(e.health_open(PACE, 100, 124))

    def test_it_says_how_long_is_left(self):
        self.assertEqual(e.hours_until_health(PACE, 100, 110), 14)
        self.assertIsNone(e.hours_until_health(PACE, 100, 130))

    def test_there_is_no_countdown_before_a_pace_is_set(self):
        """Nothing is waiting, so nothing should say it is."""
        self.assertIsNone(e.hours_until_health({}, None, 100))

    def test_an_answered_question_never_disappears(self):
        """Editing your own answer must not vanish on reload — showing it
        early is better than taking it away."""
        answered = {**PACE, "health_openness": "when_relevant"}
        self.assertTrue(e.health_open(answered, 100, 101))

    def test_an_unknown_clock_reads_as_not_yet(self):
        """Under-opening is the safe direction: the cost is a question
        arriving late, not one arriving uninvited."""
        self.assertFalse(e.health_open(PACE, None, 100))
        self.assertFalse(e.health_open(PACE, 100, None))

    def test_the_delay_survives_a_week_boundary(self):
        """The reason for the flat hour count. "Mon:12" cannot say WHICH
        Monday, so a pace set late on Sunday would otherwise look like it
        was answered in the future."""
        hours = lambda week, day_i, hour: (week - 1) * 24 * 7 + day_i * 24 + hour
        sunday_w1 = hours(1, 6, 22)     # Sun 22:00, week 1 — pace set
        monday_w2 = hours(2, 0, 8)      # Mon 08:00, week 2 — 10h later
        tuesday_w2 = hours(2, 1, 8)     # Tue 08:00, week 2 — 34h later

        # By day-of-week alone Monday looks EARLIER than Sunday, which is
        # how a week-less stamp gets the sign of the elapsed time wrong.
        self.assertLess(0, 6, "Mon:12 sorts before Sun:22 by day index")
        self.assertGreater(monday_w2, sunday_w1)

        self.assertFalse(e.health_open(PACE, sunday_w1, monday_w2))   # 10h
        self.assertTrue(e.health_open(PACE, sunday_w1, tuesday_w2))   # 34h


class ExpectationsScreenTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.make_user("u1"))
        self.make_user("u2")
        self.lock = self.make_lockin("u1", "u2")
        plan = self.make_plan(self.lock, status="confirmed")
        db.insert_row(self.conn, "DateOutcome", {
            "id": f"outcome:{plan}", "dateplan_id": plan, "happened": 1,
            "a_green_flags_json": "[]", "a_red_flags_json": "[]",
            "b_green_flags_json": "[]", "b_red_flags_json": "[]",
        })
        self.conn.commit()

    def page(self):
        return self.client.get("/expectations").get_data(as_text=True)

    def set_pace(self, value="slow"):
        self.client.post("/chemistry/set", data={
            "key": "intimacy_pace", "value": value, "back": "expectations_view"})

    def test_only_the_pace_question_is_on_the_first_visit(self):
        body = self.page()
        self.assertIn("Pace of physical intimacy", body)
        self.assertNotIn("How much does that matter", body)
        self.assertNotIn("Openness to discussing", body)

    def test_answering_the_pace_opens_its_follow_up_underneath_it(self):
        self.set_pace()
        body = self.page()
        self.assertIn("How much does that matter", body)
        self.assertIn("Because you chose", body)
        self.assertLess(body.index("Pace of physical intimacy"),
                        body.index("How much does that matter"))

    def test_the_health_question_is_not_there_the_same_day(self):
        self.set_pace()
        body = self.page()
        self.assertNotIn("Openness to discussing", body)
        self.assertIn("One more, tomorrow", body)

    def test_it_arrives_a_day_later(self):
        self.set_pace()
        self.set_clock(week=1, day="Tue", hour=13)
        body = self.page()
        self.assertIn("Openness to discussing", body)
        self.assertNotIn("One more, tomorrow", body)

    def test_a_pace_written_without_a_clock_does_not_open_it(self):
        """Rows predating the flat-hour column have no pacing clock. They
        read as "not yet" rather than throwing or opening early."""
        db.insert_row(self.conn, "ChemistryEntry", {
            "id": "u1:intimacy_pace", "user_id": "u1", "key": "intimacy_pace",
            "value": "slow", "updated_at": "Mon:12", "updated_at_hours": None})
        self.conn.commit()
        self.assertNotIn("Openness to discussing", self.page())

    def test_a_held_back_question_blocks_nothing_else(self):
        """A locked question is not a blocked user. It decides what the
        screen shows and nothing more."""
        self.set_pace()
        for path in ("/guru", "/after-date", "/week", "/escalations"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_the_screen_never_demands_an_answer(self):
        """user's rule: "not corner them to answer"."""
        body = self.page().lower()
        for word in ("required", "mandatory", "must answer", "you need to"):
            with self.subTest(word=word):
                self.assertNotIn(word, body)


if __name__ == "__main__":
    unittest.main()
