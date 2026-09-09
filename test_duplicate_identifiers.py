"""Email and phone cannot be reused across accounts.

2026-09-09 (evening), user's rule: "Hopefully there are tests to check
that phone number and emails cannot be duplicate. Or same email or phone
number not used with different phone number or emails. Avoiding
duplicates is essential."

There were none, because there was no rule to test: Account carried PLAIN
indexes on email and phone, not unique ones, and nothing anywhere checked
before writing. Two accounts could share either freely.

The second half of that sentence is the part worth being careful about.
The two identifiers are checked INDEPENDENTLY, so pairing a taken email
with a fresh phone does not launder it — and the reverse.
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import db
import onboarding

from test_segment_efg_routes import RouteTestCase, app_module


class RuleTests(unittest.TestCase):
    TAKEN_EMAIL = {"someone@example.com"}
    TAKEN_PHONE = {"919876543210"}

    def clash(self, email, phone):
        return onboarding.duplicate_identifier(
            email, phone, self.TAKEN_EMAIL, self.TAKEN_PHONE)

    def test_a_fresh_pair_is_fine(self):
        self.assertIsNone(self.clash("new@example.com", "919000000000"))

    def test_a_taken_email_is_refused(self):
        self.assertEqual(self.clash("someone@example.com", "919000000000"), "email")

    def test_a_taken_phone_is_refused(self):
        self.assertEqual(self.clash("new@example.com", "919876543210"), "phone")

    def test_a_taken_email_with_a_fresh_phone_is_still_refused(self):
        """The user's second sentence. Pairing a taken identifier with a
        fresh one does not launder it."""
        self.assertEqual(self.clash("someone@example.com", "918888888888"), "email")

    def test_a_taken_phone_with_a_fresh_email_is_still_refused(self):
        self.assertEqual(self.clash("fresh@example.com", "919876543210"), "phone")

    def test_only_one_identifier_given_is_checked_on_its_own(self):
        self.assertEqual(self.clash("someone@example.com", None), "email")
        self.assertEqual(self.clash(None, "919876543210"), "phone")
        self.assertIsNone(self.clash(None, "919000000000"))

    def test_nothing_given_clashes_with_nothing(self):
        self.assertIsNone(self.clash(None, None))
        self.assertIsNone(self.clash("", ""))

    def test_comparison_is_on_normalised_values(self):
        """"  Foo@Bar.com " and "foo@bar.com" are the same address, and
        +91 98765 43210 is the same number as 919876543210. Both sides go
        through normalise_identifiers first, so the check sees one form."""
        got = onboarding.normalise_identifiers("  SomeOne@Example.COM ", "+91 98765 43210")
        self.assertEqual(
            onboarding.duplicate_identifier(got["email"], got["phone"],
                                            self.TAKEN_EMAIL, self.TAKEN_PHONE),
            "email")
        only_phone = onboarding.normalise_identifiers("", "+91 98765 43210")
        self.assertEqual(
            onboarding.duplicate_identifier(only_phone["email"], only_phone["phone"],
                                            set(), self.TAKEN_PHONE),
            "phone")

    def test_both_identifiers_have_a_message_of_their_own(self):
        for which in ("email", "phone"):
            with self.subTest(which=which):
                self.assertIn(which, onboarding.DUPLICATE_MESSAGE[which])


class SignupRouteTests(RouteTestCase):
    """The rule where a person meets it."""

    def signup(self, email="", phone=""):
        return self.client.post("/signup", data={"email": email, "phone": phone},
                                follow_redirects=True).get_data(as_text=True)

    def take(self, user_id, email=None, phone=None):
        db.insert_row(self.conn, "User", {
            "id": user_id, "journey_state": "dating", "bgv_status": "declared",
            "consent_version": "v1", "stats_json": "{}", "vision_json": "{}",
            "skills_json": "{}", "preferences_json": "{}"})
        db.insert_row(self.conn, "Account",
                      onboarding.account_row(user_id, email, phone, "Mon:12"))
        self.conn.commit()

    def test_a_fresh_identifier_gets_through(self):
        body = self.signup(email="new@example.com")
        self.assertNotIn("already has an account", body)

    def test_a_taken_email_is_refused_at_the_front_door(self):
        self.take("u_taken", email="someone@example.com")
        self.assertIn("already has an account", self.signup(email="someone@example.com"))

    def test_a_taken_phone_is_refused(self):
        self.take("u_taken", phone="919876543210")
        self.assertIn("already has an account", self.signup(phone="+91 98765 43210"))

    def test_a_taken_email_paired_with_a_new_phone_is_refused(self):
        self.take("u_taken", email="someone@example.com", phone="919876543210")
        body = self.signup(email="someone@example.com", phone="918888888888")
        self.assertIn("already has an account", body)

    def test_a_refusal_keeps_what_they_typed(self):
        """Refusing a duplicate and clearing the box is two punishments
        for one mistake."""
        self.take("u_taken", email="someone@example.com")
        self.assertIn("someone@example.com", self.signup(email="someone@example.com"))


class DatabaseBackstopTests(unittest.TestCase):
    """The app checks before writing; this is what stops a race or a
    direct write getting past it."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = str(Path(self.dir) / "u.db")
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        db.init_db(self.conn, "schema.sql")

    def account(self, user_id, email=None, phone=None):
        db.insert_row(self.conn, "User", {
            "id": user_id, "journey_state": "dating", "bgv_status": "declared",
            "consent_version": "v1", "stats_json": "{}", "vision_json": "{}",
            "skills_json": "{}", "preferences_json": "{}"})
        db.insert_row(self.conn, "Account",
                      onboarding.account_row(user_id, email, phone, "Mon:12"))
        self.conn.commit()

    def test_the_database_refuses_a_duplicate_email(self):
        self.account("u1", email="a@b.com")
        with self.assertRaises(sqlite3.IntegrityError):
            self.account("u2", email="a@b.com")

    def test_the_database_refuses_a_duplicate_phone(self):
        self.account("u1", phone="919876543210")
        with self.assertRaises(sqlite3.IntegrityError):
            self.account("u2", phone="919876543210")

    def test_two_accounts_may_both_omit_one_identifier(self):
        """NULLs do not collide under a unique index, which is what we
        want — an account may carry only one of the two."""
        self.account("u1", email="a@b.com")
        self.account("u2", email="c@d.com")
        rows = db.fetch_all(self.conn, "Account")
        self.assertEqual(len({r["user_id"] for r in rows}), 2)

    def test_the_indexes_are_applied_outside_the_schema_script(self):
        """Deliberately not in schema.sql: init_db runs that file as one
        script, so a CREATE UNIQUE INDEX that fails on an already-dirty
        database would take down every request rather than one feature."""
        schema = Path("schema.sql").read_text(encoding="utf-8")
        for name, _table, _column in db.UNIQUE_INDEXES:
            with self.subTest(index=name):
                self.assertNotIn(name, schema)

    def test_a_dirty_database_is_reported_rather_than_crashing(self):
        """The reason for that. A database that already holds duplicates
        needs a person, not a crash loop."""
        conn = sqlite3.connect(str(Path(self.dir) / "dirty.db"))
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        conn.executescript(Path("schema.sql").read_text(encoding="utf-8"))
        for user_id in ("d1", "d2"):
            db.insert_row(conn, "User", {
                "id": user_id, "journey_state": "dating", "bgv_status": "declared",
                "consent_version": "v1", "stats_json": "{}", "vision_json": "{}",
                "skills_json": "{}", "preferences_json": "{}"})
            db.insert_row(conn, "Account",
                          onboarding.account_row(user_id, "same@example.com", None, "Mon:12"))
        conn.commit()

        problems = db.enforce_unique_indexes(conn)      # must not raise
        self.assertTrue(any(p["column"] == "email" for p in problems))
        # and the app still answers
        self.assertEqual(len(db.fetch_all(conn, "Account")), 2)


if __name__ == "__main__":
    unittest.main()
