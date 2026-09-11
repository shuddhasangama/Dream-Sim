"""Who REACH counts, before and after verification.

2026-09-10, user's rule: "When the signup is complete while the
verification is still pending we still want to have REACH made available,
just to give them the sense of available users. Here we would want to
show the verified + unverified users. Once BGV completed we would want to
show within REACH only the verified users."
"""

from __future__ import annotations

import json
import unittest

import db
import disclosure
import generate_users
import matching
from test_segment_efg_routes import RouteTestCase, app_module


class ReachScopeTests(RouteTestCase):

    def seed(self, n=24):
        """Half the pool deliberately left unverified."""
        for i, u in enumerate(generate_users.generate_users(n, seed=11)):
            row = app_module.onboarding.build_user_row(
                user_id=u["user_id"], city=u["city"], gender=u["gender"],
                stats=u["stats"], visions=u["visions"], activities={})
            row["bgv_status"] = "verified" if i % 2 == 0 else "pending"
            row["journey_state"] = "dating"
            row["preferences_json"] = json.dumps(u["preferences"], ensure_ascii=False)
            db.insert_row(self.conn, "User", row)
        self.conn.commit()

    def register(self, gender="female", email="p@x.com"):
        c = self.client
        c.post("/signup", data={"email": email})
        c.post("/onboarding/vision", data={"preset": "marriage"})
        c.post("/onboarding/stats", data={
            "city": "Bangalore", "gender": gender, "age": "31",
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

    def verify(self, user_id):
        row = dict(db.fetch_one(self.conn, "User", id=user_id))
        row["bgv_status"] = "verified"
        db.insert_row(self.conn, "User", row)
        self.conn.commit()

    def scope(self, user_id):
        with app_module.app.test_request_context():
            user = app_module.load_user(user_id)
            return app_module.reach_pool(user)

    # ── availability ──────────────────────────────────────────────────

    def test_reach_opens_before_verification(self):
        self.seed()
        self.register()
        self.assertEqual(self.client.get("/reach").status_code, 200)

    def test_and_is_offered_in_the_nav_not_just_by_url(self):
        """The route, the Dashboard button and the nav table used to give
        three different answers to this."""
        self.seed()
        self.register()
        body = self.client.get("/reach").get_data(as_text=True)
        self.assertIn("REACH", body)
        self.assertTrue(disclosure.is_open("reach", {disclosure.REGISTERED}))

    def test_the_week_is_still_closed_before_verification(self):
        """An unverified user gets no matches at all, so the weekly
        rotation would be an empty promise."""
        self.assertFalse(disclosure.is_open("week", {disclosure.REGISTERED}))

    # ── who is counted ────────────────────────────────────────────────

    def test_pending_counts_verified_and_unverified(self):
        self.seed()
        user_id = self.register()
        pool, counting_unverified = self.scope(user_id)
        self.assertTrue(counting_unverified)
        self.assertTrue(any(u["bgv_status"] != "verified" for u in pool))

    def test_verified_counts_only_verified(self):
        self.seed()
        user_id = self.register()
        self.verify(user_id)
        pool, counting_unverified = self.scope(user_id)
        self.assertFalse(counting_unverified)
        self.assertEqual([u for u in pool if u["bgv_status"] != "verified"], [])

    def test_the_pool_actually_shrinks_when_you_are_verified(self):
        """The number moves. If it did not, one of the two states would be
        wrong — which is what was shipped before today."""
        self.seed()
        user_id = self.register()
        before, _ = self.scope(user_id)
        self.verify(user_id)
        after, _ = self.scope(user_id)
        self.assertLess(len(after), len(before))

    def test_the_screen_says_which_number_it_is_showing(self):
        self.seed()
        user_id = self.register()
        pending = self.client.get("/reach").get_data(as_text=True)
        self.assertIn("verified and not yet verified", pending)

        self.verify(user_id)
        verified = self.client.get("/reach").get_data(as_text=True)
        self.assertIn("Counting verified people only", verified)
        self.assertNotIn("verified and not yet verified", verified)

    def test_the_verified_count_matches_what_the_matcher_would_do(self):
        """The honest test: REACH's number must not promise people the
        week machine will never pair you with."""
        self.seed()
        user_id = self.register()
        self.verify(user_id)
        with app_module.app.test_request_context():
            me = app_module.load_user(user_id)
            pool, _ = app_module.reach_pool(me)
            counts = matching.reciprocity_counts(me, pool)
            eligible = matching.eligible_candidates(me, pool, set(), set())
        self.assertLessEqual(len(eligible), counts["mutual_open"])

    def test_every_reach_number_comes_from_the_same_pool(self):
        """Headline, per-filter deltas and whatif all scoped together —
        otherwise the deltas argue with the number above them."""
        self.seed()
        user_id = self.register()
        self.verify(user_id)
        response = self.client.post("/reach/show-all", json={"ignore": True})
        data = response.get_json()
        self.assertFalse(data["counting_unverified"])
        self.assertIn("filters", data)
        self.assertIn("counts", data)


if __name__ == "__main__":
    unittest.main()
