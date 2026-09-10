"""Confirming a contact — and, more importantly, not asking anyone who
was already here.

2026-09-10, user's rule: "For the existing/simulated users can we leave
the email/phone verification for now. Can we do this as a process for the
new users signup."

The grandfathering is the half that can quietly break the deployed app,
so most of what is asserted here is about who is NOT asked.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

import db
import generate_users
import signup_verification as sv
from test_segment_efg_routes import RouteTestCase, app_module


class CodeTests(unittest.TestCase):
    def setUp(self):
        self.code = "123456"
        self.row = sv.challenge_row("u1", "email", "a@b.com", self.code)

    def test_the_code_itself_is_never_stored(self):
        self.assertNotIn(self.code, json.dumps(self.row))
        self.assertNotEqual(self.row["code_hash"], self.code)

    def test_the_right_code_passes(self):
        self.assertTrue(sv.check(self.row, self.code)["ok"])

    def test_a_wrong_code_does_not(self):
        got = sv.check(self.row, "000000")
        self.assertFalse(got["ok"])
        self.assertEqual(got["reason"], "wrong")
        self.assertIn("tries left", got["message"])

    def test_whitespace_around_a_pasted_code_is_forgiven(self):
        self.assertTrue(sv.check(self.row, "  123456 ")["ok"])

    def test_an_expired_code_says_so_because_the_fix_is_different(self):
        stale = {**self.row,
                 "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}
        got = sv.check(stale, self.code)
        self.assertFalse(got["ok"])
        self.assertEqual(got["reason"], "expired")

    def test_a_used_code_cannot_be_used_again(self):
        used = {**self.row, "consumed_at": "2026-09-10T00:00:00"}
        self.assertFalse(sv.check(used, self.code)["ok"])

    def test_attempts_are_capped(self):
        maxed = {**self.row, "attempts": sv.MAX_ATTEMPTS}
        got = sv.check(maxed, self.code)          # even the RIGHT code
        self.assertFalse(got["ok"])
        self.assertEqual(got["reason"], "locked")

    def test_no_code_yet_is_not_a_wrong_code(self):
        self.assertEqual(sv.check(None, "123456")["reason"], "none")

    def test_resending_has_a_cooldown(self):
        self.assertFalse(sv.can_resend(self.row))
        old = {**self.row,
               "sent_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()}
        self.assertTrue(sv.can_resend(old))
        self.assertTrue(sv.can_resend(None))

    def test_delivery_admits_it_cannot_send_yet(self):
        got = sv.deliver("phone", "+919000000000", "123456")
        self.assertFalse(got["sent"])
        self.assertEqual(got["show_on_screen"], "123456")


class WhoIsAskedTests(unittest.TestCase):
    """The grandfathering rule, stated four ways."""

    def test_a_simulated_user_has_no_account_and_is_never_asked(self):
        self.assertFalse(sv.is_required(None))
        self.assertTrue(sv.is_satisfied(None))

    def test_an_account_written_before_today_is_grandfathered(self):
        # verification_required defaults to 0, so an existing row looks
        # exactly like this.
        old_account = {"email": "a@b.com", "verified_email": 0, "verified_phone": 0}
        self.assertFalse(sv.is_required(old_account))
        self.assertTrue(sv.is_satisfied(old_account))

    def test_a_new_account_is_asked(self):
        fresh = {"email": "a@b.com", "verification_required": 1,
                 "verified_email": 0, "verified_phone": 0}
        self.assertTrue(sv.is_required(fresh))
        self.assertFalse(sv.is_satisfied(fresh))

    def test_one_channel_is_enough(self):
        """Someone who signed up with only an email cannot verify a phone
        they never gave. Demanding both is a gate nobody can pass."""
        fresh = {"email": "a@b.com", "verification_required": 1,
                 "verified_email": 1, "verified_phone": 0}
        self.assertTrue(sv.is_satisfied(fresh))

    def test_pending_lists_only_what_they_actually_gave_us(self):
        account = {"email": "a@b.com", "phone": None,
                   "verified_email": 0, "verified_phone": 0}
        self.assertEqual(sv.pending_channels(account), ["email"])


class VerificationRouteTests(RouteTestCase):
    def seed(self, n=12):
        for u in generate_users.generate_users(n, seed=5):
            row = app_module.onboarding.build_user_row(
                user_id=u["user_id"], city=u["city"], gender=u["gender"],
                stats=u["stats"], visions=u["visions"], activities={})
            row["bgv_status"] = "verified"
            row["journey_state"] = "dating"
            row["preferences_json"] = json.dumps(u["preferences"], ensure_ascii=False)
            db.insert_row(self.conn, "User", row)
        self.conn.commit()

    def register(self, gender="female", email="new@x.com"):
        c = self.client
        c.post("/signup", data={"email": email})
        c.post("/onboarding/vision", data={
            "intimacy_kinds": ["Emotional", "Physical"],
            "other_keys": ["Kids"], "kids_route": ["Naturally"]})
        c.post("/onboarding/stats", data={
            "city": "Bangalore", "gender": gender, "age": "31",
            "education": "Master's", "nationality": "IN",
            "profession": "Engineering", "salary": "1800000",
            "diet": "Everything", "religion": "Hindu",
            "languages": ["English"], "cuisine": ["Thai"],
            "ethnicity": ["Indian"]})
        c.post("/onboarding/chemistry", data={
            "act__Cooking": "good", "act__Yoga": "improve",
            "act__Tennis": "maybe", "act__Salsa": "no"})
        c.post("/onboarding/finish")
        with c.session_transaction() as sess:
            return sess["user_id"]

    def test_a_new_signup_is_marked_as_needing_it(self):
        self.seed()
        user_id = self.register()
        account = dict(db.fetch_one(self.conn, "Account", user_id=user_id))
        self.assertEqual(account["verification_required"], 1)

    def test_the_dashboard_asks_for_it_without_blocking_anything(self):
        self.seed()
        self.register()
        body = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Confirm your email", body)
        # ...and REACH still opens. Being made to prove a phone before you
        # have seen anything is how a sign-up funnel dies.
        self.assertEqual(self.client.get("/reach").status_code, 200)

    def test_the_code_is_shown_because_nothing_can_be_sent_yet(self):
        self.seed()
        self.register()
        self.client.post("/verify-contact/send", data={"channel": "email"})
        body = self.client.get("/verify-contact").get_data(as_text=True)
        self.assertIn("cannot actually send", body)
        self.assertRegex(body, r">\s*\d{6}\s*<")

    def test_confirming_it_works_end_to_end(self):
        self.seed()
        user_id = self.register()
        self.client.post("/verify-contact/send", data={"channel": "email"})
        with self.client.session_transaction() as sess:
            code = sess["verification_shown_code"]
        self.client.get("/verify-contact")           # clears the one-shot
        self.client.post("/verify-contact/check", data={"channel": "email", "code": code})
        account = dict(db.fetch_one(self.conn, "Account", user_id=user_id))
        self.assertEqual(account["verified_email"], 1)

    def test_a_wrong_code_is_counted_and_refused(self):
        self.seed()
        user_id = self.register()
        self.client.post("/verify-contact/send", data={"channel": "email"})
        self.client.post("/verify-contact/check", data={"channel": "email", "code": "000000"})
        account = dict(db.fetch_one(self.conn, "Account", user_id=user_id))
        self.assertEqual(account["verified_email"], 0)
        rows = [dict(r) for r in db.fetch_all(self.conn, "SignupVerification", user_id=user_id)]
        self.assertEqual(rows[0]["attempts"], 1)
        self.assertIn("not right", self.client.get("/verify-contact").get_data(as_text=True))

    def test_resending_immediately_is_refused(self):
        self.seed()
        self.register()
        self.client.post("/verify-contact/send", data={"channel": "email"})
        self.client.post("/verify-contact/send", data={"channel": "email"})
        self.assertIn("less than a minute",
                      self.client.get("/verify-contact").get_data(as_text=True))

    def test_a_channel_they_never_gave_is_refused_kindly(self):
        self.seed()
        self.register()
        self.client.post("/verify-contact/send", data={"channel": "phone"})
        self.assertIn("nothing to send", self.client.get("/verify-contact").get_data(as_text=True))


class TheGateTests(RouteTestCase):
    """What being unverified actually costs, and what it must not."""

    def _verified(self, user_id):
        """contact_verified() reads the request-scoped connection, so it
        needs an app context the same way a route has one."""
        with app_module.app.test_request_context():
            return app_module.contact_verified(user_id)

    def test_a_grandfathered_user_can_still_say_yes(self):
        """The whole point of the rule. A seeded user has no Account row
        and must be completely unaffected."""
        self.make_user("g1")
        self.assertTrue(self._verified("g1"))

    def test_a_new_unverified_account_cannot_say_yes_yet(self):
        db.insert_row(self.conn, "User", {
            "id": "n1", "bgv_status": "verified", "journey_state": "dating",
            "stats_json": json.dumps({"city": "Bengaluru", "gender": "female", "age": 30}),
            "vision_json": "[]", "skills_json": "{}", "preferences_json": "{}"})
        db.insert_row(self.conn, "Account", app_module.onboarding.account_row(
            "n1", "n1@x.com", None, "2026-09-10"))
        self.conn.commit()
        self.assertFalse(self._verified("n1"))

    def test_and_can_once_one_channel_is_confirmed(self):
        db.insert_row(self.conn, "User", {
            "id": "n2", "bgv_status": "verified", "journey_state": "dating",
            "stats_json": json.dumps({"city": "Bengaluru", "gender": "female", "age": 30}),
            "vision_json": "[]", "skills_json": "{}", "preferences_json": "{}"})
        row = app_module.onboarding.account_row("n2", "n2@x.com", None, "2026-09-10")
        db.insert_row(self.conn, "Account", {**row, "verified_email": 1})
        self.conn.commit()
        self.assertTrue(self._verified("n2"))


if __name__ == "__main__":
    unittest.main()
