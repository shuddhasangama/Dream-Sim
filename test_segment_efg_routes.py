"""End-to-end tests for the Segment E/F/G routes.

WHY THESE ARE DIFFERENT FROM EVERY OTHER TEST HERE
==================================================
The rest of the suite tests pure modules. That is why 596 passing tests
sat on top of a schema that could not be read on PostgreSQL — nothing
actually rendered a page. These boot the Flask app against a throwaway
SQLite file and drive it through the client, so a missing template, a
route guard wired to the wrong key, or a context variable a template
reads but no route passes, fails here rather than in production.

Still SQLite, so this is not the PostgreSQL smoke test the deployment
also needs (test_schema_postgres.py lints the schema statically instead).
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

import ceremony
import db
import guru_dating

os.environ.setdefault("PAYMENTS_ENABLED", "0")

import app as app_module  # noqa: E402  (after the env pin above)


class RouteTestCase(unittest.TestCase):
    """One temp database and one temp clock file per test, so nothing here
    touches data/dream.db or the shared simulation clock."""

    maxDiff = None

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.db_path = tmp / "test.db"

        # app_module.db IS this module, so the patch has to close over the
        # original rather than calling the name it just replaced.
        real_get_connection = db.get_connection
        self._patches = [
            mock.patch.object(db, "get_connection",
                              lambda *a, **k: real_get_connection(self.db_path)),
            mock.patch.object(app_module, "SIM_STATE_PATH", tmp / "sim_state.json"),
            mock.patch.dict(os.environ, {"PAYMENTS_ENABLED": "0", "DEMO_MODE": "1"}),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(self._stop)

        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()

        self.conn = real_get_connection(self.db_path)
        db.init_db(self.conn)

    def _stop(self):
        for p in reversed(self._patches):
            p.stop()
        if getattr(self, "conn", None) is not None:
            self.conn.close()
        self._tmp.cleanup()

    # ── fixtures ──────────────────────────────────────────────────────────

    def make_user(self, user_id, *, bgv_status="verified", journey_state="dating"):
        db.insert_row(self.conn, "User", {
            "id": user_id,
            "bgv_status": bgv_status,
            "journey_state": journey_state,
            "stats_json": json.dumps({"city": "Bengaluru", "gender": "female",
                                      "age_band": "28-32", "diet": "vegetarian"}),
            "vision_json": json.dumps([]),
            "preferences_json": json.dumps({}),
        })
        self.conn.commit()
        return user_id

    def make_lockin(self, a, b, lockin_id="lock-1"):
        db.insert_row(self.conn, "LockIn", {
            "id": lockin_id, "user_a": a, "user_b": b, "week": 1,
            "status": "active", "created_at": "W1 Wed 12:00", "dates_completed": 0,
        })
        self.conn.commit()
        return lockin_id

    def make_plan(self, lockin_id, plan_id="plan-1", status="pending_signatures"):
        db.insert_row(self.conn, "DatePlan", {
            "id": plan_id, "lockin_id": lockin_id, "datetime": "2026-01-10T19:30",
            "meal": "dinner", "venue": "Toit", "cuisine": "Thai",
            "budget_estimate": "1500-2500", "bill_split": "pay-your-own",
            "status": status,
        })
        self.conn.commit()
        return plan_id

    def login(self, user_id):
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id

    def set_clock(self, week=1, day="Mon", hour=12):
        app_module.set_clock(app_module.clock_module.SimulationClock.at(week, day, hour))


# ══ Segment G: Guru's hub ═══════════════════════════════════════════════


class GuruRouteTests(RouteTestCase):
    def test_an_unverified_user_is_told_to_get_verified_not_shown_a_hub(self):
        self.login(self.make_user("u1", bgv_status="declared", journey_state="onboarding"))
        response = self.client.get("/guru")
        self.assertEqual(response.status_code, 403)

    def test_a_verified_user_gets_the_hub_and_one_next_action(self):
        self.login(self.make_user("u1"))
        body = self.client.get("/guru").get_data(as_text=True)
        self.assertIn("What now?", body)
        self.assertIn("Your week is running", body)

    def test_the_hub_appears_in_the_navigation_once_verified(self):
        self.login(self.make_user("u1"))
        self.assertIn('href="/guru"', self.client.get("/dashboard").get_data(as_text=True))

    def test_the_navigation_stays_short_at_every_stage(self):
        """The complaint that started this. Asserted against the rendered
        page, not just the table it comes from."""
        self.login(self.make_user("u1", bgv_status="declared", journey_state="onboarding"))
        for state in (("declared", "onboarding"), ("verified", "dating"), ("verified", "relationship")):
            bgv_status, journey_state = state
            db.insert_row(self.conn, "User", {
                **dict(db.fetch_one(self.conn, "User", id="u1")),
                "bgv_status": bgv_status, "journey_state": journey_state,
            })
            self.conn.commit()
            body = self.client.get("/dashboard").get_data(as_text=True)
            with self.subTest(state=state):
                self.assertLessEqual(body.count('class="navlink"'), app_module.disclosure.MAX_NAV_LINKS + 1)

    def test_guru_points_at_the_debrief_once_the_date_has_happened(self):
        self.login(self.make_user("u1"))
        self.make_user("u2")
        lock = self.make_lockin("u1", "u2")
        plan = self.make_plan(lock, status="confirmed")
        db.insert_row(self.conn, "DateOutcome", {
            "id": f"outcome:{plan}", "dateplan_id": plan, "happened": 1,
            "a_green_flags_json": "[]", "a_red_flags_json": "[]",
            "b_green_flags_json": "[]", "b_red_flags_json": "[]",
        })
        self.conn.commit()
        body = self.client.get("/guru").get_data(as_text=True)
        self.assertIn("/debrief", body)


# ══ Segment E: the ceremony ═════════════════════════════════════════════


class CeremonyRouteTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.make_user("u1"))
        self.make_user("u2")
        self.lock = self.make_lockin("u1", "u2")
        self.plan = self.make_plan(self.lock)

    def step(self, kind=ceremony.DATE_AGREEMENT, **form):
        return self.client.post(f"/ceremony/{kind}/step", data=form, follow_redirects=False)

    def sign(self, name="Asha Rao", kind=ceremony.DATE_AGREEMENT, acks="all"):
        """Sign with every term ticked, which is the only way it completes."""
        keys = list(ceremony.ack_keys(kind)) if acks == "all" else acks
        return self.step(kind, signed_name=name, acks=keys)

    def state(self, user_id="u1", kind=ceremony.DATE_AGREEMENT):
        row = db.fetch_one(self.conn, "Ceremony", user_id=user_id, kind=kind, scope_id=self.plan)
        return dict(row) if row else None

    def test_an_unknown_kind_is_a_404_not_a_blank_agreement(self):
        self.assertEqual(self.client.get("/ceremony/marriage").status_code, 404)

    def test_the_playbook_renders_every_clause(self):
        body = self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}").get_data(as_text=True)
        for clause in ceremony.date_clauses({}):
            self.assertIn(clause["title"], body)

    def test_the_agreement_reads_back_the_plan_rather_than_asking_again(self):
        body = self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}").get_data(as_text=True)
        for value in ("Thai", "1500-2500", "Pay your own", "vegetarian"):
            self.assertIn(value, body)

    def test_the_slot_reads_as_a_sentence_not_a_timestamp(self):
        """A clause someone is asked to sign should not contain an ISO
        string. The stored value stays machine-shaped; only the readback
        is humanised."""
        body = self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}").get_data(as_text=True)
        self.assertIn("Sat 10 Jan, 19:30", body)
        self.assertNotIn("2026-01-10T19:30", body)
        self.assertEqual(db.fetch_one(self.conn, "DatePlan", id=self.plan)["datetime"],
                         "2026-01-10T19:30")

    def test_opening_it_creates_exactly_one_row_however_many_times_you_look(self):
        for _ in range(3):
            self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}")
        rows = db.fetch_all(self.conn, "Ceremony", user_id="u1", scope_id=self.plan)
        self.assertEqual(len(rows), 1)

    def test_the_three_steps_run_in_order(self):
        self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}")
        self.step()
        self.assertTrue(self.state()["playbook_ack"])
        self.assertIsNone(self.state()["signed_name"])

        self.sign()
        self.assertEqual(self.state()["signed_name"], "Asha Rao")
        self.assertFalse(self.state()["face_verified"])

        with mock.patch.object(app_module.dateplan, "verify_face", return_value=True):
            self.step()
        self.assertTrue(self.state()["face_verified"])
        self.assertIsNotNone(self.state()["completed_at"])

    def test_the_terms_are_shown_in_full_not_just_named(self):
        """The complaint this answers: the mock-up spelt the terms out and
        the build had reduced them to a bare name field."""
        self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}")
        self.step()  # past the playbook, onto the signature
        body = self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}").get_data(as_text=True)
        for ack in ceremony.acks_for(ceremony.DATE_AGREEMENT):
            self.assertIn(ack["label"], body)
            self.assertIn(ack["term"][:40], body)

    def test_a_signature_with_a_term_unticked_is_refused(self):
        """Ticking on someone's behalf records agreement they never gave."""
        self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}")
        self.step()
        keys = list(ceremony.ack_keys(ceremony.DATE_AGREEMENT))
        self.sign(acks=keys[:-1])
        self.assertIsNone(self.state()["signed_name"])
        # Nothing was stored, so the row still shows every term outstanding;
        # the proposed partial tick is short exactly the one left out.
        self.assertEqual(ceremony.signed_acks(self.state()), [])
        self.assertEqual(ceremony.missing_acks(self.state(), keys[:-1]), [keys[-1]])

    def test_the_refusal_says_why(self):
        self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}")
        self.step()
        response = self.sign(acks=[])
        self.assertIn("unsigned=1", response.headers["Location"])
        body = self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}?unsigned=1").get_data(as_text=True)
        self.assertIn("Every term has to be ticked", body)

    def test_what_was_ticked_is_stored_and_mirrored(self):
        """The Signature row must carry the terms the person actually
        agreed to, not a blanket True written by the mirror."""
        self._complete("u1")
        self.assertEqual(sorted(ceremony.signed_acks(self.state())),
                         sorted(ceremony.ack_keys(ceremony.DATE_AGREEMENT)))
        sig = dict(db.fetch_one(self.conn, "Signature", dateplan_id=self.plan, user_id="u1"))
        for field in app_module.dateplan.ACK_FIELDS:
            self.assertTrue(sig[field], field)

    def test_the_date_terms_line_up_with_the_signature_row(self):
        """The mirror maps ack keys straight onto dateplan.ACK_FIELDS. If
        those two lists drift, consent silently stops being recorded."""
        self.assertEqual(tuple(ceremony.ack_keys(ceremony.DATE_AGREEMENT)),
                         app_module.dateplan.ACK_FIELDS)

    def test_posting_a_signature_first_does_not_skip_the_playbook(self):
        """The step is decided by next_step(), never by the form. A client
        that posts out of order gets the step it was actually on."""
        self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}")
        self.sign()
        self.assertIsNone(self.state()["signed_name"])
        self.assertTrue(self.state()["playbook_ack"])

    def _complete(self, user_id):
        self.login(user_id)
        self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}")
        self.step()
        self.sign(name=f"Name {user_id}")
        with mock.patch.object(app_module.dateplan, "verify_face", return_value=True):
            self.step()

    def test_a_failed_face_check_leaves_the_ceremony_open_and_retryable(self):
        self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}")
        self.step()
        self.sign()
        with mock.patch.object(app_module.dateplan, "verify_face", return_value=False):
            self.step()
        self.assertFalse(self.state()["face_verified"])
        self.assertIsNone(self.state()["completed_at"])
        with mock.patch.object(app_module.dateplan, "verify_face", return_value=True):
            self.step()
        self.assertTrue(self.state()["face_verified"])

    def test_completing_the_agreement_writes_the_signature_row_the_plan_reads(self):
        """The ceremony did not replace dateplan.is_confirmed(); it feeds
        it. If this stops holding, a signed agreement stops confirming a
        date and nothing anywhere says why."""
        self._complete("u1")
        sig = db.fetch_one(self.conn, "Signature", dateplan_id=self.plan, user_id="u1")
        self.assertIsNotNone(sig)
        self.assertTrue(app_module.dateplan.is_fully_acknowledged(dict(sig)))

    def test_one_signature_does_not_confirm_the_date(self):
        self._complete("u1")
        self.assertEqual(db.fetch_one(self.conn, "DatePlan", id=self.plan)["status"],
                         "pending_signatures")

    def test_both_signatures_confirm_it(self):
        self._complete("u1")
        self._complete("u2")
        self.assertEqual(db.fetch_one(self.conn, "DatePlan", id=self.plan)["status"], "confirmed")

    def test_the_same_kind_recurs_for_the_next_date_rather_than_reading_as_signed(self):
        """The scope is what keeps recurrences apart. Sign for one date and
        the next must start at the playbook again."""
        self._complete("u1")
        # What plan_feedback()'s "keep dating" branch does between dates.
        db.delete_row(self.conn, "Signature", f"{self.plan}:u1")
        db.delete_row(self.conn, "DatePlan", self.plan)
        self.conn.commit()
        self.plan = self.make_plan(self.lock, plan_id="plan-2")
        self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}")
        self.assertEqual(ceremony.next_step(self.state()), ceremony.PLAYBOOK)

    def test_a_user_with_no_match_gets_the_locked_page_not_a_broken_one(self):
        """Nobody can browse to an agreement. The surface is guarded at
        MATCHED, so the URL is refused with an explanation rather than
        rendering an agreement about nothing."""
        self.login(self.make_user("u3"))
        response = self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}")
        self.assertEqual(response.status_code, 403)
        self.assertIn("locked each other in", response.get_data(as_text=True))

    def test_a_matched_user_with_no_plan_yet_is_sent_to_guru(self):
        """Past the guard, but there is nothing to agree to until a date
        exists — that is a redirect, not a refusal."""
        self.login(self.make_user("u3"))
        self.make_user("u4")
        self.make_lockin("u3", "u4", lockin_id="lock-2")
        response = self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/guru", response.headers["Location"])


