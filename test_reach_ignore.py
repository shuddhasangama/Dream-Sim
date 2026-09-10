"""Setting a filter to "any".

2026-09-10, user's rule: "Can we have ignore/showall option in REACH - so
that some filters are ignored and the answer can be any. Like religion,
budget, Nationality, smoking etc."

Two things this has to be true about, and the second is the one that
would quietly ruin someone's account:

* ignoring actually widens the pool; and
* ignoring **never deletes** the range or the dealbreaker underneath it,
  so switching it back on returns exactly what the person had set.

There is also an honest measurement here that the screen depends on:
`delta_if_ignored` is computed mutually, so it can never promise more
people than would really appear.
"""

from __future__ import annotations

import itertools
import json
import unittest

import db
import generate_users
import matching
from test_segment_efg_routes import RouteTestCase, app_module


def _pair():
    a = {"user_id": "a", "gender": "female", "city": "Bengaluru",
         "stats": {"age": 30, "religion": "Hindu", "nationality": "IN",
                   "smoking": "Regular", "drinking": "Daily", "diet": "Everything"},
         "visions": [],
         "preferences": {"fixed": {"dealbreakers": []},
                         "adjustable": {"age": [28, 34], "distance_km": [0, 50],
                                        "religion": ["same"], "nationality": ["IN"]}}}
    b = {"user_id": "b", "gender": "male", "city": "Bengaluru",
         "stats": {"age": 40, "religion": "Christian", "nationality": "US",
                   "smoking": "Regular", "drinking": "Daily", "diet": "Everything"},
         "visions": [],
         "preferences": {"fixed": {"dealbreakers": []},
                         "adjustable": {"age": [18, 70], "distance_km": [0, 1600]}}}
    return a, b


class IgnoreModelTests(unittest.TestCase):
    def test_nothing_is_ignored_by_default(self):
        a, _ = _pair()
        self.assertEqual(matching.ignored_set(a["preferences"]), set())

    def test_a_row_written_before_today_reads_as_nothing_ignored(self):
        """The preferences JSON on every existing user has no "ignored"
        key at all. That must mean "filtering normally", not crash."""
        for shape in ({}, {"adjustable": {}}, {"ignored": None}, {"ignored": "religion"}):
            with self.subTest(shape=shape):
                self.assertIsInstance(matching.ignored_set(shape), set)

    def test_an_unknown_name_is_dropped_rather_than_trusted(self):
        self.assertEqual(matching.ignored_set({"ignored": ["not_a_filter"]}), set())

    def test_gender_cannot_be_ignored(self):
        a, b = _pair()
        with self.assertRaises(ValueError):
            matching.set_ignored(a, "gender", True)

    def test_ignoring_a_lever_lets_a_candidate_through(self):
        a, b = _pair()
        self.assertFalse(matching.fits_filters(a, b))          # age, religion, nationality
        opened = a
        for name in ("age", "religion", "nationality"):
            opened = matching.set_ignored(opened, name, True)
        self.assertTrue(matching.fits_filters(opened, b))

    def test_ignoring_does_not_delete_the_range(self):
        """The rule that makes this safe to offer as one click."""
        a, _ = _pair()
        off = matching.set_ignored(a, "age", True)
        self.assertEqual(off["preferences"]["adjustable"]["age"], [28, 34])
        back = matching.set_ignored(off, "age", False)
        self.assertEqual(back["preferences"]["adjustable"]["age"], [28, 34])
        self.assertEqual(matching.ignored_set(back["preferences"]), set())

    def test_show_all_and_put_it_back(self):
        a, b = _pair()
        everything = matching.set_ignored_all(a, True)
        self.assertTrue(matching.fits_filters(everything, b))
        restored = matching.set_ignored_all(everything, False)
        self.assertFalse(matching.fits_filters(restored, b))
        self.assertEqual(restored["preferences"]["adjustable"],
                         a["preferences"]["adjustable"])

    def test_show_all_still_cannot_cross_gender(self):
        a, _ = _pair()
        same_gender = {**_pair()[1], "gender": "female"}
        self.assertFalse(matching.fits_filters(matching.set_ignored_all(a, True), same_gender))

    def test_the_original_user_dict_is_not_mutated(self):
        a, _ = _pair()
        matching.set_ignored(a, "age", True)
        self.assertNotIn("ignored", a["preferences"])

    def test_active_filter_names_reflects_what_is_switched_off(self):
        a, _ = _pair()
        a["preferences"]["fixed"]["dealbreakers"] = ["non_smoker"]
        self.assertIn("non_smoker", matching.active_filter_names(a))
        off = matching.set_ignored(a, "non_smoker", True)
        self.assertNotIn("non_smoker", matching.active_filter_names(off))


