"""Tests for stats_edit.py — which stats can change, and when.

2026-09-09, user's rule: "This should be editable until there is no
matches available or keenness expressed. Cause we don't want stats to
change between the match and date... While they are in relationship or
dating stats can change. Which can be captured and also notified to
their match."

Two decisions were taken with the user before this was built:
  * a live match freezes only the stats a candidate can SEE or FILTER on
  * BGV-verified fields are not editable in-app at all
"""

from __future__ import annotations

import pathlib
import unittest

import db
import matching
import onboarding
import stats_edit as se

from test_segment_efg_routes import RouteTestCase, app_module


QUIET = se.situation()
LIVE = se.situation(live_match=True)
KEEN = se.situation(keenness=True)
COUPLE = se.situation(in_relationship=True)


class GroupTests(unittest.TestCase):
    def test_the_groups_do_not_overlap(self):
        self.assertEqual(set(se.VERIFIED) & set(se.EDITABLE), set())
        self.assertEqual(set(se.CANDIDATE_FACING) & set(se.FREE), set())

    def test_every_verified_field_is_one_bgv_actually_checks(self):
        """A field claimed as verified that BGV never looks at would be a
        lock with nothing behind it."""
        labels = {l.lower() for l in onboarding.MANDATORY_FIELD_LABELS}
        for field in se.VERIFIED:
            with self.subTest(field=field):
                stem = field.replace("income_band", "salary")
                self.assertIn(stem, labels)

    def test_everything_a_candidate_filters_on_is_candidate_facing(self):
        """The freeze exists because someone screens you on these. A
        REACH lever missing from the list would be a stat you could
        change while a candidate was filtering on it."""
        soft_levers = [l for l in matching.LEVERS
                       if l not in se.VERIFIED and l != "distance_km"]
        for lever in soft_levers:
            with self.subTest(lever=lever):
                self.assertIn(lever, se.CANDIDATE_FACING)


class WhenTests(unittest.TestCase):
    def yes(self, field, state):
        return se.editable(field, state)["editable"]

    def test_a_verified_field_is_never_editable(self):
        """Not even in a relationship — being exclusive does not make a
        badge retypeable."""
        for state in (QUIET, LIVE, KEEN, COUPLE):
            for field in se.VERIFIED:
                with self.subTest(field=field, state=state):
                    self.assertFalse(self.yes(field, state))

    def test_a_quiet_week_opens_everything_soft(self):
        for field in se.EDITABLE:
            with self.subTest(field=field):
                self.assertTrue(self.yes(field, QUIET))

    def test_a_live_match_freezes_only_what_they_can_see(self):
        """The decision taken with the user: per-field, not all-or-nothing."""
        for field in se.CANDIDATE_FACING:
            with self.subTest(frozen=field):
                self.assertFalse(self.yes(field, LIVE))
        for field in se.FREE:
            with self.subTest(open=field):
                self.assertTrue(self.yes(field, LIVE))

    def test_weight_and_waist_freeze_because_they_are_filtered_on(self):
        """The user's own example — someone working on their diet. Those
        two are REACH range levers, so a candidate screens on them, so
        they hold while a window is open. They reopen after it closes."""
        for field in ("weight_kg", "waist_in"):
            with self.subTest(field=field):
                self.assertFalse(self.yes(field, LIVE))
                self.assertTrue(self.yes(field, QUIET))

    def test_keenness_freezes_everything_soft(self):
        """"we don't want stats to change between the match and date"."""
        for field in se.EDITABLE:
            with self.subTest(field=field):
                self.assertFalse(self.yes(field, KEEN))

    def test_a_relationship_opens_it_all_again(self):
        for field in se.EDITABLE:
            with self.subTest(field=field):
                self.assertTrue(self.yes(field, COUPLE))

    def test_only_a_relationship_discloses(self):
        self.assertTrue(se.discloses_to_partner(COUPLE))
        for state in (QUIET, LIVE, KEEN):
            self.assertFalse(se.discloses_to_partner(state))

    def test_every_refusal_says_why(self):
        """A field that is simply not there reads as a bug."""
        for state in (LIVE, KEEN, COUPLE, QUIET):
            for row in se.rows({}, state):
                if not row["editable"]:
                    with self.subTest(field=row["key"]):
                        self.assertTrue(row["reason"])

    def test_a_disclosed_change_records_both_sides_of_it(self):
        row = se.change_record("u1", "diet", "vegetarian", "vegan", "Mon:12")
        self.assertEqual((row["from_value"], row["to_value"]), ("vegetarian", "vegan"))
        self.assertEqual(row["disclosed_to_partner"], 1)


class StatsScreenTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.make_user("u1"))

    def test_the_screen_exists_at_all(self):
        """The user's report: there was no way to edit or update Stats."""
        self.assertEqual(self.client.get("/stats").status_code, 200)

    def test_reach_sends_you_here_and_not_to_vision(self):
        """user's rule: the REACH link took you to Vision, which is not
        correct \u2014 Vision has none of these fields on it."""
        # Asserted against the template rather than a render: the route
        # test fixture has no REACH preferences, and the claim here is
        # about which endpoint the link names.
        source = pathlib.Path("templates/reach.html").read_text(encoding="utf-8")
        link = source[source.index("Add the missing stats") - 160:
                      source.index("Add the missing stats")]
        self.assertIn("stats_view", link)
        self.assertNotIn("vision_view", link)

    def test_a_soft_stat_saves(self):
        self.client.post("/stats/set", data={"field": "smoking", "value": "never"})
        row = dict(db.fetch_one(self.conn, "User", id="u1"))
        import json
        self.assertEqual(json.loads(row["stats_json"]).get("smoking"), "never")

    def test_a_verified_stat_is_refused_by_the_route(self):
        """Re-checked server-side. A disabled input is a suggestion."""
        import json
        before = json.loads(dict(db.fetch_one(self.conn, "User", id="u1"))["stats_json"])
        self.client.post("/stats/set", data={"field": "profession", "value": "Astronaut"})
        after = json.loads(dict(db.fetch_one(self.conn, "User", id="u1"))["stats_json"])
        self.assertEqual(before.get("profession"), after.get("profession"))

    def test_a_refusal_says_why_on_the_screen(self):
        self.client.post("/stats/set", data={"field": "profession", "value": "Astronaut"})
        self.assertIn("form-error", self.client.get("/stats").get_data(as_text=True))

    def test_held_fields_are_shown_rather_than_hidden(self):
        body = self.client.get("/stats").get_data(as_text=True)
        self.assertIn("Held right now", body)
        self.assertIn("Profession", body)


if __name__ == "__main__":
    unittest.main()
