"""End-to-end tests for Segments G, H, I and J.

The theme across all four is the same: a ceremony gates the thing it is
about, and ONE signature gates nothing. Segment G was written as
"ceremonies 2 and 3 exist but nothing launches them" — these are the tests
that stop it regressing to that.
"""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

import ceremony
import db
import gate_conversation

from test_segment_efg_routes import RouteTestCase, app_module


class PairCase(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.make_user("u1"))
        self.make_user("u2")
        self.lock = self.make_lockin("u1", "u2")

    def reach_first_date(self):
        """Escalations and the gate open at FIRST_DATE, which needs a plan
        and an outcome — not merely a lock-in."""
        plan = self.make_plan(self.lock, status="confirmed")
        db.insert_row(self.conn, "DateOutcome", {
            "id": f"outcome:{plan}", "dateplan_id": plan, "happened": 1,
            "a_green_flags_json": "[]", "a_red_flags_json": "[]",
            "b_green_flags_json": "[]", "b_red_flags_json": "[]",
        })
        self.conn.commit()
        return plan

    def complete_ceremony(self, kind, user_id):
        """Walk one ceremony end to end for one person."""
        self.login(user_id)
        self.client.get(f"/ceremony/{kind}")
        self.client.post(f"/ceremony/{kind}/step")                       # playbook
        self.client.post(f"/ceremony/{kind}/step", data={
            "signed_name": f"Name {user_id}", "acks": list(ceremony.ack_keys(kind))})
        with mock.patch.object(app_module.dateplan, "verify_face", return_value=True):
            self.client.post(f"/ceremony/{kind}/step")                   # face

    def cer(self, kind, user_id):
        row = db.fetch_one(self.conn, "Ceremony", user_id=user_id, kind=kind, scope_id=self.lock)
        return dict(row) if row else None

    def set_dates_completed(self, count):
        db.insert_row(self.conn, "LockIn",
                      {**dict(db.fetch_one(self.conn, "LockIn", id=self.lock)),
                       "dates_completed": count})
        self.conn.commit()


# ══ Segment G ═══════════════════════════════════════════════════════════


class ContactShareCeremonyTests(PairCase):
    def setUp(self):
        super().setUp()
        self.reach_first_date()
        self.set_dates_completed(2)   # escalations unlock after the 2nd date

    def request_from(self, requester, channel="phone"):
        self.login(requester)
        return self.client.post("/escalations/contact/request", data={"channel": channel})

    def latest_request(self):
        rows = db.fetch_all(self.conn, "ContactRequest", pair_id=self.lock)
        return dict(rows[-1]) if rows else None

    def test_asking_for_a_number_needs_no_signature(self):
        """Requesting is how you ask, and asking is not the thing that
        hands your number over."""
        self.request_from("u1")
        self.assertIsNotNone(self.latest_request())
        self.assertIsNone(self.cer(ceremony.CONTACT_SHARE, "u1"))

    def test_accepting_without_signing_sends_you_to_the_ceremony(self):
        self.request_from("u1")
        row = self.latest_request()
        self.login("u2")
        response = self.client.post("/escalations/contact/respond",
                                    data={"request_id": row["id"], "response": "accepted"})
        self.assertIn(f"/ceremony/{ceremony.CONTACT_SHARE}", response.headers["Location"])
        self.assertEqual(self.latest_request()["status"], "pending")

    def test_declining_never_needs_a_signature(self):
        """Nobody should have to sign something to say no."""
        self.request_from("u1")
        row = self.latest_request()
        self.login("u2")
        self.client.post("/escalations/contact/respond",
                         data={"request_id": row["id"], "response": "declined"})
        self.assertEqual(self.latest_request()["status"], "declined")

    def test_accepting_works_once_signed(self):
        self.request_from("u1")
        row = self.latest_request()
        self.complete_ceremony(ceremony.CONTACT_SHARE, "u2")
        self.client.post("/escalations/contact/respond",
                         data={"request_id": row["id"], "response": "accepted"})
        self.assertEqual(self.latest_request()["status"], "accepted")

    def test_the_screen_offers_the_agreement_before_it_is_signed(self):
        self.login("u1")
        body = self.client.get("/escalations").get_data(as_text=True)
        self.assertIn(f"/ceremony/{ceremony.CONTACT_SHARE}", body)

    def test_one_signature_is_not_both(self):
        self.complete_ceremony(ceremony.CONTACT_SHARE, "u1")
        self.login("u1")
        body = self.client.get("/escalations").get_data(as_text=True)
        self.assertIn("one signature is", body.lower().replace("\n", " "))