class FilterStateTests(unittest.TestCase):
    """The numbers the screen puts next to each switch."""

    def setUp(self):
        self.pool = [u for u in generate_users.generate_users(60, seed=9)
                     if u.get("bgv_status") == "verified"]
        self.me = self.pool[0]

    def test_every_filter_the_person_has_is_listed(self):
        names = {f["name"] for f in matching.filter_states(self.me, self.pool)}
        for lever in ("age", "distance_km", "religion", "nationality"):
            self.assertIn(lever, names)

    def test_the_delta_is_measured_mutually_not_one_sided(self):
        """The honest half. Whatever the row claims must be exactly what
        appears if the person actually flips the switch."""
        others = [u for u in self.pool if u["user_id"] != self.me["user_id"]]
        before = sum(1 for c in others if matching.mutual_open(self.me, c))
        for entry in matching.filter_states(self.me, self.pool):
            with self.subTest(filter=entry["name"]):
                flipped = matching.set_ignored(self.me, entry["name"], True)
                after = sum(1 for c in others if matching.mutual_open(flipped, c))
                self.assertEqual(entry["delta_if_ignored"], after - before)

    def test_a_delta_is_never_negative_for_an_active_filter(self):
        for entry in matching.filter_states(self.me, self.pool):
            if not entry["ignored"]:
                self.assertGreaterEqual(entry["delta_if_ignored"], 0, entry["name"])

    def test_sensitive_levers_are_marked_so_the_screen_can_say_so(self):
        marked = {f["name"] for f in matching.filter_states(self.me, self.pool) if f["sensitive"]}
        self.assertEqual(marked, {"religion", "nationality"})

    def test_widening_is_not_offered_for_a_filter_already_set_to_any(self):
        """A Widen button on an ignored lever is a control that does
        nothing."""
        off = matching.set_ignored(self.me, "religion", True)
        levers = {d["lever"] for d in matching.whatif_deltas(off, self.pool)}
        self.assertNotIn("religion", levers)


class IgnoreRouteTests(RouteTestCase):
    def seed(self, n=20):
        for u in generate_users.generate_users(n, seed=9):
            row = app_module.onboarding.build_user_row(
                user_id=u["user_id"], city=u["city"], gender=u["gender"],
                stats=u["stats"], visions=u["visions"], activities={})
            row["bgv_status"] = "verified"
            row["journey_state"] = "dating"
            row["preferences_json"] = json.dumps(u["preferences"], ensure_ascii=False)
            db.insert_row(self.conn, "User", row)
        self.conn.commit()

    def register(self):
        c = self.client
        c.post("/signup", data={"email": "me@x.com"})
        c.post("/onboarding/vision", data={
            "intimacy_kinds": ["Emotional", "Physical"],
            "other_keys": ["Kids"], "kids_route": ["Naturally"]})
        c.post("/onboarding/stats", data={
            "city": "Bangalore", "gender": "female", "age": "31",
            "education": "Master's", "nationality": "IN",
            "profession": "Engineering", "salary": "1800000",
            "diet": "Everything", "religion": "Hindu",
            "languages": ["English"], "cuisine": ["Thai"], "ethnicity": ["Indian"]})
        c.post("/onboarding/chemistry", data={
            "act__Cooking": "good", "act__Yoga": "improve",
            "act__Tennis": "maybe", "act__Salsa": "no"})
        c.post("/onboarding/finish")
        with c.session_transaction() as sess:
            return sess["user_id"]

    def test_the_panel_renders_on_reach(self):
        self.seed()
        self.register()
        body = self.client.get("/reach").get_data(as_text=True)
        self.assertIn("What you are filtering on", body)
        self.assertIn("Show everyone", body)

    def test_setting_one_to_any_is_saved(self):
        self.seed()
        user_id = self.register()
        response = self.client.post("/reach/ignore",
                                    json={"filter": "religion", "ignore": True})
        self.assertEqual(response.status_code, 200)

        stored = json.loads(dict(db.fetch_one(self.conn, "User", id=user_id))
                            ["preferences_json"])
        self.assertIn("religion", stored["ignored"])
        self.assertEqual(response.get_json()["ignored_count"], 1)

    def test_switching_it_back_restores_the_range_untouched(self):
        self.seed()
        user_id = self.register()
        before = json.loads(dict(db.fetch_one(self.conn, "User", id=user_id))
                            ["preferences_json"])["adjustable"]
        self.client.post("/reach/ignore", json={"filter": "age", "ignore": True})
        self.client.post("/reach/ignore", json={"filter": "age", "ignore": False})
        after = json.loads(dict(db.fetch_one(self.conn, "User", id=user_id))
                           ["preferences_json"])["adjustable"]
        self.assertEqual(before, after)

    def test_show_all_switches_every_filter_off(self):
        self.seed()
        self.register()
        payload = self.client.post("/reach/show-all", json={"ignore": True}).get_json()
        self.assertTrue(payload["all_ignored"])
        self.assertTrue(all(f["ignored"] for f in payload["filters"]))

    def test_show_all_widens_the_pool(self):
        self.seed()
        self.register()
        before = self.client.post("/reach/ignore",
                                  json={"filter": "age", "ignore": False}).get_json()
        after = self.client.post("/reach/show-all", json={"ignore": True}).get_json()
        self.assertGreaterEqual(after["counts"]["fits_user_filters"],
                                before["counts"]["fits_user_filters"])

    def test_an_unknown_filter_is_refused(self):
        self.seed()
        self.register()
        response = self.client.post("/reach/ignore",
                                    json={"filter": "gender", "ignore": True})
        self.assertEqual(response.status_code, 400)

    def test_reach_still_opens_with_everything_ignored(self):
        """The whole-pool scans run over more people in this state, which
        is exactly when a missing-stat crash would surface."""
        self.seed()
        self.register()
        self.client.post("/reach/show-all", json={"ignore": True})
        self.assertEqual(self.client.get("/reach").status_code, 200)
        self.assertEqual(self.client.get("/week").status_code, 200)


if __name__ == "__main__":
    unittest.main()