class CeremonyPaymentTests(CeremonyRouteTests):
    """The fee, when fees are switched on. Same fixtures, one switch."""

    def setUp(self):
        super().setUp()
        self._pay = mock.patch.dict(os.environ, {"PAYMENTS_ENABLED": "1"})
        self._pay.start()
        self.addCleanup(self._pay.stop)

    def test_the_screen_offers_the_checkout_rather_than_the_sign_button(self):
        body = self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}").get_data(as_text=True)
        self.assertIn("₹1,499", body)
        self.assertIn("/pay/agreement", body)

    def test_no_step_can_be_taken_before_the_fee_clears(self):
        self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}")
        response = self.step()
        self.assertEqual(response.status_code, 302)
        self.assertIn("/pay/agreement", response.headers["Location"])
        self.assertFalse(self.state()["playbook_ack"])

    def test_once_it_clears_the_ceremony_runs(self):
        self.client.post("/pay/agreement/confirm", data={})
        self.client.get(f"/ceremony/{ceremony.DATE_AGREEMENT}")
        self.step()
        self.assertTrue(self.state()["playbook_ack"])

    # Inherited cases that assume free access are re-pointed at the paid
    # path rather than silently passing for the wrong reason.
    def _complete(self, user_id):
        self.login(user_id)
        self.client.post("/pay/agreement/confirm", data={})
        super()._complete(user_id)

    def test_the_playbook_renders_every_clause(self):
        self.client.post("/pay/agreement/confirm", data={})
        super().test_the_playbook_renders_every_clause()

    def test_the_agreement_reads_back_the_plan_rather_than_asking_again(self):
        self.client.post("/pay/agreement/confirm", data={})
        super().test_the_agreement_reads_back_the_plan_rather_than_asking_again()

    def test_the_slot_reads_as_a_sentence_not_a_timestamp(self):
        self.client.post("/pay/agreement/confirm", data={})
        super().test_the_slot_reads_as_a_sentence_not_a_timestamp()

    def test_the_terms_are_shown_in_full_not_just_named(self):
        self.client.post("/pay/agreement/confirm", data={})
        super().test_the_terms_are_shown_in_full_not_just_named()

    def test_a_signature_with_a_term_unticked_is_refused(self):
        self.client.post("/pay/agreement/confirm", data={})
        super().test_a_signature_with_a_term_unticked_is_refused()

    def test_the_refusal_says_why(self):
        self.client.post("/pay/agreement/confirm", data={})
        super().test_the_refusal_says_why()

    def test_what_was_ticked_is_stored_and_mirrored(self):
        self.client.post("/pay/agreement/confirm", data={})
        super().test_what_was_ticked_is_stored_and_mirrored()

    def test_the_three_steps_run_in_order(self):
        self.client.post("/pay/agreement/confirm", data={})
        super().test_the_three_steps_run_in_order()

    def test_posting_a_signature_first_does_not_skip_the_playbook(self):
        self.client.post("/pay/agreement/confirm", data={})
        super().test_posting_a_signature_first_does_not_skip_the_playbook()

    def test_a_failed_face_check_leaves_the_ceremony_open_and_retryable(self):
        self.client.post("/pay/agreement/confirm", data={})
        super().test_a_failed_face_check_leaves_the_ceremony_open_and_retryable()

    def test_the_same_kind_recurs_for_the_next_date_rather_than_reading_as_signed(self):
        self.client.post("/pay/agreement/confirm", data={})
        super().test_the_same_kind_recurs_for_the_next_date_rather_than_reading_as_signed()