class HomeInviteCeremonyTests(PairCase):
    def setUp(self):
        super().setUp()
        self.reach_first_date()
        self.set_dates_completed(2)

    def propose(self, user_id="u1"):
        self.login(user_id)
        return self.client.post("/escalations/invite/propose",
                                data={"proposed_datetime": "2026-01-17T19:00",
                                      "expectation_flag": "social_only"})

    def invites(self):
        return db.fetch_all(self.conn, "HomeInvite", pair_id=self.lock)

    def test_an_address_is_not_offered_before_a_phone_number(self):
        """Contact details come before an address does. Checked in the
        route, not merely hidden in the template — a posted form is not
        a click."""
        self.propose()
        self.assertEqual(self.invites(), [])

    def test_with_contact_shared_it_still_needs_its_own_ceremony(self):
        for uid in ("u1", "u2"):
            self.complete_ceremony(ceremony.CONTACT_SHARE, uid)
        response = self.propose()
        self.assertIn(f"/ceremony/{ceremony.HOME_INVITE}", response.headers["Location"])
        self.assertEqual(self.invites(), [])

    def test_both_ceremonies_signed_lets_the_invitation_through(self):
        for kind in (ceremony.CONTACT_SHARE, ceremony.HOME_INVITE):
            for uid in ("u1", "u2"):
                self.complete_ceremony(kind, uid)
        self.propose()
        self.assertEqual(len(self.invites()), 1)

    def test_the_screen_says_what_the_home_invite_is_waiting_on(self):
        self.login("u1")
        body = self.client.get("/escalations").get_data(as_text=True)
        self.assertIn("Contact details", body)


# ══ Segment H ═══════════════════════════════════════════════════════════


class GateCeremonyTests(PairCase):
    """The duplicate signature path is gone: /gate/consent used to run its
    own, which meant two places for one rule to drift apart."""

    def setUp(self):
        super().setUp()
        self.reach_first_date()
        db.insert_row(self.conn, "StageGate", {
            "id": f"gate:{self.lock}", "pair_id": self.lock,
            "trigger": "exclusivity_raised", "status": "open",
            "opened_at": "W1 Sun 21:00",
        })
        self.conn.commit()

    def gate(self):
        return dict(db.fetch_one(self.conn, "StageGate", pair_id=self.lock))

    def test_consent_now_sends_you_to_the_shared_ceremony(self):
        self.login("u1")
        response = self.client.post("/gate/consent")
        self.assertIn(f"/ceremony/{ceremony.RELATIONSHIP_ENTRY}", response.headers["Location"])

    def test_it_no_longer_signs_anything_by_itself(self):
        self.login("u1")
        self.client.post("/gate/consent")
        self.assertFalse(self.gate()["consent_a"])

    def test_completing_the_ceremony_writes_the_gate_row(self):
        """The ceremony is the front end; the gate row stays the source of
        truth for every rule already written against it."""
        self.complete_ceremony(ceremony.RELATIONSHIP_ENTRY, "u1")
        gate = self.gate()
        self.assertTrue(gate["consent_a"])
        self.assertTrue(gate["biometric_a"])
        self.assertFalse(gate["consent_b"])

    def test_both_signing_fills_in_both_halves(self):
        for uid in ("u1", "u2"):
            self.complete_ceremony(ceremony.RELATIONSHIP_ENTRY, uid)
        gate = self.gate()
        self.assertTrue(gate["consent_a"] and gate["consent_b"])

    def test_the_gate_screen_no_longer_has_its_own_sign_button(self):
        """The consent step only renders once the earlier steps are done,
        so this reads the template rather than driving nine steps to see
        one link. What matters is that the duplicate path is gone."""
        from pathlib import Path
        template = Path(app_module.__file__).with_name("templates") / "gate.html"
        markup = template.read_text(encoding="utf-8")
        self.assertIn(f"kind='{ceremony.RELATIONSHIP_ENTRY}'", markup)
        self.assertNotIn("Sign &amp; verify", markup)


