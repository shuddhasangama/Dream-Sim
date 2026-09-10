"""A match's name is hidden until the two of them have actually met.

2026-09-09 (evening), user's rule: "the match names to be not visible
until after the date feedback is provided and lock-in."

Nothing enforced this. An audit found NO masking anywhere: a candidate's
name sat on the weekly match card directly above the Pass / Express
interest buttons — somebody the viewer has no relationship with at all —
and stayed visible on every screen after it.

The line is per PAIR, not per person: having met one match must not
reveal the next one's name.
"""

from __future__ import annotations

import unittest

import db

from test_segment_efg_routes import RouteTestCase, app_module


class MaskingTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.make_user("u1"))
        self.make_user("u2")
        self.lock = self.make_lockin("u1", "u2")
        self.their_name = app_module.display_name("u2", "female")

    def body(self, path):
        return self.client.get(path).get_data(as_text=True)

    def complete_a_date(self):
        plan = self.make_plan(self.lock, status="confirmed")
        db.insert_row(self.conn, "DateOutcome", {
            "id": f"o:{plan}", "dateplan_id": plan, "happened": 1,
            "a_green_flags_json": "[]", "a_red_flags_json": "[]",
            "b_green_flags_json": "[]", "b_red_flags_json": "[]"})
        self.conn.commit()
        return plan

    def test_a_locked_in_partner_has_no_name_before_the_date(self):
        self.assertNotIn(self.their_name, self.body("/week"))
        self.assertIn("Your match", self.body("/week"))

    def test_nor_on_the_calendar_or_the_plan(self):
        self.make_plan(self.lock, status="confirmed")
        for path in ("/calendar", "/plan"):
            with self.subTest(path=path):
                self.assertNotIn(self.their_name, self.body(path))

    def test_the_name_appears_once_the_feedback_exists(self):
        self.complete_a_date()
        self.assertIn(self.their_name, self.body("/after-date"))

    def test_meeting_one_match_does_not_reveal_another(self):
        """The rule is per pair. This is the mistake a per-USER milestone
        check would make — FIRST_DATE is true of the person, not of the
        pairing."""
        self.complete_a_date()
        self.make_user("u3")
        stranger = app_module.display_name("u3", "female")
        with app_module.app.test_request_context("/week"):
            from flask import session
            session["user_id"] = "u1"
            self.assertTrue(app_module._have_met("u1", "u2"))
            self.assertFalse(app_module._have_met("u1", "u3"))
        self.assertNotIn(stranger, self.body("/week"))

    def test_masking_hides_a_name_and_nothing_else(self):
        """The profile is the point of the screen. Only the name goes."""
        with app_module.app.test_request_context("/week"):
            from flask import session
            session["user_id"] = "u1"
            other = app_module.load_user("u2")
            shown = app_module.named_for("u1", other)
        self.assertEqual(shown["name"], app_module.MASKED_NAME)
        self.assertEqual(shown["stats"], other["stats"])
        self.assertEqual(shown["visions"], other["visions"])

    def test_your_own_name_is_always_yours(self):
        with app_module.app.test_request_context("/week"):
            from flask import session
            session["user_id"] = "u1"
            self.assertTrue(app_module._have_met("u1", "u1"))

    def test_the_rule_can_be_relaxed_with_one_constant(self):
        """Documented escape hatch — this is a product stance, not a
        security boundary, and it should be one line to move."""
        original = app_module.NAMES_BEFORE_MEETING
        app_module.NAMES_BEFORE_MEETING = True
        self.addCleanup(setattr, app_module, "NAMES_BEFORE_MEETING", original)
        self.assertIn(self.their_name, self.body("/week"))


if __name__ == "__main__":
    unittest.main()