# ══ Segment F: the debrief ══════════════════════════════════════════════


class DebriefRouteTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.make_user("u1"))
        self.make_user("u2")
        self.lock = self.make_lockin("u1", "u2")
        self.plan = self.make_plan(self.lock, status="confirmed")
        db.insert_row(self.conn, "DateOutcome", {
            "id": f"outcome:{self.plan}", "dateplan_id": self.plan, "happened": 1,
            "a_green_flags_json": "[]", "a_red_flags_json": "[]",
            "b_green_flags_json": "[]", "b_red_flags_json": "[]",
        })
        self.conn.commit()
        self.set_clock(week=1, day="Sun", hour=21)

    def outcome(self):
        return app_module._outcome_from_row(
            dict(db.fetch_one(self.conn, "DateOutcome", dateplan_id=self.plan)))

    def test_it_is_locked_before_a_date_is_set(self):
        self.login(self.make_user("u3"))
        self.assertEqual(self.client.get("/debrief").status_code, 403)

    def test_it_asks_for_the_flags_first(self):
        body = self.client.get("/debrief").get_data(as_text=True)
        self.assertIn("green flags", body)
        self.assertNotIn("continue dating", body)

    def test_the_decision_only_appears_once_the_flags_are_in(self):
        self.client.post("/plan/feedback/flags", data={
            "green_flags": guru_dating.GREEN_FLAGS[:2], "back": "debrief_view"})
        body = self.client.get("/debrief").get_data(as_text=True)
        self.assertIn("continue dating", body)

    def test_saving_the_flags_comes_back_to_the_debrief_not_the_week(self):
        """The one change the existing routes needed: the same rules, a
        different destination, chosen by the screen that posted."""
        response = self.client.post("/plan/feedback/flags", data={
            "green_flags": guru_dating.GREEN_FLAGS[:2], "back": "debrief_view"})
        self.assertIn("/debrief", response.headers["Location"])

    def test_without_that_field_it_still_comes_back_to_the_week(self):
        response = self.client.post("/plan/feedback/flags", data={
            "green_flags": guru_dating.GREEN_FLAGS[:2]})
        self.assertIn("/week", response.headers["Location"])

    def test_a_decision_without_flags_is_refused_by_the_route_not_just_hidden(self):
        self.client.post("/plan/feedback", data={"decision": "relationship", "back": "debrief_view"})
        self.assertIsNone(self.outcome()["a_decision"])

    def test_the_three_way_branch_is_recorded(self):
        self.client.post("/plan/feedback/flags", data={
            "green_flags": guru_dating.GREEN_FLAGS[:2], "back": "debrief_view"})
        self.client.post("/plan/feedback", data={"decision": "continue", "back": "debrief_view"})
        self.assertEqual(self.outcome()["a_decision"], "continue")

    def test_the_screen_says_it_is_waiting_on_the_partner(self):
        self.client.post("/plan/feedback/flags", data={
            "green_flags": guru_dating.GREEN_FLAGS[:2], "back": "debrief_view"})
        self.client.post("/plan/feedback", data={"decision": "continue", "back": "debrief_view"})
        self.assertIn("Waiting on", self.client.get("/debrief").get_data(as_text=True))

    # ── timing: an hour after the date, not Sunday night ────────────────
    # The fixture's slot is 2026-01-10T19:30, a Saturday dinner, so the
    # debrief opens Sat 21:00 (19:30 + 1h, rounded up off the half hour).

    def test_it_is_shut_before_the_date_has_happened(self):
        self.set_clock(week=1, day="Wed", hour=12)
        body = self.client.get("/debrief").get_data(as_text=True)
        self.assertIn("Sat 21:00", body)
        self.assertNotIn("Save the flags", body)

    def test_it_is_still_shut_while_the_date_is_happening(self):
        """Dinner starts 19:30. At 20:00 they are at the table, and the
        old Sunday-night rule was not the only way to get this wrong."""
        self.set_clock(week=1, day="Sat", hour=20)
        self.assertNotIn("Save the flags", self.client.get("/debrief").get_data(as_text=True))

    def test_it_opens_an_hour_after_the_date_starts(self):
        self.set_clock(week=1, day="Sat", hour=21)
        self.assertIn("Save the flags", self.client.get("/debrief").get_data(as_text=True))

    def test_a_plan_with_an_unreadable_slot_opens_rather_than_seals_shut(self):
        """Not knowing when the date was is not a reason to stop someone
        reporting what happened at it."""
        db.insert_row(self.conn, "DatePlan",
                      {**dict(db.fetch_one(self.conn, "DatePlan", id=self.plan)), "datetime": "unknown"})
        self.conn.commit()
        self.set_clock(week=1, day="Mon", hour=1)
        self.assertIn("Save the flags", self.client.get("/debrief").get_data(as_text=True))

    # ── the no-show path ────────────────────────────────────────────────

    def test_a_no_show_is_offered_without_asking_for_green_flags(self):
        body = self.client.get("/debrief").get_data(as_text=True)
        self.assertIn("Report a no-show", body)

    def test_reporting_a_no_show_records_it_against_them_not_you(self):
        self.client.post("/debrief/no-show")
        outcome = self.outcome()
        self.assertFalse(outcome["happened"])
        self.assertEqual(outcome["a_decision"], "pass")
        events = db.fetch_all(self.conn, "ComplianceEvent", user_id="u2")
        self.assertEqual([e["type"] for e in events], ["no_show"])
        self.assertEqual(db.fetch_all(self.conn, "ComplianceEvent", user_id="u1"), [])

    def test_a_no_show_releases_the_lock_in(self):
        self.client.post("/debrief/no-show")
        self.assertNotEqual(db.fetch_one(self.conn, "LockIn", id=self.lock)["status"], "active")

    def test_a_no_show_cannot_be_reported_before_the_debrief_opens(self):
        self.set_clock(week=1, day="Wed", hour=12)
        self.client.post("/debrief/no-show")
        self.assertTrue(self.outcome()["happened"])
        self.assertEqual(db.fetch_all(self.conn, "ComplianceEvent", user_id="u2"), [])

    def test_no_flags_are_demanded_of_someone_who_was_stood_up(self):
        """Reporting it returns you to the pool immediately. There is no
        screen asking for two nice things about an empty chair, because
        the lock-in is already gone by the time you land."""
        response = self.client.post("/debrief/no-show")
        self.assertIn("/week", response.headers["Location"])
        self.assertEqual(self.client.get("/debrief").status_code, 403)