class StageGateFeeTests(PairCase):
    """Segment I, 36b: the ₹2,999 fee used to be unconnected at both ends."""

    def setUp(self):
        super().setUp()
        self._pay = mock.patch.dict(os.environ, {"PAYMENTS_ENABLED": "1"})
        self._pay.start()
        self.addCleanup(self._pay.stop)

    def test_the_checkpoint_charges_before_anything_is_signed(self):
        self.login("u1")
        self.client.get(f"/ceremony/{ceremony.STAGE_GATE}")
        response = self.client.post(f"/ceremony/{ceremony.STAGE_GATE}/step")
        self.assertIn("/pay/stage_gate", response.headers["Location"])

    def test_the_screen_names_the_amount(self):
        self.login("u1")
        body = self.client.get(f"/ceremony/{ceremony.STAGE_GATE}").get_data(as_text=True)
        self.assertIn("₹2,999", body)

    def test_once_paid_the_checkpoint_runs(self):
        self.login("u1")
        self.client.post("/pay/stage_gate/confirm", data={})
        self.client.get(f"/ceremony/{ceremony.STAGE_GATE}")
        self.client.post(f"/ceremony/{ceremony.STAGE_GATE}/step")
        self.assertTrue(self.cer(ceremony.STAGE_GATE, "u1")["playbook_ack"])


# ══ Segment J ═══════════════════════════════════════════════════════════


class DemoScaffoldingTests(PairCase):
    def test_the_pair_finder_lists_pairs_without_a_sql_query(self):
        body = self.client.get("/admin/pairs").get_data(as_text=True)
        self.assertIn("Who can walk the journey", body)

    def test_it_says_so_plainly_when_nobody_can_match(self):
        """An empty list is a matching-model result, not a broken page."""
        body = self.client.get("/admin/pairs").get_data(as_text=True)
        self.assertIn("matching-model", body)

    def test_resetting_a_pair_clears_what_the_journey_wrote(self):
        self.reach_first_date()
        self.complete_ceremony(ceremony.CONTACT_SHARE, "u1")
        self.assertIsNotNone(db.fetch_one(self.conn, "DatePlan", lockin_id=self.lock))

        self.client.post("/admin/reset-walkthrough",
                         data={"user_id": "u1", "partner_id": "u2"})
        self.assertIsNone(db.fetch_one(self.conn, "DatePlan", lockin_id=self.lock))
        self.assertIsNone(db.fetch_one(self.conn, "LockIn", id=self.lock))
        self.assertIsNone(db.fetch_one(self.conn, "Ceremony", user_id="u1"))

    def test_a_reset_leaves_both_verified_and_dating(self):
        """Back to step 1 of the DATING journey, not back to a sign-up form
        that is already done."""
        self.client.post("/admin/reset-walkthrough",
                         data={"user_id": "u1", "partner_id": "u2"})
        for uid in ("u1", "u2"):
            row = db.fetch_one(self.conn, "User", id=uid)
            self.assertEqual(row["journey_state"], "dating")
            self.assertEqual(row["bgv_status"], "verified")

    def test_a_reset_puts_the_clock_back_to_monday(self):
        self.set_clock(week=1, day="Sat", hour=20)
        self.client.post("/admin/reset-walkthrough", data={"user_id": "u1", "partner_id": "u2"})
        self.assertEqual(str(app_module.get_clock()), "Mon:12")

    def test_the_stage_indicator_appears_on_every_page(self):
        for path in ("/dashboard", "/guru", "/week"):
            with self.subTest(path=path):
                body = self.client.get(path).get_data(as_text=True)
                self.assertIn("stage-bar", body)

    def test_it_shows_the_stage_rather_than_a_step_count(self):
        """2026-09-04: "Step 11 of 12" invited the question "what are the
        other eleven?" — the confusion it existed to remove."""
        body = self.client.get("/dashboard").get_data(as_text=True)
        for stage in ("Dating", "Relationship", "Engaged", "Married"):
            self.assertIn(stage, body)
        self.assertNotIn("of 12", body)

    def test_every_signed_in_screen_has_a_way_back(self):
        """2026-09-04, user's rule: "Closing the app is not the solution"."""
        for path in ("/guru", "/week", "/dashboard", "/vision", "/chemistry"):
            with self.subTest(path=path):
                body = self.client.get(path).get_data(as_text=True)
                self.assertIn("backlink", body)


if __name__ == "__main__":
    unittest.main()


class GateConversationRouteTests(PairCase):
    """The gate end to end: ask, answer, wait, commit.

    The route-level half of gate_conversation's two rules — a pause that a
    disabled button would not actually enforce, and a screen that must
    never leak one person's words to the other.
    """

    SCALE = "ready_meet_friends"

    def setUp(self):
        super().setUp()
        self.reach_first_date()
        db.insert_row(self.conn, "StageGate", {
            "id": f"gate:{self.lock}", "pair_id": self.lock,
            "trigger": "exclusivity_raised", "status": "open",
            "opened_at": "W1 Sun 21:00",
        })
        self.conn.commit()

    def gate(self):
        return dict(db.fetch_one(self.conn, "StageGate", pair_id=self.lock))

    def ask(self, user_id, *keys):
        self.login(user_id)
        return self.client.post("/gate/ask", data={"question_key": list(keys)})

    def answer(self, user_id, key, scale=None, text=None):
        self.login(user_id)
        return self.client.post("/gate/respond", data={
            "question_key": key, "readiness_scale": scale or "", "answer_text": text or ""})

    def test_asking_puts_the_question_to_both_of_them(self):
        self.ask("u1", self.SCALE)
        rows = db.fetch_all(self.conn, "GateAsk", pair_id=self.lock)
        self.assertEqual([r["question_key"] for r in rows], [self.SCALE])
        self.assertEqual(rows[0]["asked_by"], "u1")

    def test_the_screen_never_says_who_asked(self):
        self.ask("u1", self.SCALE)
        self.login("u2")
        body = self.client.get("/gate").get_data(as_text=True)
        self.assertIn("You are both answering", body)
        self.assertNotIn("asked by", body.lower())

    def test_asking_more_than_the_cap_is_refused(self):
        keys = [q["key"] for q in gate_conversation.askable([])][:4]
        self.ask("u1", *keys)
        self.assertEqual(db.fetch_all(self.conn, "GateAsk", pair_id=self.lock), [])

    def test_you_cannot_answer_something_nobody_asked(self):
        self.answer("u1", self.SCALE, scale="ready_now")
        self.assertEqual(db.fetch_all(self.conn, "GateResponse", pair_id=self.lock), [])

    def test_the_pause_starts_only_once_both_have_answered(self):
        self.ask("u1", self.SCALE)
        self.answer("u1", self.SCALE, scale="ready_now")
        self.assertIsNone(self.gate()["answers_closed_at"])
        self.answer("u2", self.SCALE, scale="soon")
        self.assertIsNotNone(self.gate()["answers_closed_at"])

    def test_committing_before_the_pause_is_refused_by_the_route(self):
        """A disabled button is not a rule. This is the behaviour the whole
        feature exists to prevent."""
        self.ask("u1", self.SCALE)
        self.answer("u1", self.SCALE, scale="ready_now")
        self.answer("u2", self.SCALE, scale="soon")
        self.login("u1")
        response = self.client.post("/gate/confirm")
        self.assertIn("early=1", response.headers["Location"])
        self.assertFalse(self.gate()["confirm_a"])

    def test_committing_works_once_the_pause_has_run(self):
        self.ask("u1", self.SCALE)
        self.answer("u1", self.SCALE, scale="ready_now")
        self.answer("u2", self.SCALE, scale="soon")
        self.set_clock(week=1, day="Tue", hour=12)   # well past 12 hours
        self.login("u1")
        self.client.post("/gate/confirm")
        self.assertTrue(self.gate()["confirm_a"])

    def test_asking_again_restarts_the_pause(self):
        """A new question means something new to sit with."""
        self.ask("u1", self.SCALE)
        self.answer("u1", self.SCALE, scale="ready_now")
        self.answer("u2", self.SCALE, scale="soon")
        self.assertIsNotNone(self.gate()["answers_closed_at"])
        self.ask("u2", "exclusivity_check")
        self.assertIsNone(self.gate()["answers_closed_at"])

    def test_one_persons_words_never_reach_the_other(self):
        self.ask("u1", "who_knows")
        self.answer("u1", "who_knows", text="I told my sister and two close friends")
        self.answer("u2", "who_knows", text="Nobody yet")
        self.login("u2")
        body = self.client.get("/gate").get_data(as_text=True)
        for word in ("sister", "close friends"):
            self.assertNotIn(word, body)

    def test_a_gap_is_reported_without_naming_either_side(self):
        self.ask("u1", self.SCALE)
        self.answer("u1", self.SCALE, scale="ready_now")
        self.answer("u2", self.SCALE, scale="not_yet")
        self.login("u2")
        body = self.client.get("/gate").get_data(as_text=True)
        self.assertIn("not in the same place", body)
        self.assertNotIn("ready_now", body.split("On the table")[-1])