class CancellationTests(RouteTestCase):
    """2026-09-04, user's rule: dates are set Thursday for the weekend, so
    a free cancellation is an invitation to change your mind at everyone
    else's expense."""

    def setUp(self):
        super().setUp()
        self.login(self.make_user("u1"))
        self.make_user("u2")
        self.lock = self.make_lockin("u1", "u2")
        self.plan = self.make_plan(self.lock, status="confirmed")

    def strikes(self, user_id):
        return [e["type"] for e in db.fetch_all(self.conn, "ComplianceEvent", user_id=user_id)]

    def test_early_notice_is_free_and_unrecorded(self):
        """Punishing honest early notice teaches people to no-show
        instead, which is the behaviour this is trying to prevent."""
        self.set_clock(week=1, day="Thu", hour=12)   # Sat 19:30 is 55h away
        self.client.post("/plan/cancel")
        row = db.fetch_one(self.conn, "DatePlan", id=self.plan)
        self.assertEqual(row["status"], "cancelled")
        self.assertEqual(row["cancel_fee"], 0)
        self.assertEqual(self.strikes("u1"), [])

    def test_inside_the_window_it_costs_and_is_recorded(self):
        self.set_clock(week=1, day="Sat", hour=10)   # 9h before a 19:30 slot
        self.client.post("/plan/cancel")
        row = db.fetch_one(self.conn, "DatePlan", id=self.plan)
        self.assertEqual(row["cancel_fee"], 999)
        self.assertEqual(self.strikes("u1"), ["late_cancel"])

    def test_the_penalty_lands_on_the_person_who_cancelled(self):
        self.set_clock(week=1, day="Sat", hour=10)
        self.client.post("/plan/cancel")
        self.assertEqual(self.strikes("u2"), [])

    def test_cancelling_releases_the_pair_back_to_the_pool(self):
        self.set_clock(week=1, day="Thu", hour=12)
        self.client.post("/plan/cancel")
        self.assertNotEqual(db.fetch_one(self.conn, "LockIn", id=self.lock)["status"], "active")

    def test_the_screen_states_the_cost_before_you_click(self):
        self.set_clock(week=1, day="Sat", hour=10)
        body = self.client.get("/plan").get_data(as_text=True)
        self.assertIn("₹999", body)
        self.assertIn("24-hour window", body)

    def test_an_unconfirmed_plan_has_nothing_to_cancel(self):
        db.insert_row(self.conn, "DatePlan",
                      {**dict(db.fetch_one(self.conn, "DatePlan", id=self.plan)),
                       "status": "pending_signatures"})
        self.conn.commit()
        self.client.post("/plan/cancel")
        self.assertEqual(db.fetch_one(self.conn, "DatePlan", id=self.plan)["status"],
                         "pending_signatures")


if __name__ == "__main__":
    unittest.main()