class AfterDateScreenTests(PairCase):
    """One post-date screen instead of three cards to choose between.

    2026-09-04, user's rule: "I think request for no and socials can be
    kept after first date. Maybe post date expectations all of these can
    be clubbed together."
    """

    def setUp(self):
        super().setUp()
        self.reach_first_date()
        self.login("u1")

    def test_it_is_locked_before_a_first_date(self):
        other = self.make_user("u3")
        self.login(other)
        self.assertNotEqual(self.client.get("/after-date").status_code, 200)

    def test_all_three_parts_are_on_the_one_screen(self):
        body = self.client.get("/after-date").get_data(as_text=True)
        for part in ("What you each expect", "Numbers and socials",
                     "Whether this goes further"):
            with self.subTest(part=part):
                self.assertIn(part, body)

    def test_contact_sharing_opens_after_one_date(self):
        """escalations.unlocks_available() demanded two dates while
        disclosure opened the surface at FIRST_DATE. One rule now."""
        body = self.client.get("/after-date").get_data(as_text=True)
        self.assertIn("Read and sign", body)

    def test_it_reports_expectations_progress(self):
        body = self.client.get("/after-date").get_data(as_text=True)
        self.assertIn("0/5", body)

    def test_it_has_a_way_back_to_guru(self):
        body = self.client.get("/after-date").get_data(as_text=True)
        self.assertIn("backlink", body)
        self.assertIn("Guru", body)


class GuruFocusTests(PairCase):
    """One answer, at most two cards, and one link to the rest.

    2026-09-04, user's rule: "All other tabs being visible under guru,
    doesn't make sense as well. Keep this intuitive rather than with
    multiple options, which is very confusing."
    """

    def setUp(self):
        super().setUp()
        self.reach_first_date()
        self.login("u1")

    def tiles(self, path="/guru"):
        return self.client.get(path).get_data(as_text=True).count('class="guru-tile"')

    def test_the_hub_never_shows_more_than_the_cap(self):
        self.assertLessEqual(self.tiles(), app_module.guru.MAX_CARDS)

    def test_the_rest_is_one_link_away_not_gone(self):
        """A screen that silently drops a door you used yesterday is its
        own confusion."""
        body = self.client.get("/guru").get_data(as_text=True)
        self.assertIn(url_for_everything := "/guru/everything", body)
        self.assertGreaterEqual(self.tiles("/guru/everything"), self.tiles("/guru"))

    def test_everything_else_has_a_way_back(self):
        body = self.client.get("/guru/everything").get_data(as_text=True)
        self.assertIn("backlink", body)

    def test_a_raised_gate_is_the_first_thing_on_the_screen(self):
        """user's rule: "If one of them expressed moving to next stage it
        should be visible or first thing someone wants to see"."""
        self.login("u2")
        self.client.post("/gate/raise")
        self.login("u1")
        body = self.client.get("/guru").get_data(as_text=True)
        headline = body.split('class="guru-avatar"')[1]
        self.assertIn("has raised the next stage", headline)
        # and it is above every tile on the page
        self.assertLess(body.index("has raised the next stage"),
                        body.index('class="guru-tile"') if 'class="guru-tile"' in body else len(body))

    def test_it_names_the_partner_who_raised_it(self):
        self.login("u2")
        self.client.post("/gate/raise")
        self.login("u1")
        with app_module.app.app_context():
            name = app_module.with_view_fields(app_module.load_user("u2"))["name"]
        self.assertIn(name, self.client.get("/guru").get_data(as_text=True))

    def test_the_person_who_raised_it_is_not_told_they_raised_it(self):
        self.login("u1")
        self.client.post("/gate/raise")
        body = self.client.get("/guru").get_data(as_text=True)
        self.assertIn("The next stage is on the table", body)

    def test_the_gate_is_not_also_a_tile_once_it_is_the_answer(self):
        """The same door twice is the crowding, not the fix."""
        self.client.post("/gate/raise")
        body = self.client.get("/guru").get_data(as_text=True)
        self.assertEqual(body.count('href="/gate"'), 1)
